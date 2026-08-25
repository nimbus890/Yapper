from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path


class HistoryStore:
    def __init__(self, path: Path, enabled: bool):
        self.path = path
        self.enabled = enabled
        self._lock = threading.RLock()

    def append(self, raw: str, final: str, metadata: dict[str, object]) -> dict[str, object]:
        payload = {
            "id": uuid.uuid4().hex,
            "timestamp": time.time(),
            "raw": raw,
            "final": final,
            **metadata,
        }
        if not self.enabled:
            return payload
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return payload

    def recent(self, limit: int = 30, query: str = "") -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        needle = query.casefold().strip()
        results: list[dict[str, object]] = []
        for line in reversed(lines):
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if needle and needle not in f"{item.get('raw', '')} {item.get('final', '')}".casefold():
                continue
            results.append(item)
            if len(results) >= limit:
                break
        return results

    def get(self, entry_id: str) -> dict[str, object] | None:
        return next((item for item in self.recent(10_000) if item.get("id") == entry_id), None)

    def all_entries(self) -> list[dict[str, object]]:
        """Return all readable entries, newest first."""
        return self.recent(1_000_000)

    def stats(self, typing_wpm: int = 40) -> dict[str, float | int]:
        entries = self.recent(100_000)
        today_date = datetime.now().date()
        today = [
            item for item in entries
            if datetime.fromtimestamp(float(item.get("timestamp", 0))).date() == today_date
        ]

        def word_count(items: list[dict[str, object]]) -> int:
            return sum(len(str(item.get("final", "")).split()) for item in items)

        words_today = word_count(today)
        total_words = word_count(entries)
        audio_seconds = sum(float(item.get("audio_seconds", 0) or 0) for item in today)
        speaking_wpm = round(words_today / (audio_seconds / 60)) if audio_seconds > 1 else 0
        typing_seconds = words_today / max(1, typing_wpm) * 60
        return {
            "words_today": words_today,
            "total_words": total_words,
            "speaking_wpm": speaking_wpm,
            "time_saved_minutes": max(0, round((typing_seconds - audio_seconds) / 60)),
            "dictations_today": len(today),
        }
