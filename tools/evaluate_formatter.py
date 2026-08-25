from __future__ import annotations

import sys
import time

from aura_flow.config import AppConfig
from aura_flow.formatting import DeterministicFormatter, FormatContext
from aura_flow.semantic import OptionalSemanticFormatter


SAMPLES = (
    (
        "correction",
        "Hi, this is Yapper. It is going to launch on Thursday, no Friday morning. "
        "It is pretty damn useful and I hope you like it. Thank you.",
    ),
    (
        "list",
        "Hi, this is Yapper. We need three things:\n"
        "1. Capture everything you say even if you pause or repeat a word\n"
        "2. Clean up the text and format it naturally\n"
        "3. Use either local AI or the selected API model\n"
        "I made it in one afternoon and I hope you like it.",
    ),
    (
        "intentional repetition",
        "Um, this can also do very very very smart things, but yeah, it is still "
        "my voice and I really want that emphasis to stay.",
    ),
)


def main() -> int:
    config = AppConfig.load()
    formatter = OptionalSemanticFormatter(True, config.semantic_model_path)
    if not formatter.available:
        print(formatter.error or "Local Smart formatter is unavailable")
        return 1
    load_started = time.perf_counter()
    formatter._load()
    print(f"Local model loaded in {time.perf_counter() - load_started:.2f}s")
    rejected = False
    controls = DeterministicFormatter()
    for label, source in SAMPLES:
        print(f"\n--- {label} ---")
        prepared = controls.format(source, FormatContext(cleanup_level="smart")).text
        started = time.perf_counter()
        try:
            result = formatter.format(
                prepared, "other", "smart", "default", original_text=source
            )
        except ValueError as exc:
            rejected = True
            print(f"SAFE REJECTION: {exc}")
        else:
            print(result)
        print(f"{time.perf_counter() - started:.2f}s")
    return 1 if rejected else 0


if __name__ == "__main__":
    sys.exit(main())
