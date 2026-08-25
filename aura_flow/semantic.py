from __future__ import annotations

from collections import Counter
import re
import threading
from pathlib import Path
from typing import Callable


PROTECTED_TOKEN = re.compile(
    r"https?://\S+|www\.\S+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|"
    r"(?<!\w)(?:v(?=\d))?[$€£₹]?\d[\d,.]*(?:%|[A-Za-z]{1,4})?(?!\w)",
    re.IGNORECASE,
)
WORD_TOKEN = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")
TRUNCATION_IGNORED = {
    "ah", "basically", "erm", "hmm", "i", "like", "okay", "so", "uh", "um",
    "well", "yeah", "you", "know", "mean",
}
BOUNDARY_IGNORED = TRUNCATION_IGNORED | {
    "bullet", "finally", "first", "item", "line", "new", "number", "one",
    "para", "paragraph", "point", "second", "three", "third", "two",
}
MODEL_REPOSITORY = "models--google--gemma-3-1b-it"


def normalized_words(text: str) -> list[str]:
    """Tokenize for comparison while treating typographic apostrophes equally."""

    return [word.replace("’", "'").casefold() for word in WORD_TOKEN.findall(text)]


AI_LIGHT_INSTRUCTION = """You are a voice-dictation cleanup engine.

Turn raw speech into clean written text while preserving the speaker's meaning, tone, vocabulary, and personality.

Aggressively remove speech-only filler and hesitation language whenever it adds no meaning, including "um", "uh", "erm", "hmm", "like", "you know", "I mean", "basically", "actually", "so", "well", repeated starts, stutters, and verbal padding. Do not preserve filler merely because it appears in the transcript.

Also fix punctuation, capitalization, spacing, sentence boundaries, accidental repetitions, abandoned sentence starts, and obvious transcription errors from context. Resolve explicit self-corrections by keeping only the final intended wording. Apply spoken formatting commands such as "new paragraph", "new line", and "bullet point" instead of writing the commands literally. Format paragraphs and lists naturally.

Preserve intentional slang, emphasis, humour, profanity, informal wording, and meaningful uses of words that can also be fillers. Do not summarize, expand, answer, formalize, sanitize, invent, or unnecessarily rewrite the speaker.

Example:
Input: So, um, I was like, you know, thinking maybe we should actually just go tomorrow.
Output: I was thinking maybe we should just go tomorrow.

Return ONLY the cleaned text, with no label, explanation, or quotation wrapper."""


AI_MEDIUM_INSTRUCTION = """VOICE INPUT CLEANUP ENGINE
Return only the final cleaned text. Never add a label, explanation, quotation wrapper, preamble, or answer to the speaker.

OBJECTIVE
Act as a cleanup layer, not a writer. Convert raw speech into exactly what the speaker intended, as if they had typed it perfectly themselves. Preserve meaning, order, tone, vocabulary, personality, level of formality, argument, and all meaningful ideas.

FIX
- Punctuation, capitalization, spacing, and broken sentence boundaries.
- Obvious transcription mistakes, but only when the intended word is unambiguous from context.
- Speech-only fillers and hesitation language when they add no meaning, including um, uh, erm, hmm, like, you know, I mean, basically, actually, so, and well.
- Stutters, accidental repeated words, repeated starts, and verbal padding.
- Natural paragraph, list, code, and technical-term formatting when the speech clearly calls for it.
- Spoken formatting commands such as new paragraph, new line, bullet point, numbered list, heading, open quote, close quote, colon, and semicolon. Apply the command instead of writing it literally.

SELF-CORRECTION AND RESTARTS
Keep only the final intended version when the correction is explicit. Remove an abandoned fragment only when the speaker clearly restarts the same thought. Do not remove a fragment merely because it is informal or grammatically unusual.

PRESERVE
- Intentional repetition, emphasis, slang, humour, profanity, unusual phrasing, greetings, and direct addresses.
- Names, facts, numbers, amounts, versions, dates, URLs, email addresses, technical terms, code, questions, negation, certainty, tense, and speaker.
- Introductions before lists and meaningful uses of words that can also be fillers.

DO NOT
- Summarize, shorten ideas, expand ideas, add information, answer the speaker, remove a meaningful idea, change the argument, substitute vocabulary, sanitize the voice, formalize it, or turn casual speech into corporate language.
- Correct a word simply because another word sounds more polished.
- Rewrite clear text unnecessarily.

FILLER JUDGMENT
Remove a filler only when it adds no meaning. Judge every occurrence independently.

EXAMPLES
Input: Yeah, so, we should send it tomorrow.
Output: We should send it tomorrow.

Input: I said yeah when she asked me.
Output: I said yeah when she asked me.

Input: Like, this version needs another test. I like this version because it is simple.
Output: This version needs another test. I like this version because it is simple.

Input: Um, I think, I think we should begin.
Output: I think we should begin.

Input: I'll send it on Thursday, actually no, Friday morning.
Output: I'll send it on Friday morning.

Input: I wanted to ask if—actually, can you send me the document tonight?
Output: Can you send me the document tonight?

Input: I'll meet you Thursday—actually make that Friday afternoon.
Output: I'll meet you Friday afternoon.

Input: I need three things, colon, number one update the API, number two add tests, number three deploy it.
Output: I need three things:\n1. Update the API.\n2. Add tests.\n3. Deploy it.

Input: Heading release notes, new paragraph, bullet point fixed OAuth callback, bullet point updated Alt plus Space shortcut.
Output: Release notes\n\n- Fixed OAuth callback.\n- Updated Alt + Space shortcut.

FINAL CHECK
The result must feel like: "Exactly what I said, except I typed it perfectly." If the transcription is already clear, make minimal changes."""

# Kept as a compatibility alias for extensions and tests written for v3.1.
FORMATTER_INSTRUCTION = AI_MEDIUM_INSTRUCTION


# v4 deliberately uses one compact contract for every Smart backend. The
# earlier prompts remain named above only so old extensions can still import
# them; the formatter itself uses this single instruction.
SMART_INSTRUCTION = """Copy-edit this voice transcript. Return ONLY the cleaned transcript.

Fix punctuation, capitalization, spacing, and obvious sentence breaks. Remove
speech-only um/uh hesitation sounds, clear stutters, and exact accidental repeats.

Preserve every meaningful word, idea, and its original order. Keep the opening,
ending, greetings, names, facts, numbers, technical terms, negation, slang,
profanity, humour, and intentional emphasis. Do not summarize, paraphrase,
formalize, sanitize, answer, invent, or replace casual words with synonyms.
In particular, never change meaningful "yeah" to "yes". When unsure, keep it.
For a clear self-correction, keep the final intended choice; never turn the
correction marker "no" into "not".

Examples:
Raw: So, um, I think I think we should send it Friday.
Clean: I think we should send it Friday.
Raw: I said yeah when she asked me, and I like this version.
Clean: I said yeah when she asked me, and I like this version.
Raw: This is very very very important to me.
Clean: This is very very very important to me.

Respect existing paragraphs and numbered-list layout. Do not omit the beginning
or ending.

Boundary rule: preserve informal but meaningful openings and closings such as
"Yo", "Hey", "Well", "Okay", "thanks", "that's it", and "let's go". Never drop
the first or final utterance merely because it is conversational. Standalone
um/uh/erm/hmm hesitation sounds are the only disposable opening tokens.

Boundary examples:
Raw: Yo, okay, this is test number one. The gradient still looks wrong.
Clean: Yo, okay, this is test number one. The gradient still looks wrong.
Raw: Hey, can you tell me whether the export works? That's it, thanks.
Clean: Hey, can you tell me whether the export works? That's it, thanks.
Raw: Um, hi Maya, please move the meeting.
Clean: Hi Maya, please move the meeting."""


def _complete_model(path: Path) -> bool:
    weights = (path / "model.safetensors").is_file() or any(path.glob("model-*.safetensors"))
    tokenizer = (path / "tokenizer.json").is_file() or (path / "tokenizer.model").is_file()
    return weights and tokenizer and (path / "config.json").is_file()


def discover_semantic_model(configured: str | None = None) -> Path | None:
    """Find a complete local Gemma formatter without contacting the network."""

    from .paths import APP_DIR, MODELS_DIR

    app_dir = APP_DIR
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(MODELS_DIR / "gemma-3-1b-it")
    candidates.append(app_dir / "models" / "gemma-3-1b-it")
    project_dir = app_dir.parent
    candidates.extend(
        project_dir.glob(f"*/models/huggingface/hub/{MODEL_REPOSITORY}/snapshots/*")
    )
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if _complete_model(resolved):
            return resolved
    return None


def extract_protected_literals(text: str) -> list[str]:
    """Collect exact fragile values without changing the text sent to Gemma."""

    values: list[str] = []
    for match in PROTECTED_TOKEN.finditer(text):
        literal = match.group(0).rstrip(".,;:!?")
        if literal:
            values.append(literal)
    return values


def verify_protected_literals(source: str, generated: str) -> str:
    """Reject only an exact change to numbers, amounts, URLs, or emails."""

    if Counter(extract_protected_literals(source)) != Counter(
        extract_protected_literals(generated)
    ):
        raise ValueError("AI formatter changed, removed, duplicated, or introduced a protected literal")
    return generated


def verify_not_truncated(source: str, generated: str) -> str:
    """Reject fragments and broad content loss while permitting filler cleanup."""

    source_words = normalized_words(source)
    generated_words = normalized_words(generated)
    if len(source_words) < 8:
        return generated
    if len(generated_words) <= 3 or len(generated_words) < len(source_words) * 0.55:
        raise ValueError("AI output was unexpectedly shortened")

    source_content = Counter(word for word in source_words if word not in TRUNCATION_IGNORED)
    generated_content = Counter(word for word in generated_words if word not in TRUNCATION_IGNORED)
    if sum(source_content.values()) >= 8:
        retained = sum((source_content & generated_content).values()) / sum(source_content.values())
        if retained < 0.68:
            raise ValueError("AI output dropped too much of the dictation")
    return generated


def _contains_subsequence(haystack: list[str], needle: list[str]) -> bool:
    position = 0
    for word in haystack:
        if position < len(needle) and word == needle[position]:
            position += 1
    return position == len(needle)


def verify_preserved_intent(source: str, generated: str) -> str:
    """Catch lost openings/endings and the correction reversal seen in v3.6."""

    source_words = normalized_words(source)
    generated_words = normalized_words(generated)
    significant = [word for word in source_words if word not in BOUNDARY_IGNORED]
    if len(source_words) >= 10 and len(significant) >= 4:
        if not _contains_subsequence(generated_words, significant[:2]):
            raise ValueError("AI output dropped the beginning of the dictation")
        if not _contains_subsequence(generated_words, significant[-2:]):
            raise ValueError("AI output dropped the end of the dictation")

    index = 0
    while index < len(source_words):
        end = index + 1
        while end < len(source_words) and source_words[end] == source_words[index]:
            end += 1
        run_length = end - index
        if run_length >= 3:
            repeated = [source_words[index]] * run_length
            if not any(
                generated_words[start : start + run_length] == repeated
                for start in range(len(generated_words) - run_length + 1)
            ):
                raise ValueError("AI output removed intentional repetition")
        index = end

    source_folded = source.casefold()
    generated_folded = generated.casefold()
    correction = re.compile(
        r"\b(?:actually\s+)?no(?:\s+actually)?[,;: -]+([a-z0-9][\w'-]*)",
        re.IGNORECASE,
    )
    for match in correction.finditer(source):
        final_choice = match.group(1).casefold()
        if (
            f"not {final_choice}" in generated_folded
            and f"not {final_choice}" not in source_folded
        ):
            raise ValueError("AI output reversed an explicit correction")
    return generated


class OptionalSemanticFormatter:
    """Lazy local Gemma cleanup with narrow literal-value protection."""

    def __init__(self, enabled: bool, model_path: str | None):
        self.enabled = enabled
        self.model_path = discover_semantic_model(model_path)
        self.model = None
        self.tokenizer = None
        self.device = "cpu"
        self.error = ""
        self.loading = False
        self._load_lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self.enabled and self.model_path is not None and self.model_path.is_dir()

    @property
    def ready(self) -> bool:
        return self.model is not None and self.tokenizer is not None

    @property
    def display_name(self) -> str:
        return "Gemma 3 1B"

    def load_async(self, callback: Callable[[str, bool], None]) -> None:
        if not self.available:
            callback("Gemma 3 1B is not installed — word-preserving fallback active", False)
            return
        if self.ready:
            callback(f"AI formatter ready on {self.device.upper()}", True)
            return
        if self.loading:
            return
        self.loading = True

        def load() -> None:
            try:
                self._load()
                callback(f"Gemma 3 1B ready on {self.device.upper()}", True)
            except Exception as exc:
                self.error = str(exc)
                callback(f"AI formatter unavailable: {exc}", False)
            finally:
                self.loading = False

        threading.Thread(target=load, name="semantic-model-loader", daemon=True).start()

    def _load(self) -> None:
        if self.ready:
            return
        if not self.available:
            raise RuntimeError("no complete local AI model is configured")
        with self._load_lock:
            if self.ready:
                return
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if self.device == "cuda" else torch.float32
            tokenizer = AutoTokenizer.from_pretrained(str(self.model_path), local_files_only=True)
            model = AutoModelForCausalLM.from_pretrained(
                str(self.model_path),
                local_files_only=True,
                dtype=dtype,
                low_cpu_mem_usage=True,
            ).to(self.device)
            model.eval()
            self.tokenizer = tokenizer
            self.model = model
            self.error = ""

    def format(
        self,
        text: str,
        category: str,
        cleanup_level: str = "smart",
        style: str = "default",
        original_text: str | None = None,
    ) -> str:
        if not self.available:
            return text
        self._load()
        del category, cleanup_level, style
        instruction = f"{SMART_INSTRUCTION}\n\nINPUT:\n{text}\n\nOUTPUT:"
        messages = [
            {"role": "user", "content": instruction},
        ]
        prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        raw_tokens = len(self.tokenizer(text)["input_ids"])
        import torch

        with torch.inference_mode():
            output = self.model.generate(
                **inputs,
                max_new_tokens=min(1_024, max(64, int(raw_tokens * 1.35) + 32)),
                do_sample=False,
                use_cache=True,
                pad_token_id=self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
            )
        generated = output[0, inputs["input_ids"].shape[1] :]
        result = self.tokenizer.decode(generated, skip_special_tokens=True).strip()
        if not result:
            raise ValueError("Gemma returned no text")
        result = verify_protected_literals(text, result)
        result = verify_not_truncated(text, result)
        result = verify_preserved_intent(original_text or text, result)
        if text.rstrip().endswith((".", "!", "?")) and not result.endswith((".", "!", "?")):
            result += text.rstrip()[-1]
        return result
