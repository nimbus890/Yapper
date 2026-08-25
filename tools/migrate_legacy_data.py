"""Copy selected personal state from an older yapper_ data folder."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from aura_flow.paths import DATA_DIR


FILES = (
    "api_key.bin",
    "history.jsonl",
    "last_transcript.txt",
    "metrics.jsonl",
    "personalization.json",
    "settings.json",
)


def migrate(source: Path, destination: Path = DATA_DIR, force: bool = False) -> list[Path]:
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Legacy data folder not found: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for name in FILES:
        old = source / name
        new = destination / name
        if not old.is_file() or (new.exists() and not force):
            continue
        shutil.copy2(old, new)
        copied.append(new)
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Older version's data folder")
    parser.add_argument("--destination", type=Path, default=DATA_DIR)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    copied = migrate(args.source, args.destination, args.force)
    print(f"Copied {len(copied)} file(s) into {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

