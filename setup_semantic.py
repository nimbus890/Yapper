from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from huggingface_hub import snapshot_download

from aura_flow.config import AppConfig
from aura_flow.paths import MODELS_DIR
from aura_flow.semantic import _complete_model, discover_semantic_model


MODEL_REPO = "google/gemma-3-1b-it"
TARGET = MODELS_DIR / "gemma-3-1b-it"


def _enable_inherited_access(path: Path) -> None:
    if os.name == "nt":
        subprocess.run(
            ["icacls", str(path), "/inheritance:e", "/T", "/C"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def _copy_or_link_tree(source: Path, target: Path) -> None:
    for item in source.rglob("*"):
        destination = target / item.relative_to(source)
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(item, destination)
        except OSError:
            shutil.copy2(item, destination)


def _select(target: Path) -> None:
    config = AppConfig.load()
    config.semantic_formatting = True
    config.semantic_model_path = str(target.resolve())
    config.cleanup_level = "smart"
    config.save()


def adopt_existing() -> Path | None:
    source = discover_semantic_model(AppConfig.load().semantic_model_path)
    if source is None:
        return None
    if source == TARGET.resolve() and _complete_model(TARGET):
        _select(TARGET)
        _enable_inherited_access(TARGET)
        return TARGET
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gemma-adopt-", dir=TARGET.parent) as temporary:
        staging = Path(temporary) / "model"
        staging.mkdir()
        _copy_or_link_tree(source, staging)
        if not _complete_model(staging):
            raise RuntimeError("The adopted Gemma model is incomplete")
        if TARGET.exists():
            shutil.rmtree(TARGET)
        os.replace(staging, TARGET)
    _select(TARGET)
    _enable_inherited_access(TARGET)
    print(f"Adopted local Gemma model: {source} -> {TARGET}")
    return TARGET


def install(force: bool = False) -> Path:
    if _complete_model(TARGET) and not force:
        _select(TARGET)
        _enable_inherited_access(TARGET)
        return TARGET
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gemma-download-", dir=TARGET.parent) as temporary:
        staging = Path(temporary) / "model"
        try:
            snapshot_download(repo_id=MODEL_REPO, local_dir=staging)
        except Exception as exc:
            message = str(exc)
            if "gated" in message.casefold() or "401" in message or "403" in message:
                raise RuntimeError(
                    "Gemma access is gated. Accept Google's license at "
                    "https://huggingface.co/google/gemma-3-1b-it, sign in with "
                    "`hf auth login`, then run setup_semantic.py again."
                ) from exc
            raise
        if not _complete_model(staging):
            raise RuntimeError("The downloaded Gemma model is incomplete")
        if TARGET.exists():
            shutil.rmtree(TARGET)
        os.replace(staging, TARGET)
    _select(TARGET)
    _enable_inherited_access(TARGET)
    print(f"Installed local Gemma 3 1B formatter: {TARGET}")
    return TARGET


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the local yapper_ AI formatter.")
    parser.add_argument("--adopt-existing", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        if args.adopt_existing:
            return 0 if adopt_existing() else 2
        install(args.force)
        return 0
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
