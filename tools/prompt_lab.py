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


@dataclass(frozen=True)
class Case:
    group: str
    label: str
    source: str
    required: tuple[str, ...]
    forbidden: tuple[str, ...] = ()


CASES = (
    # Real dictations from the app's history.
    Case(
        "real",
        "yapper_feature_pitch",
        "Hi, this is Yapper. You might be wondering what all I can do. Well, number one, "
        "I can capture everything you say even if you pause repeat repeat a word. Number two, "
        "I can clean up text and format it naturally. Number three, I can either use your local "
        "AI or your API models and it's gonna launch on Thursday no actually Friday morning so "
        "yeah new para so yeah it's pretty damn useful and I hope you like it because I made it "
        "in one afternoon let's go.",
        ("Hi, this is Yapper", "1.", "2.", "3.", "Friday morning", "pretty damn useful", "one afternoon", "let's go"),
        ("Thursday", "not Friday", "repeat repeat"),
    ),
    Case(
        "real",
        "gradient_regression",
        "Yo, okay this is test number one. Okay, one, we're gonna test how the formatting is gonna "
        "be. Two, it is still not, it did not change the gradient. The gradient source points are "
        "not moving and there's still overlapping lines. It's forming a pattern that's straining. "
        "Number three, the mic icon should be BGB gradient should move.",
        ("Yo", "test number one", "gradient source points", "overlapping lines", "pattern", "Number three", "BGB gradient"),
    ),
    Case(
        "real",
        "super_bowl_story",
        "Well, it's a story about... It's an absurd story. It's a Super Bowl ad of a guy who is in "
        "Eastern Ukraine and all these badass things are happening to him because people around are "
        "eating, drinking a certain kind of coffee.",
        ("story about", "absurd story", "Super Bowl ad", "Eastern Ukraine", "badass things", "certain kind of coffee"),
    ),
    Case(
        "real",
        "dashboard_todos",
        "Ok, a few things I wanna get out of the box. Number 1 in the dashboard, the gradient should "
        "be throughout the dashboard, not just in that one box. Also why there are so many boxes? "
        "Just get rid of them. Number 2 these light, medium, none, they should have one line explainers "
        "when I have a cursor over them. Number 3 once you are done making these changes let me know "
        "what other things we can do next.",
        ("few things", "1.", "2.", "3.", "throughout the dashboard", "so many boxes?", "one line explainers", "cursor", "what other things"),
    ),
    Case(
        "real",
        "long_mic_feedback",
        "Yo check mic testing 1 2 3 alright so let me begin. Number one, the gradients in the "
        "background should be throughout the overlay, not just the center box. Number two, the "
        "gradients need to move as I'm speaking. Number three, make sure there is an example in the "
        "settings for smooth scroll. The words get added once and then move behind, so what should "
        "we do here?",
        ("mic testing 1 2 3", "1.", "2.", "3.", "gradients in the background", "center box", "move as I'm speaking", "settings", "smooth scroll", "what should we do here?"),
    ),
    Case(
        "real",
        "unfinished_opinion",
        "Yo, this is how it's gonna work, huh? The gradients have this weird pattern going on, so I "
        "don't think—yeah, I do not like the fact that I can see so many lines in the gradients.",
        ("Yo", "gonna work", "weird pattern", "I do not like", "so many lines", "gradients"),
    ),
    Case(
        "real",
        "product_names_fragment",
        "Yapkey, Wispr Flow. These changes, I wanna know what all do you think we should do next? "
        "Yeah, that's it.",
        ("Yapkey", "Wispr Flow", "what all do you think", "do next?", "that's it"),
    ),
    # Synthetic cases designed to probe behavior not fully covered in history.
    Case(
        "synthetic",
        "meeting_correction",
        "Um, hi Maya, please move the design review from Tuesday no actually Wednesday afternoon, "
        "and send the invite to dev-team@example.com. That's all, thanks.",
        ("Hi Maya", "Wednesday afternoon", "dev-team@example.com", "That's all", "thanks"),
        ("Tuesday", "not Wednesday", "Um"),
    ),
    Case(
        "synthetic",
        "meaningful_fillers",
        "I said yeah because I actually like the first option, so is that the one we're shipping?",
        ("said yeah", "actually like", "so is that", "we're shipping?"),
    ),
    Case(
        "synthetic",
        "emphasis_and_profanity",
        "Uh, this is very very very important, and I'm really, really not okay with that damn workaround.",
        ("very very very", "really, really", "not okay", "damn workaround"),
        ("Uh",),
    ),
    Case(
        "synthetic",
        "technical_literals",
        "Email ops+night@example.com, open https://status.example.com/v3.7, and reserve ₹2,500 for build 1042.",
        ("ops+night@example.com", "https://status.example.com/v3.7", "₹2,500", "1042"),
    ),
    Case(
        "synthetic",
        "negation_and_uncertainty",
        "I don't think we should cancel the launch, but I'm not completely sure we should announce it today either.",
        ("don't think", "cancel the launch", "not completely sure", "today either"),
    ),
    Case(
        "synthetic",
        "direct_question",
        "Hey, can you tell me whether the export keeps transparent backgrounds, or does it flatten everything?",
        ("Hey", "can you tell me", "transparent backgrounds", "flatten everything?"),
        ("Yes,", "No,", "It will flatten", "It keeps transparent"),
    ),
    Case(
        "synthetic",
        "already_clean_formal",
        "The quarterly review begins at 9:30 AM, and all department leads are expected to attend.",
        ("quarterly review", "9:30 AM", "all department leads", "expected to attend"),
    ),
)


BROAD_PROMPTS = {
    "incumbent_examples": SMART_INSTRUCTION,
    "ultra_terse": """Return only the cleaned voice transcript. Fix punctuation and casing; remove
meaningless fillers, stutters, and accidental repeats. Preserve every idea,
meaningful word, fact, name, number, question, negation, tone, opening, and ending.
Do not summarize, paraphrase, answer, invent, or formalize. If unsure, keep it.""",
    "protected_copy": """TRANSCRIPT COPY MODE. Output only the edited transcript.

Treat every source phrase as protected unless it is clearly one of these:
- a standalone hesitation sound such as um, uh, erm, or hmm;
- an immediate accidental repeat or stutter;
- spoken punctuation already represented by layout.

You may fix capitalization, punctuation, spacing, and sentence boundaries. You
must copy all other content in the same order, including greetings, unfinished
thoughts, meaningful repetition, slang, profanity, questions, negation, names,
numbers, URLs, email addresses, technical terms, the opening, and the ending.
Never answer, summarize, paraphrase, improve the argument, or substitute synonyms.
For clear self-corrections, retain the speaker's final choice. When uncertain,
copy the words rather than deleting them.""",
    "silent_audit": """Act as a careful voice-transcript editor. Return only the final transcript.

Silently do three passes:
1. Mark every idea, name, number, technical term, question, negation, greeting,
   emphatic repetition, opening phrase, and closing phrase that must survive.
2. Remove only speech-only hesitation sounds, clear stutters, abandoned duplicate
   starts, and exact accidental repeats; fix punctuation, casing, and layout.
3. Verify every marked element is still present in its original order.

Do not answer the speaker, summarize, paraphrase, formalize, sanitize, invent,
or replace casual vocabulary. Resolve only unmistakable self-corrections by
keeping the final choice. If any edit is uncertain, preserve the original words.""",
    "contrast_examples": """Clean voice dictation. Return only the cleaned transcript.

Allowed: punctuation, capitalization, spacing, clear sentence breaks, removal of
standalone um/uh sounds, stutters, and exact accidental repeats.
Forbidden: summarizing, paraphrasing, answering, adding facts, changing tone or
vocabulary, or dropping any meaningful beginning, ending, question, negation,
name, number, technical term, slang, profanity, or intentional repetition.

Raw: Um, I think I think we should ship Friday.
Clean: I think we should ship Friday.
Raw: I said yeah, and I actually like it.
Clean: I said yeah, and I actually like it.
Raw: This is very very very important.
Clean: This is very very very important.
Raw: Can you tell me whether it works?
Clean: Can you tell me whether it works?

Keep the original order. For explicit corrections keep the final choice. When
unsure, retain the source wording.""",
}


EDGE_RULE = """

Boundary rule: preserve informal but meaningful openings and closings such as
"Yo", "Hey", "Well", "Okay", "thanks", "that's it", and "let's go". Never drop
the first or final utterance merely because it is conversational. Standalone
um/uh/erm/hmm hesitation sounds are the only disposable opening tokens."""

EDGE_EXAMPLES = """

Boundary examples:
Raw: Yo, okay, this is test number one. The gradient still looks wrong.
Clean: Yo, okay, this is test number one. The gradient still looks wrong.
Raw: Hey, can you tell me whether the export works? That's it, thanks.
Clean: Hey, can you tell me whether the export works? That's it, thanks.
Raw: Um, hi Maya, please move the meeting.
Clean: Hi Maya, please move the meeting."""

REPEAT_RULE = """

Repeat rule: remove an immediately duplicated word or short phrase when it occurs
exactly twice as a speech stumble. Preserve three-or-more repetitions and
punctuated repetitions as intentional emphasis."""

NARROW_PROMPTS = {
    # SMART_INSTRUCTION is now the winning edge-examples prompt. Keeping a
    # single post-install entry prevents future lab runs from appending the
    # experimental boundary material a second time.
    "installed_winner": SMART_INSTRUCTION,
}


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


def score(case: Case, prepared: str, result: str) -> tuple[float, str, tuple[str, ...]]:
    if not result:
        return 0.0, "empty", ("complete output",)
    try:
        verify_protected_literals(prepared, result)
        verify_not_truncated(prepared, result)
        verify_preserved_intent(case.source, result)
    except ValueError as exc:
        return 0.0, f"unsafe: {exc}", ()

    folded = result.replace("’", "'").casefold()
    missing = tuple(
        phrase
        for phrase in case.required
        if phrase.replace("’", "'").casefold() not in folded
    )
    present_forbidden = tuple(
        phrase
        for phrase in case.forbidden
        if phrase.replace("’", "'").casefold() in folded
    )
    required_score = 4.0 * (len(case.required) - len(missing)) / max(1, len(case.required))
    cleanup_score = (
        2.0 * (len(case.forbidden) - len(present_forbidden)) / len(case.forbidden)
        if case.forbidden
        else 2.0
    )
    source_words = set(re.findall(r"[a-z0-9]+", prepared.casefold()))
    result_words = set(re.findall(r"[a-z0-9]+", folded))
    invented = len(result_words - source_words)
    invention_score = max(0.0, 1.0 - invented * 0.2)
    details = missing + tuple(f"forbidden:{item}" for item in present_forbidden)
    return 3.0 + required_score + cleanup_score + invention_score, "accepted", details


def run(prompts: dict[str, str]) -> dict[str, float]:
    config = AppConfig.load()
    formatter = OptionalSemanticFormatter(True, config.semantic_model_path)
    if not formatter.available:
        raise RuntimeError(formatter.error or "Local formatter unavailable")
    started = time.perf_counter()
    formatter._load()
    print(f"MODEL READY {time.perf_counter() - started:.2f}s")
    controls = DeterministicFormatter()
    totals = {name: 0.0 for name in prompts}
    group_totals = {name: {"real": 0.0, "synthetic": 0.0} for name in prompts}
    unsafe = {name: 0 for name in prompts}

    for prompt_name, prompt in prompts.items():
        print(f"\n========== {prompt_name} ({len(prompt)} chars) ==========")
        for case in CASES:
            prepared = controls.format(
                case.source, FormatContext(cleanup_level="smart")
            ).text
            case_started = time.perf_counter()
            result = generate(formatter, prompt, prepared)
            points, verdict, details = score(case, prepared, result)
            totals[prompt_name] += points
            group_totals[prompt_name][case.group] += points
            if verdict != "accepted":
                unsafe[prompt_name] += 1
            elapsed = time.perf_counter() - case_started
            suffix = f" · issues={details}" if details else ""
            print(
                f"[{case.group}/{case.label}] {points:.2f}/10 · {verdict} · {elapsed:.2f}s{suffix}"
            )
            preview = result.replace("\n", "\\n")
            print(preview[:420] + ("…" if len(preview) > 420 else ""))

    maximum = len(CASES) * 10
    group_maximum = sum(case.group == "real" for case in CASES) * 10
    print("\n========== TOTALS ==========")
    for name, total in sorted(totals.items(), key=lambda item: item[1], reverse=True):
        print(
            f"{name}: {total:.2f}/{maximum} · real={group_totals[name]['real']:.2f}/{group_maximum} "
            f"· synthetic={group_totals[name]['synthetic']:.2f}/{maximum - group_maximum} "
            f"· unsafe={unsafe[name]}"
        )
    return totals


if __name__ == "__main__":
    run(BROAD_PROMPTS)
