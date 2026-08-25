from __future__ import annotations

import threading
from difflib import SequenceMatcher
from dataclasses import replace
from pathlib import Path
from typing import Callable

from .asr import FasterWhisperEngine


def _word_key(word: str) -> str:
    return "".join(character for character in word.casefold() if character.isalnum() or character == "'")


def merge_partial_transcript(current: str, latest: str) -> str:
    """Reconcile an overlapping rolling ASR window with the live dashboard text.

    Tiny Whisper revises the beginning of its six-second window frequently, so
    exact suffix/prefix matching duplicates whole phrases.  Aligning words in
    the recent tail lets the new window replace its unstable region instead.
    """

    current = current.strip()
    latest = latest.strip()
    if not current:
        return latest
    if not latest:
        return current
    old_words = current.split()
    new_words = latest.split()
    old_keys = [_word_key(word) for word in old_words]
    new_keys = [_word_key(word) for word in new_words]
    tail_size = min(len(old_words), max(36, len(new_words) * 2))
    tail_start = len(old_words) - tail_size
    matcher = SequenceMatcher(
        None,
        old_keys[tail_start:],
        new_keys,
        autojunk=False,
    )
    blocks = [block for block in matcher.get_matching_blocks() if block.size]
    total_matching = sum(block.size for block in blocks)
    anchors = [block for block in blocks if block.size >= 2]
    if anchors or total_matching >= 3:
        # Prefer a strong block near the beginning of the new rolling window.
        # Everything following it is the model's newest revision of that tail.
        anchor = max(
            anchors or blocks,
            key=lambda block: (block.size * 4 - block.b, -block.a),
        )
        old_anchor = tail_start + anchor.a
        # Preserve the already displayed anchor (including its punctuation)
        # and take only genuinely new/revised words after that anchor.
        prefix = old_words[: old_anchor + anchor.size]
        # The newest window may have just discovered punctuation at the end of
        # the shared phrase; adopt that one boundary token without reflowing
        # the stable words before it.
        prefix[-1] = new_words[anchor.b + anchor.size - 1]
        return " ".join(prefix + new_words[anchor.b + anchor.size :]).strip()

    # With no trustworthy anchor, replace approximately one rolling window
    # instead of appending another copy of the same audio.  This is a visual
    # preview only; the final Medium transcript still processes the full audio.
    if len(new_words) <= 4 and current.rstrip().endswith((".", "!", "?")):
        return f"{current} {latest}".strip()
    if len(old_words) <= len(new_words) + 3:
        return latest
    replace_count = min(len(old_words), max(1, len(new_words)))
    return " ".join(old_words[:-replace_count] + new_words).strip()


def last_words(text: str, limit: int = 10) -> str:
    """Return the rolling overlay caption without altering the cumulative text."""

    words = text.strip().split()
    return " ".join(words[-max(1, int(limit)):])


class PartialTranscriber:
    """Optional preview ASR isolated from the final model and forced onto CPU.

    It is enabled only with a separately installed complete lightweight model.
    Therefore a preview can neither own the final engine lock nor consume its
    CUDA execution queue.
    """

    def __init__(self, config, audio_capture, callback: Callable[[str, str], None]):
        self.config = config
        self.audio_capture = audio_capture
        self.callback = callback
        self.engine: FasterWhisperEngine | None = None
        self.ready = False
        self.loading = False
        self._session_stop: threading.Event | None = None
        self._cumulative = ""
        self._cumulative_lock = threading.Lock()

    def cumulative_text(self) -> str:
        with self._cumulative_lock:
            return self._cumulative

    def use_shared_engine(self, engine: FasterWhisperEngine) -> None:
        """Use the selected Tiny final engine for live transcription too."""

        self.engine = engine
        self.ready = True
        self.loading = False

    def load_async(self, status_callback: Callable[[str], None]) -> None:
        path = Path(self.config.partial_model_path).resolve() if self.config.partial_model_path else None
        if (
            not self.config.partial_transcription
            or not path
            or not path.is_dir()
            or self.loading
            or self.ready
        ):
            return
        self.loading = True

        def load() -> None:
            try:
                preview_config = replace(self.config, device="cpu", cpu_compute_type="int8")
                engine = FasterWhisperEngine(path, preview_config, cpu_threads=2)
                engine.load()
                self.engine = engine
                self.ready = True
                status_callback("Partial transcription ready (isolated CPU model)")
            except Exception as exc:
                status_callback(f"Partial transcription unavailable: {exc}")
            finally:
                self.loading = False

        threading.Thread(target=load, name="partial-model-loader", daemon=True).start()

    def start_session(self) -> None:
        self.stop_session()
        with self._cumulative_lock:
            self._cumulative = ""
        if not self.config.partial_transcription:
            return
        stop = threading.Event()
        self._session_stop = stop

        def run() -> None:
            # A recording can begin while the lightweight preview model is
            # still loading. Keep the session alive so it joins immediately
            # when loading completes instead of silently missing the recording.
            while not stop.is_set() and (not self.ready or self.engine is None):
                stop.wait(0.08)
            if stop.is_set() or self.engine is None:
                return
            last_size = 0
            cumulative = ""
            while not stop.wait(self.config.partial_interval_seconds):
                snapshot = self.audio_capture.buffer.snapshot()
                if snapshot.samples.size == last_size:
                    continue
                last_size = snapshot.samples.size
                tail_samples = int(self.config.partial_tail_seconds * self.config.sample_rate)
                tail = snapshot.samples[-tail_samples:]
                if tail.size < self.config.sample_rate:
                    continue
                try:
                    result = self.engine.transcribe(tail)
                    if not stop.is_set() and result.text:
                        cumulative = merge_partial_transcript(cumulative, result.text)
                        with self._cumulative_lock:
                            self._cumulative = cumulative
                        preview = last_words(
                            cumulative,
                            getattr(self.config, "partial_preview_words", 10),
                        )
                        self.callback(preview, cumulative)
                except Exception:
                    continue

        threading.Thread(target=run, name="partial-transcriber", daemon=True).start()

    def stop_session(self) -> str:
        if self._session_stop:
            self._session_stop.set()
            self._session_stop = None
        return self.cumulative_text()
