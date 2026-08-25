from __future__ import annotations

import queue
import re
import threading
from dataclasses import dataclass


CLEANUP_LEVELS = ("minimal", "smart")
_POLISH_LEVELS = (*CLEANUP_LEVELS, "none", "high")


@dataclass(frozen=True, slots=True)
class CleanupResult:
    text: str
    level: str
    method: str
    fallback: bool = False
    detail: str = ""


class GrammarPolisher:
    """Safe typography cleanup plus explicit selected-text rewrites.

    Ordinary dictation only uses the word-preserving ``minimal`` branch. The
    aggressive rules are reserved for an explicit selection command such as
    "make this concise"; they never run before Smart cleanup.
    """

    HESITATIONS = re.compile(r"(?i)(?<!\w)(?:uh+|um+|erm+|hmm+|ah+)(?!\w)[,;: -]*")
    REPEATED_WORD = re.compile(r"(?i)(?<!\w)\b(\w[\w'-]*)(?:\s+\1\b)+")
    REPEATED_PHRASE = re.compile(
        r"(?i)(?<!\w)\b((?:\w[\w'-]*\s+){1,3}\w[\w'-]*)\s*[,;-]?\s+\1\b"
    )
    CONTRACTIONS = (
        (re.compile(r"(?i)\b(i)\s+am\b"), "I'm"),
        (re.compile(r"(?i)\b(i)\s+have\b"), "I've"),
        (re.compile(r"(?i)\b(i)\s+will\b"), "I'll"),
        (re.compile(r"(?i)\b(i)\s+would\b"), "I'd"),
        (re.compile(r"(?i)\b(can)\s+not\b"), "can't"),
        (re.compile(r"(?i)\b(do)\s+not\b"), "don't"),
        (re.compile(r"(?i)\b(does)\s+not\b"), "doesn't"),
        (re.compile(r"(?i)\b(did)\s+not\b"), "didn't"),
        (re.compile(r"(?i)\b(is)\s+not\b"), "isn't"),
        (re.compile(r"(?i)\b(are)\s+not\b"), "aren't"),
        (re.compile(r"(?i)\b(was)\s+not\b"), "wasn't"),
        (re.compile(r"(?i)\b(were)\s+not\b"), "weren't"),
        (re.compile(r"(?i)\b(will)\s+not\b"), "won't"),
        (re.compile(r"(?i)\b(that)\s+is\b"), "that's"),
        (re.compile(r"(?i)\b(it)\s+is\b"), "it's"),
        (re.compile(r"(?i)\b(there)\s+is\b"), "there's"),
        (re.compile(r"(?i)\b(let)\s+us\b"), "let's"),
    )
    CONCISE_REPLACEMENTS = (
        (re.compile(r"(?i)\bdue to the fact that\b"), "because"),
        (re.compile(r"(?i)\bin order to\b"), "to"),
        (re.compile(r"(?i)\bat this point in time\b"), "now"),
        (re.compile(r"(?i)\ba large number of\b"), "many"),
        (re.compile(r"(?i)\bhas the ability to\b"), "can"),
        (re.compile(r"(?i)\bfor the purpose of\b"), "to"),
    )

    @classmethod
    def polish(
        cls, text: str, level: str, style: str = "default", mid_sentence: bool = False
    ) -> str:
        level = level if level in _POLISH_LEVELS else "minimal"
        if level == "none" or not text:
            return text

        leading = " " if text.startswith(" ") else ""
        trailing = " " if text.endswith(" ") else ""
        value = re.sub(r"[ \t]+", " ", text).strip()

        # Only explicit selected-text rewrites may remove or rewrite words.
        if level == "high":
            value = cls.HESITATIONS.sub("", value)
            value = cls.REPEATED_WORD.sub(r"\1", value)
            for _ in range(2):
                value = cls.REPEATED_PHRASE.sub(r"\1", value)
            for pattern, replacement in cls.CONTRACTIONS:
                value = pattern.sub(replacement, value)
            for pattern, replacement in cls.CONCISE_REPLACEMENTS:
                value = pattern.sub(replacement, value)
            value = re.sub(r"(?i)\b(?:really|very)\s+(?=important\b)", "", value)
            value = re.sub(r"(?i)^I just wanted to\b", "I wanted to", value)
            value = re.sub(r"(?i)^please be advised that\s+", "", value)
            value = re.sub(r"(?i)^I am writing to let you know that\s+", "", value)

        value = re.sub(r"(?i)(?<![\w'])\bi\b", "I", value)
        value = re.sub(r"\s+([,.;:!?])", r"\1", value)
        value = re.sub(r"([,.;:!?])(?=[A-Za-z])", r"\1 ", value)
        value = re.sub(r"[ \t]*\n[ \t]*", "\n", value).strip()
        value = re.sub(r"^[,;: -]+", "", value)
        value = re.sub(r"\n[,;: -]+", "\n", value)
        value = cls._sentence_case(value, capitalize_first=not mid_sentence)

        if style == "very_casual" and value:
            value = value[0].lower() + value[1:] if value[0].isalpha() else value
        return leading + value + trailing

    @staticmethod
    def _sentence_case(text: str, capitalize_first: bool = True) -> str:
        characters = list(text)
        capitalize_next = capitalize_first
        for index, character in enumerate(characters):
            if capitalize_next and character.isalpha():
                characters[index] = character.upper()
                capitalize_next = False
            elif character in ".!?\n":
                capitalize_next = True
        return "".join(characters)

    @classmethod
    def rewrite_selection(cls, text: str, action: str) -> str:
        if action == "rewrite_bullets":
            chunks = [part.strip(" ,.;") for part in re.split(r"[,;\n]|\band\b", text, flags=re.I)]
            items = [item for item in chunks if item]
            return "\n".join(f"• {cls._sentence_case(item)}" for item in items) if items else text
        style = "formal" if action == "rewrite_professional" else "concise"
        return cls.polish(text, "high", style)


class CleanupService:
    """Run exactly one ordinary cleanup owner: Minimal rules or Smart AI."""

    def __init__(self, semantic_formatter, timeout_seconds: float = 1.8):
        self.semantic_formatter = semantic_formatter
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self._semantic_lock = threading.Lock()

    def clean(
        self,
        text: str,
        level: str,
        style: str,
        category: str,
        mid_sentence: bool = False,
        original_text: str | None = None,
    ) -> CleanupResult:
        backend = getattr(self.semantic_formatter, "display_name", "AI formatter")
        if level == "none":
            return CleanupResult(text, level, "safe-verbatim")
        level = level if level in CLEANUP_LEVELS else "minimal"
        local = GrammarPolisher.polish(text, "minimal", style, mid_sentence)
        if level == "minimal":
            return CleanupResult(local, level, "local-minimal")

        if not self.semantic_formatter.available:
            detail = getattr(self.semantic_formatter, "error", "") or f"{backend} is unavailable"
            return CleanupResult(local, level, "safe-local", True, detail)
        if not self._semantic_lock.acquire(blocking=False):
            return CleanupResult(
                local,
                level,
                "safe-busy",
                True,
                f"{backend} is still formatting the previous dictation",
            )

        result_queue: queue.Queue[tuple[bool, str]] = queue.Queue(maxsize=1)

        def run() -> None:
            try:
                result = (
                    True,
                    self.semantic_formatter.format(
                        text,
                        category,
                        "smart",
                        style,
                        original_text=original_text or text,
                    ),
                )
            except Exception as exc:
                result = (False, str(exc))
            finally:
                self._semantic_lock.release()
            result_queue.put(result)

        threading.Thread(target=run, name="smart-cleanup", daemon=True).start()
        try:
            success, value = result_queue.get(timeout=self.timeout_seconds)
        except queue.Empty:
            return CleanupResult(
                local,
                level,
                "safe-timeout",
                True,
                f"{backend} exceeded the {self.timeout_seconds:g}-second formatting limit",
            )
        if not success or not value.strip():
            return CleanupResult(
                local,
                level,
                "safe-rejected",
                True,
                value.strip() or f"{backend} returned no text",
            )
        prefix = " " if text.startswith(" ") else ""
        suffix = " " if text.endswith(" ") else ""
        return CleanupResult(prefix + value.strip() + suffix, level, "ai-smart")
