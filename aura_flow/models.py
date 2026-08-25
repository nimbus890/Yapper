from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .paths import DATA_DIR, MODELS_DIR


REQUIRED_FASTER_WHISPER_FILES = (
    "config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.txt",
)


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    path: Path
    name: str
    complete: bool
    missing: tuple[str, ...]
    size_bytes: int

    def as_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["path"] = str(self.path)
        return payload


def validate_faster_whisper(path: Path) -> ModelCandidate:
    path = path.resolve()
    missing = tuple(name for name in REQUIRED_FASTER_WHISPER_FILES if not (path / name).is_file())
    size = sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.exists() else 0
    name = path.name.removeprefix("faster-whisper-")
    for parent in (path, *path.parents):
        marker = "models--Systran--faster-whisper-"
        if parent.name.startswith(marker):
            name = parent.name.removeprefix(marker)
            break
    return ModelCandidate(path, name, not missing, missing, size)


def _snapshot_dirs(cache_root: Path) -> list[Path]:
    if not cache_root.exists():
        return []
    results: list[Path] = []
    for repo in cache_root.glob("models--Systran--faster-whisper-*"):
        snapshots = repo / "snapshots"
        if snapshots.is_dir():
            results.extend(item for item in snapshots.iterdir() if item.is_dir())
    return results


def discover_models(app_dir: Path) -> list[ModelCandidate]:
    roots = [
        MODELS_DIR / "faster-whisper",
        *MODELS_DIR.glob("faster-whisper-*"),
        app_dir / "models" / "faster-whisper",
    ]
    roots.extend(path for path in (app_dir / "models").glob("faster-whisper-*") if path.is_dir())
    # Development migration: detect complete models in older sibling versions
    # without making those folders part of the release.
    roots.extend(
        path
        for path in app_dir.parent.glob("*/models/faster-whisper-*")
        if path.is_dir()
    )
    seen: set[Path] = set()
    candidates: list[ModelCandidate] = []
    for root in roots:
        direct = validate_faster_whisper(root) if root.is_dir() else None
        paths = [root] if direct and direct.complete else _snapshot_dirs(root)
        for path in paths:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(validate_faster_whisper(resolved))
    return sorted(candidates, key=lambda item: (not item.complete, item.name, str(item.path)))


def choose_model(app_dir: Path, configured_path: str | None, preferred_name: str) -> ModelCandidate:
    if configured_path:
        configured = validate_faster_whisper(Path(configured_path))
        if configured.complete:
            return configured
        missing = ", ".join(configured.missing)
        raise RuntimeError(f"Configured speech model is incomplete: {configured.path} (missing {missing})")

    complete = [item for item in discover_models(app_dir) if item.complete]
    preferred = [item for item in complete if preferred_name.lower() in str(item.path).lower()]
    if preferred:
        return preferred[0]
    if complete:
        return complete[0]
    raise RuntimeError(
        "No complete Faster-Whisper model is installed. Run setup_models.py; "
        "incomplete cache entries will not be used."
    )


def write_manifest(app_dir: Path, candidates: list[ModelCandidate]) -> Path:
    del app_dir  # Kept in the public signature for compatibility with older tools.
    target = DATA_DIR / "model_manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"models": [item.as_json() for item in candidates]}, indent=2),
        encoding="utf-8",
    )
    temporary.replace(target)
    return target
