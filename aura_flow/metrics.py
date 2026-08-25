from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class DictationMetrics:
    session_id: str
    audio_seconds: float = 0.0
    speech_seconds: float = 0.0
    queue_wait_ms: float = 0.0
    asr_ms: float = 0.0
    format_ms: float = 0.0
    insert_ms: float = 0.0
    total_ms: float = 0.0
    model: str = ""
    device: str = ""
    result: str = ""
    words: int = 0
    error: str = ""


class MetricsStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def append(self, metrics: DictationMetrics) -> None:
        payload = {"timestamp": time.time(), **asdict(metrics)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())

