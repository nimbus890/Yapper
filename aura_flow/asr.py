from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
import threading

import numpy as np


@dataclass(frozen=True, slots=True)
class Transcription:
    text: str
    language: str
    language_probability: float
    elapsed_ms: float


class FasterWhisperEngine:
    def __init__(self, model_path: Path, config, cpu_threads: int = 6):
        self.model_path = model_path
        self.config = config
        self.model = None
        self.device = ""
        self.compute_type = ""
        self.cpu_threads = cpu_threads
        self._transcribe_lock = threading.Lock()

    @staticmethod
    def _cuda_available() -> bool:
        try:
            import ctranslate2

            return ctranslate2.get_cuda_device_count() > 0
        except Exception:
            return False

    def load(self) -> None:
        from faster_whisper import WhisperModel

        attempts: list[tuple[str, str]] = []
        requested = self.config.device.lower()
        if requested in {"auto", "cuda"} and (requested == "cuda" or self._cuda_available()):
            attempts.append(("cuda", self.config.cuda_compute_type))
        if requested in {"auto", "cpu"}:
            attempts.append(("cpu", self.config.cpu_compute_type))
        if not attempts:
            attempts.append((requested, self.config.cuda_compute_type))

        errors: list[str] = []
        for device, compute_type in attempts:
            try:
                self.model = WhisperModel(
                    str(self.model_path),
                    device=device,
                    compute_type=compute_type,
                    local_files_only=True,
                    cpu_threads=self.cpu_threads if device == "cpu" else 0,
                    num_workers=1,
                )
                self.device = device
                self.compute_type = compute_type
                return
            except Exception as exc:
                errors.append(f"{device}/{compute_type}: {exc}")
        raise RuntimeError("Could not load speech model locally. " + " | ".join(errors))

    def transcribe(
        self,
        audio: np.ndarray,
        hotwords: str | None = None,
        *,
        vad_filter: bool = True,
    ) -> Transcription:
        if self.model is None:
            raise RuntimeError("Speech model is not loaded")
        start = time.perf_counter()
        with self._transcribe_lock:
            segments, info = self.model.transcribe(
                audio,
                beam_size=1,
                best_of=1,
                temperature=0.0,
                language=self.config.language,
                condition_on_previous_text=False,
                vad_filter=vad_filter,
                without_timestamps=True,
                hotwords=hotwords,
            )
            text = "".join(segment.text for segment in segments).strip()
        return Transcription(
            text=text,
            language=getattr(info, "language", "") or "",
            language_probability=float(getattr(info, "language_probability", 0.0) or 0.0),
            elapsed_ms=(time.perf_counter() - start) * 1_000,
        )
