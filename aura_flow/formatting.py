from __future__ import annotations

import re
from dataclasses import dataclass


SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")
MULTISPACE = re.compile(r"[ \t]{2,}")
FRAGILE_LITERAL = re.compile(
    r"https?://\S+|www\.\S+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
    re.IGNORECASE,
)
COMMANDS = (
    (re.compile(r"(?i)\b(?:new paragraph|new para)\b"), "\n\n"),
    (re.compile(r"(?i)\b(?:new line|next line|line break)\b"), "\n"),
    (re.compile(r"(?i)\bquestion mark\b"), "?"),
    (re.compile(r"(?i)\bexclamation (?:point|mark)\b"), "!"),
    (re.compile(r"(?i)\bfull stop\b|\bperiod\b"), "."),
    (re.compile(r"(?i)\bcomma\b"), ","),
    (re.compile(r"(?i)\bsemicolon\b"), ";"),
    (re.compile(r"(?i)\bcolon\b"), ":"),
    (re.compile(r"(?i)\bopen (?:parenthesis|paren)\b"), "("),
    (re.compile(r"(?i)\bclose (?:parenthesis|paren)\b"), ")"),
)
DAY_CHOICE_CORRECTION = re.compile(
    r"(?ix)\b(?P<old>"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow"
    r")\b\s*[,.;:—-]?\s+(?:actually\s+)?no(?:\s+actually)?\s*[,;:—-]?\s*"
    r"(?P<new>"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow"
    r")(?:\s+(?P<daypart>morning|afternoon|evening|night))?\b"
)

VOICE_ACTIONS = {
    "undo that": "undo",
    "undo": "undo",
    "paste last transcript": "paste_last",
    "paste last dictation": "paste_last",
    "copy last transcript": "copy_last",
    "copy last dictation": "copy_last",
    "undo formatting": "undo_cleanup",
    "restore original dictation": "undo_cleanup",
    "make this professional": "rewrite_professional",
    "make this formal": "rewrite_professional",
    "make this concise": "rewrite_concise",
    "shorten this": "rewrite_concise",
    "turn this into bullets": "rewrite_bullets",
    "make this a bullet list": "rewrite_bullets",
}


@dataclass(frozen=True, slots=True)
class FormatContext:
    app_category: str = "other"
    before_cursor: str = ""
    after_cursor: str = ""
    selected_text: str = ""
    style: str = "default"
    cleanup_level: str = "minimal"


@dataclass(frozen=True, slots=True)
class FormatResult:
    text: str
    press_enter: bool = False
    used_semantic_formatter: bool = False
    action: str | None = None
    style: str = "default"
    snippet_trigger: str | None = None


class Dictionary:
    def __init__(self, replacements: dict[str, str] | None = None):
        self.replacements = replacements or {}

    def apply(self, text: str) -> str:
        for wrong, correct in sorted(self.replacements.items(), key=lambda pair: -len(pair[0])):
            text = re.sub(rf"(?i)(?<!\w){re.escape(wrong)}(?!\w)", lambda _: correct, text)
        return text


class DeterministicFormatter:
    """Recognize explicit controls without making language-editing decisions.

    Ordinary wording is deliberately left for the single semantic formatting
    pass.  This layer owns only voice actions, literal snippets, saved
    dictionary replacements, spoken punctuation and unmistakable structure.
    """

    def __init__(self, dictionary: Dictionary | None = None, snippets: dict[str, str] | None = None):
        self.dictionary = dictionary or Dictionary()
        self.snippets = snippets or {}

    def refresh(self, replacements: dict[str, str], snippets: dict[str, str]) -> None:
        self.dictionary = Dictionary(dict(replacements))
        self.snippets = dict(snippets)

    def format(self, raw: str, context: FormatContext | None = None) -> FormatResult:
        context = context or FormatContext()
        text = raw.strip()
        normalized = re.sub(r"\s+", " ", text.lower()).strip(" .!?")
        if normalized in VOICE_ACTIONS:
            return FormatResult("", action=VOICE_ACTIONS[normalized], style=context.style)

        text, snippet_trigger, literal_snippet, snippet_value = self._expand_snippets(text)
        if literal_snippet:
            # Snippets are deliberately literal.  Running URLs, signatures or
            # code fragments through sentence casing/punctuation corrupts the
            # exact text the user saved.
            return FormatResult(
                text=text,
                style=context.style,
                snippet_trigger=snippet_trigger,
            )

        style_override, text = self._style_override(text, context.style)
        press_enter = bool(re.search(r"(?i)(?:[.!?]\s*)?\bpress enter\b[.!?]?\s*$", text))
        if press_enter:
            text = re.sub(r"(?i)(?:\s*[.!?])?\s*\bpress enter\b[.!?]?\s*$", "", text).strip()

        if context.cleanup_level != "none":
            text = self._apply_explicit_restart(text)
            text = self._apply_explicit_day_correction(text)
        for pattern, replacement in COMMANDS:
            text = pattern.sub(replacement, text)
        text = self.dictionary.apply(text)
        fragile_literals: list[str] = []

        def protect_literal(match: re.Match[str]) -> str:
            fragile_literals.append(match.group(0))
            return f"AURAFLOWLITERAL{len(fragile_literals) - 1}TOKEN"

        text = FRAGILE_LITERAL.sub(protect_literal, text)
        text = SPACE_BEFORE_PUNCT.sub(r"\1", text)
        text = re.sub(r"([,.;:!?])(?=[A-Za-z])", r"\1 ", text)
        text = MULTISPACE.sub(" ", text)
        text = re.sub(r" *\n *", "\n", text).strip()
        text = self._mark_explicit_list(text)
        styled_context = FormatContext(
            app_category=context.app_category,
            before_cursor=context.before_cursor,
            after_cursor=context.after_cursor,
            selected_text=context.selected_text,
            style=style_override,
            cleanup_level=context.cleanup_level,
        )
        text = self._fit_cursor(text, styled_context)
        text = self._apply_style(text, style_override)
        for index, literal in enumerate(fragile_literals):
            text = text.replace(f"AURAFLOWLITERAL{index}TOKEN", literal)
        if snippet_value:
            text = text.replace("__AURA_FLOW_SNIPPET__", snippet_value)
        return FormatResult(
            text=text,
            press_enter=press_enter,
            style=style_override,
            snippet_trigger=snippet_trigger,
        )

    def _expand_snippets(self, raw: str) -> tuple[str, str | None, bool, str | None]:
        normalized = re.sub(r"\s+", " ", raw.lower()).strip(" .!?")
        for prefix in ("insert ", "snippet "):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):].strip()
                break
        snippet = self.snippets.get(normalized)
        if snippet is not None:
            return snippet, normalized, True, None

        # Triggers also work naturally inside longer dictations. Prefer the
        # longest trigger so "work email address" wins over "email address".
        for trigger, expansion in sorted(self.snippets.items(), key=lambda pair: -len(pair[0])):
            pattern = re.compile(
                rf"(?i)(?<!\w)(?:(?:insert|snippet)\s+)?{re.escape(trigger)}(?!\w)"
            )
            if pattern.search(raw):
                protected = pattern.sub("__AURA_FLOW_SNIPPET__", raw, count=1)
                return protected, trigger, False, expansion
        return raw, None, False, None

    @staticmethod
    def _style_override(text: str, default: str) -> tuple[str, str]:
        match = re.match(r"(?i)^(formal|casual|very casual|excited)\s+(?:style|mode)[:,]?\s+(.+)$", text)
        if not match:
            return default, text
        return match.group(1).lower().replace(" ", "_"), match.group(2).strip()

    @staticmethod
    def _apply_explicit_restart(text: str) -> str:
        explicit = re.split(r"(?i)\b(?:scratch that|never mind|start over)\b[,;: -]*", text)
        if len(explicit) > 1 and explicit[-1].strip():
            return explicit[-1].strip()
        return text

    @staticmethod
    def _apply_explicit_day_correction(text: str) -> str:
        """Resolve only unmistakable day choices; leave all other wording alone."""

        def keep_final_choice(match: re.Match[str]) -> str:
            replacement = match.group("new")
            if match.group("daypart"):
                replacement += f" {match.group('daypart')}"
            return replacement

        return DAY_CHOICE_CORRECTION.sub(keep_final_choice, text)

    @staticmethod
    def _mark_explicit_list(text: str) -> str:
        marker = re.compile(
            r"(?ix)(?<!\w)(?:"
            r"number\s+(?P<number>one|two|three|four|five|six|seven|eight|nine|ten|\d{1,2})"
            r"|(?P<ordinal>first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|finally)"
            r"|(?P<plain>one|two|three|four|five|six|seven|eight|nine|ten|\d{1,2})\s*[,.:)](?!\d)"
            r")\s*(?:(?:item|thing)\s+)?(?:is(?:\s+that)?\s+)?"
        )
        matches = list(marker.finditer(text))
        if len(matches) < 2:
            return text
        if any(
            "\n\n" in text[left.end():right.start()]
            for left, right in zip(matches, matches[1:])
        ):
            return text

        order = {
            "one": 1, "first": 1, "two": 2, "second": 2,
            "three": 3, "third": 3, "four": 4, "fourth": 4,
            "five": 5, "fifth": 5, "six": 6, "sixth": 6,
            "seven": 7, "seventh": 7, "eight": 8, "eighth": 8,
            "nine": 9, "ninth": 9, "ten": 10, "tenth": 10,
            "finally": 99,
        }

        ranks: list[int] = []
        for match in matches:
            token = next(value for value in match.groups() if value is not None).casefold()
            rank = int(token) if token.isdigit() else order[token]
            if rank == 99 and ranks:
                rank = ranks[-1] + 1
            ranks.append(rank)
        # A list must begin at one and proceed sequentially. This prevents
        # versions, test numbers, and stray numeric phrases from becoming lists.
        if ranks[0] != 1 or any(right != left + 1 for left, right in zip(ranks, ranks[1:])):
            return text

        prefix = text[:matches[0].start()].strip(" ,")
        items: list[str] = []
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            value = text[start:end].strip(" ,.;")
            if value:
                items.append(value[0].upper() + value[1:])
        if len(items) < 2:
            return text
        formatted = "\n".join(f"{index}. {value}" for index, value in enumerate(items, 1))
        if not prefix:
            return formatted
        separator = "\n" if prefix.endswith((".", "!", "?", ":")) else ":\n"
        return prefix + separator + formatted

    @staticmethod
    def _fit_cursor(text: str, context: FormatContext) -> str:
        if not text:
            return text
        mid_sentence = bool(
            context.before_cursor[-1:].isalnum()
            and context.after_cursor[:1].isalnum()
        )
        if mid_sentence and text[0].isalpha():
            text = text[0].lower() + text[1:]
        elif not mid_sentence and text[0].isalpha():
            text = text[0].upper() + text[1:]

        if context.style in {"casual", "very_casual"}:
            if len(text.split()) <= 30 or context.style == "very_casual":
                text = text.removesuffix(".")
        elif "\n" not in text and text[-1] not in ".!?" and not context.after_cursor:
            text += "."

        prefix = " " if mid_sentence and not text.startswith((" ", "\n")) else ""
        suffix = " " if context.after_cursor[:1].isalnum() and not text.endswith((" ", "\n")) else ""
        return prefix + text + suffix

    @staticmethod
    def _apply_style(text: str, style: str) -> str:
        if not text:
            return text
        if style == "very_casual":
            return text[0].lower() + text[1:] if text[0].isalpha() else text
        if style == "excited" and text[-1] not in "!?\n":
            return text.removesuffix(".") + "!"
        return text
