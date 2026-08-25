from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class AudioSnapshot:
    samples: np.ndarray
    duration_seconds: float
    peak: float
    rms: float
    dropped_blocks: int


class BoundedAudioBuffer:
    """A fixed-size block buffer; recording time can never grow memory without bound."""

    def __init__(self, sample_rate: int, block_size: int, max_seconds: int):
        self.sample_rate = sample_rate
        self.block_size = block_size
        max_blocks = max(1, int(max_seconds * sample_rate / block_size) + 1)
        self._blocks: deque[np.ndarray] = deque(maxlen=max_blocks)
        self._lock = threading.Lock()
        self._dropped_blocks = 0

    def clear(self) -> None:
        with self._lock:
            self._blocks.clear()
            self._dropped_blocks = 0

    def append(self, block: np.ndarray) -> None:
        mono = np.asarray(block, dtype=np.float32).reshape(-1).copy()
        with self._lock:
            if len(self._blocks) == self._blocks.maxlen:
                self._dropped_blocks += 1
            self._blocks.append(mono)

    def snapshot(self) -> AudioSnapshot:
        with self._lock:
            blocks = tuple(self._blocks)
            dropped = self._dropped_blocks
        samples = np.concatenate(blocks).astype(np.float32, copy=False) if blocks else np.empty(0, np.float32)
        if samples.size:
            peak = float(np.max(np.abs(samples)))
            rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
        else:
            peak = rms = 0.0
        return AudioSnapshot(samples, samples.size / self.sample_rate, peak, rms, dropped)


class AudioCapture:
    def __init__(self, config, level_callback=None):
        self.config = config
        self.level_callback = level_callback or (lambda level: None)
        self.buffer = BoundedAudioBuffer(
            config.sample_rate, config.block_size, config.max_recording_seconds
        )
        self.stream = None
        self.recording = False
        self._lock = threading.Lock()

    def open(self) -> None:
        import sounddevice as sd

        if self.stream is not None:
            return
        self.stream = sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.config.block_size,
            device=self.config.audio_device,
            latency="low",
            callback=self._callback,
        )
        self.stream.start()

    def _callback(self, indata, frames, time_info, status) -> None:
        del frames, time_info
        block = np.asarray(indata, dtype=np.float32)
        rms = float(np.sqrt(np.mean(np.square(block, dtype=np.float64)))) if block.size else 0.0
        self.level_callback(min(1.0, rms * 30.0))
        with self._lock:
            active = self.recording
        if active:
            self.buffer.append(block)

    def start(self) -> None:
        self.open()
        self.buffer.clear()
        with self._lock:
            self.recording = True

    def stop(self) -> AudioSnapshot:
        with self._lock:
            self.recording = False
        return self.buffer.snapshot()

    def close(self) -> None:
        with self._lock:
            self.recording = False
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None

