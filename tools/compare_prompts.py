from __future__ import annotations

from dataclasses import dataclass
import re
import time

from aura_flow.config import AppConfig
from aura_flow.formatting import DeterministicFormatter, FormatContext
from aura_flow.semantic import (
    OptionalSemanticFormatter,
    SMART_INSTRUCTION,
    verify_not_truncated,
    verify_preserved_intent,
    verify_protected_literals,
)


PROMPTS = {
    "current": SMART_INSTRUCTION,
    "priority_examples": """You are a copy editor for voice transcripts. Return ONLY the cleaned transcript.

PRIORITY 1 — PRESERVE: Keep every intended idea in its original order and voice.
Keep the opening, ending, greetings, names, facts, numbers, technical terms,
questions, negation, slang, profanity, humour, and intentional emphasis. Never
summarize, paraphrase, answer, formalize, sanitize, or add information.

PRIORITY 2 — CLEAN: Fix punctuation, capitalization, spacing, and sentence
boundaries. Remove only meaningless hesitation sounds, clear stutters, and exact
accidental repeats. Keep uncertain words. Respect existing paragraphs and lists.

Examples:
Raw: Um, I think I think we should send it Friday.
Clean: I think we should send it Friday.
Raw: I said yeah when she asked me, and I like this version.
Clean: I said yeah when she asked me, and I like this version.
Raw: This is very very very important to me.
Clean: This is very very very important to me.

Before returning, confirm internally that no idea, opening, ending, or meaningful
repetition was lost. If unsure, keep the original wording.""",
    "strict_edits": """Clean this voice transcript and return only the final text.

You may: fix punctuation, capitalization, spacing, and obvious sentence breaks;
remove um/uh hesitation sounds, stutters, and exact accidental word repeats.

You may not: summarize, paraphrase, shorten ideas, change vocabulary or tone,
answer the speaker, add facts, remove the beginning or ending, or alter names,
numbers, technical terms, negation, slang, profanity, or intentional repetition.
Keep greetings, list introductions, existing paragraph/list structure, and every
meaningful idea in the same order. When uncertain, preserve the words exactly.""",
    "balanced_examples": """Copy-edit this voice transcript. Return ONLY the cleaned transcript.

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
or ending.""",
    "hard_rules": """Copy-edit this voice transcript. Return ONLY the cleaned transcript.

Apply these exact cleanup rules:
1. Delete standalone hesitation sounds: um, uh, erm, and hmm.
2. Collapse an accidental word repeated exactly twice, such as "I think I think".
3. NEVER collapse a word repeated three or more times; that is intentional emphasis.
4. Fix punctuation, capitalization, spacing, and obvious sentence boundaries.

Preserve every meaningful word and idea in its original order. Keep the opening,
ending, greetings, names, facts, numbers, technical terms, negation, slang,
profanity, humour, and voice. Never change meaningful "yeah" to "yes". Do not
summarize, paraphrase, formalize, sanitize, answer, invent, or replace vocabulary.
When unsure, keep the original words.

Examples:
Raw: So, um, I think I think we should send it Friday.
Clean: So, I think we should send it Friday.
Raw: I said yeah when she asked me, and I like this version.
Clean: I said yeah when she asked me, and I like this version.
Raw: This is very very very important to me.
Clean: This is very very very important to me.

Respect existing paragraphs and numbered-list layout. Do not omit the beginning
or ending.""",
}


@dataclass(frozen=True)
class Case:
    label: str
    source: str
    required: tuple[str, ...]
    forbidden: tuple[str, ...] = ()


CASES = (
    Case(
        "filler_and_repeat",
        "So, um, I think I think we should actually just send the report tomorrow.",
        ("I think", "send the report", "tomorrow"),
        ("um", "I think I think"),
    ),
    Case(
        "meaningful_like_and_yeah",
        "I said yeah when she asked me, and I like this version because it is simple.",
        ("said yeah", "I like this version", "because it is simple"),
    ),
    Case(
        "opening_list_correction_ending",
        "Hi, this is Yapper. You might be wondering what all I can do. Well, number one, "
        "I capture everything you say. Number two, I clean up the text naturally. Number "
        "three, I use local AI or an API. It launches Thursday, no actually Friday morning. "
        "It is pretty damn useful and I hope you like it. Thank you.",
        ("Hi, this is Yapper", "1.", "2.", "3.", "Friday morning", "hope you like it", "Thank you"),
        ("Thursday", "not Friday"),
    ),
    Case(
        "intentional_repetition",
        "Um, this can do very very very smart things, but yeah, I want that emphasis to stay.",
        ("very very very", "emphasis to stay"),
        ("Um",),
    ),
    Case(
        "protected_values",
        "Email maya@example.com about version v3.7 and the ₹2,500 budget on Friday.",
        ("maya@example.com", "v3.7", "₹2,500", "Friday"),
    ),
    Case(
        "already_clean",
        "The launch plan is ready, and the design feels right.",
        ("launch plan is ready", "design feels right"),
    ),
)


def generate(formatter: OptionalSemanticFormatter, prompt: str, text: str) -> str:
    messages = [{"role": "user", "content": f"{prompt}\n\nINPUT:\n{text}\n\nOUTPUT:"}]
    rendered = formatter.tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = formatter.tokenizer(rendered, return_tensors="pt").to(formatter.device)
    raw_tokens = len(formatter.tokenizer(text)["input_ids"])
    import torch

    with torch.inference_mode():
        output = formatter.model.generate(
            **inputs,
            max_new_tokens=min(1_024, max(64, int(raw_tokens * 1.35) + 32)),
            do_sample=False,
            use_cache=True,
            pad_token_id=formatter.tokenizer.pad_token_id or formatter.tokenizer.eos_token_id,
        )
    generated = output[0, inputs["input_ids"].shape[1] :]
    return formatter.tokenizer.decode(generated, skip_special_tokens=True).strip()


def score(case: Case, prepared: str, result: str) -> tuple[float, str]:
    try:
        verify_protected_literals(prepared, result)
        verify_not_truncated(prepared, result)
        verify_preserved_intent(case.source, result)
    except ValueError as exc:
        return 0.0, f"unsafe: {exc}"

    folded = result.casefold()
    required = sum(phrase.casefold() in folded for phrase in case.required)
    forbidden = sum(phrase.casefold() not in folded for phrase in case.forbidden)
    required_score = 3.0 * required / max(1, len(case.required))
    forbidden_score = 2.0 * forbidden / max(1, len(case.forbidden)) if case.forbidden else 2.0
    source_words = set(re.findall(r"[a-z0-9]+", prepared.casefold()))
    result_words = set(re.findall(r"[a-z0-9]+", folded))
    invented = len(result_words - source_words)
    invention_score = max(0.0, 1.0 - invented * 0.2)
    return 4.0 + required_score + forbidden_score + invention_score, "accepted"


def main() -> int:
    config = AppConfig.load()
    formatter = OptionalSemanticFormatter(True, config.semantic_model_path)
    if not formatter.available:
        print(formatter.error or "Local formatter unavailable")
        return 1
    started = time.perf_counter()
    formatter._load()
    print(f"MODEL READY {time.perf_counter() - started:.2f}s")
    controls = DeterministicFormatter()
    totals = {name: 0.0 for name in PROMPTS}

    for prompt_name, prompt in PROMPTS.items():
        print(f"\n========== {prompt_name} ({len(prompt)} chars) ==========")
        for case in CASES:
            prepared = controls.format(
                case.source, FormatContext(cleanup_level="smart")
            ).text
            case_started = time.perf_counter()
            result = generate(formatter, prompt, prepared)
            points, verdict = score(case, prepared, result)
            totals[prompt_name] += points
            elapsed = time.perf_counter() - case_started
            print(f"\n[{case.label}] {points:.2f}/10 · {verdict} · {elapsed:.2f}s")
            print(result.replace("\n", "\\n"))

    maximum = len(CASES) * 10
    print("\n========== TOTALS ==========")
    for name, total in sorted(totals.items(), key=lambda item: item[1], reverse=True):
        print(f"{name}: {total:.2f}/{maximum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
