from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from .asr import FasterWhisperEngine
from .audio import AudioCapture, AudioSnapshot
from .cleanup import CleanupService, GrammarPolisher
from .config import APP_DIR, DATA_DIR, AppConfig
from .context import TargetWindow, WindowsContextProvider
from .credentials import ApiCredentialStore
from .formatting import DeterministicFormatter, FormatContext
from .history import HistoryStore
from .insertion import TextInserter
from .metrics import DictationMetrics, MetricsStore
from .models import choose_model, discover_models, write_manifest
from .partial import PartialTranscriber
from .personalization import PersonalizationStore
from .remote_semantic import RemoteSemanticFormatter
from .semantic import OptionalSemanticFormatter
from .vad import EnergyVad


class PipelineState(str, Enum):
    LOADING = "loading"
    READY = "ready"
    RECORDING = "recording"
    PROCESSING = "processing"
    ERROR = "error"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class WorkItem:
    session_id: str
    submitted_at: float
    audio: AudioSnapshot
    target: TargetWindow
    live_transcript: str = ""


def _word_count(text: str) -> int:
    return len(text.split())


def final_asr_is_incomplete(final_text: str, live_text: str) -> bool:
    """Detect a final whole-recording pass that lost most of a fuller preview."""

    final_words = _word_count(final_text)
    live_words = _word_count(live_text)
    return live_words >= 8 and (
        final_words <= 3 or final_words < live_words * 0.45
    )


def tiny_live_is_final(model_name: str, live_text: str) -> bool:
    """Tiny mode uses its accumulated live result instead of a second pass."""

    return model_name == "tiny.en" and _word_count(live_text) >= 3


def choose_recovered_transcript(
    final_text: str,
    retry_text: str,
    live_text: str,
) -> tuple[str, str]:
    """Prefer the complete Medium retry, then the accumulated live preview."""

    best_final = max((final_text, retry_text), key=_word_count)
    if not final_asr_is_incomplete(best_final, live_text):
        return best_final, "final-retry" if best_final == retry_text and retry_text else "final"
    return live_text.strip(), "live-preview-recovery"


class DictationPipeline:
    def __init__(self, config: AppConfig, event_callback: Callable[[dict], None] | None = None):
        self.config = config
        self.event_callback = event_callback or (lambda event: None)
        self.state = PipelineState.LOADING
        self.state_lock = threading.Lock()
        self.context = WindowsContextProvider(config.context_awareness)
        self._context_poll_lock = threading.Lock()
        self.current_target = TargetWindow(None, None, "", "", "other")
        self.current_session = ""
        self.audio = AudioCapture(config, lambda level: self.emit("level", value=level))
        self.vad = EnergyVad(config.sample_rate, config.vad_rms_threshold, config.min_speech_seconds)
        self.personalization = PersonalizationStore(DATA_DIR / "personalization.json")
        self.formatter = DeterministicFormatter()
        self.reload_personalization()
        self.credentials = ApiCredentialStore(DATA_DIR / "api_key.bin")
        self.semantic = self._build_semantic_formatter()
        self.cleanup = CleanupService(self.semantic, config.formatter_timeout_seconds)
        self.inserter = TextInserter(
            DATA_DIR / "last_transcript.txt", config.restore_clipboard, config.direct_insertion
        )
        self.metrics = MetricsStore(DATA_DIR / "metrics.jsonl")
        self.history = HistoryStore(DATA_DIR / "history.jsonl", config.store_history)
        self.engine: FasterWhisperEngine | None = None
        self.model_name = ""
        self.work_queue: queue.Queue[WorkItem | None] = queue.Queue(maxsize=1)
        self.worker = threading.Thread(target=self._worker_loop, name="inference-worker", daemon=True)
        self.closed = threading.Event()
        self.partial = PartialTranscriber(
            config,
            self.audio,
            lambda preview, cumulative: self.emit(
                "partial", text=cumulative, preview=preview
            ),
        )

    def reload_personalization(self) -> None:
        data = self.personalization.load()
        self.formatter.refresh(data.replacements, data.snippets)
        self.emit(
            "personalization",
            vocabulary=len(data.vocabulary),
            replacements=len(data.replacements),
            snippets=len(data.snippets),
        )

    def _build_semantic_formatter(self):
        if self.config.api_enabled:
            remote = RemoteSemanticFormatter(self.config, self.credentials.load())
            if remote.available:
                return remote
        return OptionalSemanticFormatter(
            self.config.semantic_formatting,
            self.config.semantic_model_path,
        )

    def reload_api_formatter(self) -> None:
        """Activate a newly saved online profile or return to local Gemma."""
        self.semantic = self._build_semantic_formatter()
        self.cleanup = CleanupService(
            self.semantic,
            self.config.formatter_timeout_seconds,
        )
        self.semantic.load_async(
            lambda message, ready: self.emit(
                "semantic_status", message=message, ready=ready
            )
        )

    def emit(self, kind: str, **payload) -> None:
        try:
            self.event_callback({"type": kind, **payload})
        except Exception:
            pass

    def _set_state(self, state: PipelineState) -> None:
        with self.state_lock:
            self.state = state
        self.emit("state", state=state.value)

    def start(self) -> None:
        self.worker.start()
        threading.Thread(target=self._load_engine, name="model-loader", daemon=True).start()
        if self.config.model_name != "tiny.en":
            self.partial.load_async(lambda message: self.emit("partial_status", message=message))
        self.semantic.load_async(
            lambda message, ready: self.emit("semantic_status", message=message, ready=ready)
        )

    def _load_engine(self) -> None:
        try:
            candidates = discover_models(APP_DIR)
            write_manifest(APP_DIR, candidates)
            chosen = choose_model(APP_DIR, self.config.model_path, self.config.model_name)
            self.emit("status", message=f"Loading {chosen.name} locally…")
            engine = FasterWhisperEngine(chosen.path, self.config)
            engine.load()
            self.engine = engine
            self.model_name = chosen.name
            if chosen.name == "tiny.en" and self.config.partial_transcription:
                self.partial.use_shared_engine(engine)
                self.emit("partial_status", message="Tiny live/final engine ready")
            elif self.config.model_name == "tiny.en":
                self.partial.load_async(
                    lambda message: self.emit("partial_status", message=message)
                )
            self.emit(
                "model",
                name=chosen.name,
                path=str(chosen.path),
                device=engine.device,
                compute_type=engine.compute_type,
                warning=(
                    "Medium ASR on CPU will be slow; install a small English model or repair CUDA."
                    if engine.device == "cpu" and "medium" in chosen.name.lower()
                    else ""
                ),
            )
            self._set_state(PipelineState.READY)
            shortcut = self.config.hotkey.upper().replace("+", " + ")
            self.emit("status", message=f"Ready — hold {shortcut} to dictate")
            self.emit(
                "context",
                accessibility=self.context.accessibility_available,
                direct_insertion=bool(self.inserter.uia),
            )
        except Exception as exc:
            self._set_state(PipelineState.ERROR)
            self.emit("error", message=str(exc))

    def poll_context(self) -> None:
        if not self._context_poll_lock.acquire(blocking=False):
            return

        def capture() -> None:
            try:
                self.context.current_target()
            finally:
                self._context_poll_lock.release()

        threading.Thread(target=capture, name="context-reader", daemon=True).start()

    def usage_stats(self) -> dict[str, float | int]:
        return self.history.stats(self.config.typing_wpm_baseline)

    def set_audio_device(self, device: int | None) -> None:
        self.config.audio_device = device
        self.config.save()
        if self.state == PipelineState.RECORDING:
            return
        try:
            self.audio.close()
        except Exception:
            pass

    def restore_history(self, entry_id: str, use_raw: bool = True) -> bool:
        entry = self.history.get(entry_id)
        if not entry:
            self.emit("error", message="That history entry is no longer available.")
            return False
        text = str(entry.get("raw" if use_raw else "final", ""))
        if not text:
            return False
        target = self.context.best_external_target()
        result = self.inserter.insert(text, target)
        self.emit("insertion", success=result.success, method=result.method, message=result.message)
        self.emit("status", message="Restored original dictation" if use_raw else "Reinserted formatted text")
        return result.success

    def paste_latest_final(self) -> bool:
        """Insert the newest finished output from history, regardless of age."""
        entries = self.history.recent(1)
        if not entries:
            self.emit("status", message="No finished output is available in history")
            return False
        text = str(entries[0].get("final", "")).strip()
        if not text:
            self.emit("status", message="The latest history entry has no finished output")
            return False
        target = self.context.best_external_target()
        result = self.inserter.insert(text, target)
        self.emit("insertion", success=result.success, method=result.method, message=result.message)
        self.emit("status", message="Pasted latest finished output" if result.success else result.message)
        return result.success

    def undo_last_formatting(self) -> bool:
        entries = self.history.recent(1)
        if not entries:
            self.emit("status", message="No formatted dictation is available to undo")
            return False
        entry = entries[0]
        target = self.context.best_external_target()
        undone = self.inserter.perform_action("undo", target)
        if not undone.success:
            self.emit("insertion", success=False, method=undone.method, message=undone.message)
            return False
        restored = self.inserter.insert(str(entry.get("raw", "")), target)
        self.emit(
            "insertion",
            success=restored.success,
            method=restored.method,
            message="Restored the original dictation" if restored.success else restored.message,
        )
        return restored.success

    def start_recording(self) -> bool:
        with self.state_lock:
            if self.state != PipelineState.READY:
                return False
            self.state = PipelineState.RECORDING
        try:
            # Context is sampled continually in the background. Reusing the
            # cached target keeps the hotkey-to-audio path immediate even when
            # an application has a slow accessibility tree.
            cached = self.context.last_external
            self.current_target = cached if cached.process_id else self.context.best_external_target()
            self.current_session = uuid.uuid4().hex
            self.audio.start()
            self.partial.start_session()
        except Exception as exc:
            self._set_state(PipelineState.ERROR)
            self.emit("error", message=f"Microphone failed: {exc}")
            return False
        self.emit("state", state=PipelineState.RECORDING.value)
        self.emit(
            "context_target",
            app=self.current_target.process_name,
            category=self.current_target.category,
            context_available=self.current_target.context_available,
            direct=self.current_target.direct_insertion_available,
        )
        self.emit("status", message="Listening…")
        return True

    def stop_recording(self) -> bool:
        with self.state_lock:
            if self.state != PipelineState.RECORDING:
                return False
            self.state = PipelineState.PROCESSING
        audio = self.audio.stop()
        live_transcript = self.partial.stop_session()
        self.emit("state", state=PipelineState.PROCESSING.value)
        decision = self.vad.analyze(audio.samples)
        self.emit(
            "vad",
            accepted=decision.accepted,
            speech_seconds=decision.speech_seconds,
            speech_ratio=decision.speech_ratio,
            threshold=decision.threshold,
        )
        if audio.duration_seconds < self.config.min_recording_seconds or not decision.accepted:
            metrics = DictationMetrics(
                session_id=self.current_session,
                audio_seconds=audio.duration_seconds,
                speech_seconds=decision.speech_seconds,
                result="rejected_by_vad",
            )
            self.metrics.append(metrics)
            self._set_state(PipelineState.READY)
            self.emit("status", message="No speech detected — try again")
            return False
        item = WorkItem(
            self.current_session,
            time.perf_counter(),
            audio,
            self.current_target,
            live_transcript,
        )
        try:
            self.work_queue.put_nowait(item)
        except queue.Full:
            self._set_state(PipelineState.READY)
            self.emit("error", message="The inference queue is busy; recording was preserved in memory only.")
            return False
        self.emit("status", message="Transcribing…")
        return True

    def toggle(self) -> None:
        state = self.state
        if state == PipelineState.READY:
            self.start_recording()
        elif state == PipelineState.RECORDING:
            self.stop_recording()
        else:
            self.emit("status", message=f"yapper_ is {state.value}; please wait")

    def cancel_recording(self) -> None:
        if self.state != PipelineState.RECORDING:
            return
        self.audio.stop()
        self.partial.stop_session()
        self.current_session = ""
        self._set_state(PipelineState.READY)
        self.emit("status", message="Recording cancelled")

    def _worker_loop(self) -> None:
        while not self.closed.is_set():
            item = self.work_queue.get()
            if item is None:
                return
            self._process(item)

    def _hotwords(self) -> str | None:
        return self.personalization.hotwords()

    def _process(self, item: WorkItem) -> None:
        metrics = DictationMetrics(
            session_id=item.session_id,
            audio_seconds=item.audio.duration_seconds,
            queue_wait_ms=(time.perf_counter() - item.submitted_at) * 1_000,
            model=self.model_name,
            device=self.engine.device if self.engine else "",
        )
        total_start = time.perf_counter()
        try:
            if self.engine is None:
                raise RuntimeError("Speech engine is unavailable")
            language = ""
            if tiny_live_is_final(self.model_name, item.live_transcript):
                raw = item.live_transcript.strip()
                asr_recovery = "tiny-live-single-engine"
                metrics.asr_ms = 0.0
            else:
                transcript = self.engine.transcribe(item.audio.samples, self._hotwords())
                metrics.asr_ms = transcript.elapsed_ms
                raw = transcript.text
                language = transcript.language
                asr_recovery = "final"
                if final_asr_is_incomplete(raw, item.live_transcript) or (
                    not raw and item.audio.duration_seconds >= 1.0
                ):
                    self.emit("status", message="Final transcript was incomplete — recovering…")
                    retry = self.engine.transcribe(
                        item.audio.samples,
                        self._hotwords(),
                        vad_filter=False,
                    )
                    metrics.asr_ms += retry.elapsed_ms
                    raw, asr_recovery = choose_recovered_transcript(
                        raw,
                        retry.text,
                        item.live_transcript,
                    )
            self.emit("raw", text=raw, language=language)
            if not raw:
                metrics.result = "empty_transcript"
                self.emit("status", message="No words recognized — try again")
                return

            self.emit("status", message="Formatting…")
            format_start = time.perf_counter()
            base_context = self.context.formatting_context(item.target)
            context = FormatContext(
                app_category=base_context.app_category,
                before_cursor=base_context.before_cursor,
                after_cursor=base_context.after_cursor,
                selected_text=base_context.selected_text,
                style="default",
                cleanup_level=self.config.cleanup_level,
            )
            fast_result = self.formatter.format(raw, context)
            final = fast_result.text
            if fast_result.action:
                if fast_result.action == "undo_cleanup":
                    success = self.undo_last_formatting()
                    metrics.format_ms = (time.perf_counter() - format_start) * 1_000
                    metrics.result = "undo_cleanup" if success else "undo_cleanup_failed"
                    return
                if fast_result.action.startswith("rewrite_"):
                    if not item.target.selected_text:
                        self.emit("status", message="Select text first, then say the rewrite command")
                        metrics.result = "voice_action_no_selection"
                        return
                    final = GrammarPolisher.rewrite_selection(
                        item.target.selected_text, fast_result.action
                    )
                    inserted = self.inserter.insert(final, item.target)
                    self.emit("final", text=final, cleanup="selection-command", fallback=False)
                else:
                    inserted = self.inserter.perform_action(fast_result.action, item.target)
                metrics.format_ms = (time.perf_counter() - format_start) * 1_000
                metrics.insert_ms = inserted.elapsed_ms
                metrics.result = "voice_action" if inserted.success else "voice_action_failed"
                self.emit("insertion", success=inserted.success, method=inserted.method, message=inserted.message)
                self.emit("status", message=inserted.message)
                return

            cleaned = self.cleanup.clean(
                final,
                "none" if fast_result.snippet_trigger else context.cleanup_level,
                fast_result.style,
                item.target.category,
                mid_sentence=bool(
                    context.before_cursor[-1:].isalnum()
                    and context.after_cursor[:1].isalnum()
                ),
                original_text=raw,
            )
            final = cleaned.text
            metrics.format_ms = (time.perf_counter() - format_start) * 1_000
            self.emit(
                "final",
                text=final,
                cleanup=cleaned.method,
                level=context.cleanup_level,
                fallback=cleaned.fallback,
                detail=cleaned.detail,
            )

            self.emit("status", message="Inserting…")
            inserted = self.inserter.insert(final, item.target, fast_result.press_enter)
            metrics.insert_ms = inserted.elapsed_ms
            metrics.words = len(final.split())
            metrics.result = "inserted" if inserted.success else "clipboard_fallback"
            history_entry = self.history.append(
                raw,
                final,
                {
                    "session_id": item.session_id,
                    "app": item.target.process_name,
                    "category": item.target.category,
                    "style": fast_result.style,
                    "cleanup_level": context.cleanup_level,
                    "cleanup_method": cleaned.method,
                    "formatter_fallback": cleaned.fallback,
                    "semantic_validation": context.cleanup_level == "smart",
                    "protected_literal_guard": True,
                    "intent_preservation_guard": True,
                    "cleanup_detail": cleaned.detail,
                    "context_available": item.target.context_available,
                    "insertion_method": inserted.method,
                    "model": self.model_name,
                    "device": metrics.device,
                    "audio_seconds": item.audio.duration_seconds,
                    "asr_recovery": asr_recovery,
                },
            )
            self.emit("history", entry=history_entry, stats=self.usage_stats())
            self.emit("insertion", success=inserted.success, method=inserted.method, message=inserted.message)
            self.emit("status", message="Inserted" if inserted.success else inserted.message)
        except Exception as exc:
            metrics.result = "failed"
            metrics.error = str(exc)
            self.emit("error", message=f"Dictation failed: {exc}")
        finally:
            metrics.total_ms = (time.perf_counter() - total_start) * 1_000
            self.metrics.append(metrics)
            self.emit("timing", **{
                "queue_ms": metrics.queue_wait_ms,
                "asr_ms": metrics.asr_ms,
                "format_ms": metrics.format_ms,
                "insert_ms": metrics.insert_ms,
                "total_ms": metrics.total_ms,
            })
            if self.state != PipelineState.CLOSED:
                self._set_state(PipelineState.READY)

    def close(self) -> None:
        self.closed.set()
        self.partial.stop_session()
        self._set_state(PipelineState.CLOSED)
        try:
            self.audio.close()
        except Exception:
            pass
        try:
            self.work_queue.put_nowait(None)
        except queue.Full:
            pass
