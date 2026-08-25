from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from huggingface_hub import snapshot_download

from aura_flow.config import APP_DIR, AppConfig
from aura_flow.paths import MODELS_DIR
from aura_flow.models import discover_models, validate_faster_whisper


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
        relative = item.relative_to(source)
        destination = target / relative
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(item, destination)
        except OSError:
            shutil.copy2(item, destination)


def adopt_existing(model_name: str | None = None, role: str = "main") -> Path | None:
    complete = [candidate for candidate in discover_models(APP_DIR) if candidate.complete]
    if model_name:
        complete = [candidate for candidate in complete if candidate.name == model_name]
    if not complete:
        return None
    source = complete[0]
    models_dir = MODELS_DIR
    models_dir.mkdir(parents=True, exist_ok=True)
    target = models_dir / f"faster-whisper-{source.name}"
    if validate_faster_whisper(target).complete:
        selected = target
    else:
        with tempfile.TemporaryDirectory(prefix=f".{source.name}-adopt-", dir=models_dir) as temporary:
            staging = Path(temporary) / "model"
            staging.mkdir()
            _copy_or_link_tree(source.path, staging)
            candidate = validate_faster_whisper(staging)
            if not candidate.complete:
                raise RuntimeError("Adopted model failed validation: " + ", ".join(candidate.missing))
            if target.exists():
                shutil.rmtree(target)
            os.replace(staging, target)
        selected = target
    _enable_inherited_access(selected)
    _select_model(selected, source.name, role)
    print(f"Adopted existing model: {source.path} -> {selected}")
    return selected


def _select_model(target: Path, model_name: str, role: str) -> None:
    config = AppConfig.load()
    if role == "partial":
        config.partial_transcription = True
        config.partial_model_path = str(target.resolve())
    else:
        config.model_name = model_name
        config.model_path = str(target.resolve())
    config.save()


def install(model_name: str, force: bool, role: str = "main") -> Path:
    models_dir = MODELS_DIR
    models_dir.mkdir(parents=True, exist_ok=True)
    target = models_dir / f"faster-whisper-{model_name}"
    current = validate_faster_whisper(target)
    if current.complete and not force:
        _select_model(target, model_name, role)
        _enable_inherited_access(target)
        print(f"Model is already complete: {target}")
        return target
    if target.exists() and not force:
        missing = ", ".join(current.missing)
        raise RuntimeError(f"Existing model directory is incomplete ({missing}). Re-run with --force to repair it.")

    with tempfile.TemporaryDirectory(prefix=f".{model_name}-", dir=models_dir) as temporary:
        staging = Path(temporary) / "model"
        print(f"Downloading Systran/faster-whisper-{model_name} into staging…")
        snapshot_download(
            repo_id=f"Systran/faster-whisper-{model_name}",
            local_dir=staging,
        )
        candidate = validate_faster_whisper(staging)
        if not candidate.complete:
            raise RuntimeError("Downloaded model failed validation: missing " + ", ".join(candidate.missing))
        if target.exists():
            shutil.rmtree(target)
        os.replace(staging, target)

    _select_model(target, model_name, role)
    _enable_inherited_access(target)
    print(f"Installed and selected for {role}: {target}")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Transactionally install a local Faster-Whisper model.")
    parser.add_argument("--model", default="small.en", help="Model name, e.g. base.en, small.en, medium, turbo")
    parser.add_argument("--force", action="store_true", help="Replace an incomplete/existing target")
    parser.add_argument("--adopt-existing", action="store_true", help="Hard-link/copy a complete model from an older snapshot")
    parser.add_argument("--role", choices=("main", "partial"), default="main", help="Which pipeline role should use the model")
    args = parser.parse_args()
    if args.adopt_existing:
        adopted = adopt_existing(args.model, args.role)
        if adopted is None:
            print("No complete existing model was available to adopt.")
        return 0
    install(args.model, args.force, args.role)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
