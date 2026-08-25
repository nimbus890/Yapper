from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class PersonalizationData:
    vocabulary: list[str] = field(default_factory=list)
    replacements: dict[str, str] = field(default_factory=dict)
    snippets: dict[str, str] = field(default_factory=dict)


class PersonalizationStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self.data = PersonalizationData()
        self.load()

    def load(self) -> PersonalizationData:
        with self._lock:
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                payload = {}
            vocabulary = payload.get("vocabulary", [])
            replacements = payload.get("replacements", {})
            snippets = payload.get("snippets", {})
            self.data = PersonalizationData(
                vocabulary=[str(item).strip() for item in vocabulary if str(item).strip()],
                replacements={str(k).strip(): str(v) for k, v in replacements.items() if str(k).strip()},
                snippets={self.normalize_trigger(k): str(v) for k, v in snippets.items() if self.normalize_trigger(k)},
            )
            return self.data

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({
                    "vocabulary": self.data.vocabulary,
                    "replacements": self.data.replacements,
                    "snippets": self.data.snippets,
                }, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)

    @staticmethod
    def normalize_trigger(value: str) -> str:
        return re.sub(r"\s+", " ", str(value).strip().lower())

    def hotwords(self) -> str | None:
        with self._lock:
            words = list(self.data.vocabulary)
            words.extend(self.data.replacements.values())
        unique = list(dict.fromkeys(word for word in words if word))
        return ", ".join(unique[:100]) or None

    def add_vocabulary(self, value: str) -> None:
        value = value.strip()
        if not value:
            return
        with self._lock:
            if value.casefold() not in {item.casefold() for item in self.data.vocabulary}:
                self.data.vocabulary.append(value)
            self.save()

    def remove_vocabulary(self, value: str) -> None:
        with self._lock:
            self.data.vocabulary = [item for item in self.data.vocabulary if item != value]
            self.save()

    def update_vocabulary(self, old_value: str, new_value: str) -> bool:
        new_value = new_value.strip()
        if not new_value:
            return False
        with self._lock:
            duplicate = any(
                item.casefold() == new_value.casefold() and item != old_value
                for item in self.data.vocabulary
            )
            if duplicate:
                return False
            try:
                index = self.data.vocabulary.index(old_value)
            except ValueError:
                return False
            self.data.vocabulary[index] = new_value
            self.save()
            return True

    def set_replacement(self, spoken: str, replacement: str) -> None:
        spoken = spoken.strip()
        if not spoken or not replacement:
            return
        with self._lock:
            self.data.replacements[spoken] = replacement
            self.save()

    def remove_replacement(self, spoken: str) -> None:
        with self._lock:
            self.data.replacements.pop(spoken, None)
            self.save()

    def set_snippet(self, trigger: str, content: str) -> None:
        trigger = self.normalize_trigger(trigger)
        if not trigger or not content:
            return
        with self._lock:
            self.data.snippets[trigger] = content
            self.save()

    def remove_snippet(self, trigger: str) -> None:
        with self._lock:
            self.data.snippets.pop(self.normalize_trigger(trigger), None)
            self.save()

    def update_pair(
        self,
        kind: str,
        old_key: str,
        new_key: str,
        new_value: str,
    ) -> bool:
        if kind not in {"replacements", "snippets"}:
            raise ValueError("Unknown personalization mapping")
        key = self.normalize_trigger(new_key) if kind == "snippets" else new_key.strip()
        old = self.normalize_trigger(old_key) if kind == "snippets" else old_key
        value = str(new_value)
        if not key or not value:
            return False
        with self._lock:
            mapping = getattr(self.data, kind)
            if key != old and key in mapping:
                return False
            if old not in mapping:
                return False
            mapping.pop(old)
            mapping[key] = value
            self.save()
            return True

    def expand_snippet(self, raw: str) -> str | None:
        normalized = self.normalize_trigger(raw).strip(".!?")
        if normalized.startswith("insert "):
            normalized = normalized[7:].strip()
        elif normalized.startswith("snippet "):
            normalized = normalized[8:].strip()
        with self._lock:
            return self.data.snippets.get(normalized)
