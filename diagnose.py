from __future__ import annotations

import argparse
import json
import platform
import sys

import psutil

from aura_flow.asr import FasterWhisperEngine
from aura_flow import __version__
from aura_flow.config import APP_DIR, AppConfig
from aura_flow.models import choose_model, discover_models, write_manifest
from aura_flow.semantic import discover_semantic_model


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect yapper_'s local runtime.")
    parser.add_argument("--load-model", action="store_true", help="Also verify the selected ASR backend")
    args = parser.parse_args()
    config = AppConfig.load()
    models = discover_models(APP_DIR)
    manifest = write_manifest(APP_DIR, models)
    try:
        import ctranslate2

        cuda_devices = ctranslate2.get_cuda_device_count()
        ct2_version = ctranslate2.__version__
    except Exception as exc:
        cuda_devices = 0
        ct2_version = f"unavailable: {exc}"
    report = {
        "yapkey": __version__,
        "python": sys.version,
        "platform": platform.platform(),
        "cpu_threads": psutil.cpu_count(),
        "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "ctranslate2": ct2_version,
        "ctranslate2_cuda_devices": cuda_devices,
        "configured_device": config.device,
        "cleanup_level": config.cleanup_level,
        "run_at_startup": config.run_at_startup,
        "api_provider": config.api_provider,
        "api_base_url": config.api_base_url,
        "api_model": config.api_model,
        "semantic_formatting": config.semantic_formatting,
        "semantic_validation": True,
        "protected_literal_guard": True,
        "intent_preservation_guard": True,
        "semantic_model_path": str(discover_semantic_model(config.semantic_model_path) or ""),
        "partial_transcription": config.partial_transcription,
        "partial_model_path": config.partial_model_path,
        "models": [item.as_json() for item in models],
        "manifest": str(manifest),
    }
    try:
        import PySide6

        report["pyside6"] = PySide6.__version__
    except Exception as exc:
        report["pyside6"] = f"unavailable: {exc}"
    try:
        import uiautomation

        report["windows_uiautomation"] = getattr(uiautomation, "VERSION", "available")
    except Exception as exc:
        report["windows_uiautomation"] = f"unavailable: {exc}"
    complete = [item for item in models if item.complete]
    if not complete:
        print(json.dumps(report, indent=2))
        print("\nERROR: no complete Faster-Whisper model found.")
        return 2
    if args.load_model:
        try:
            selected = choose_model(APP_DIR, config.model_path, config.model_name)
            engine = FasterWhisperEngine(selected.path, config)
            engine.load()
            report["verified_model"] = selected.name
            report["verified_device"] = engine.device
            report["verified_compute_type"] = engine.compute_type
        except Exception as exc:
            report["model_load_error"] = str(exc)
            print(json.dumps(report, indent=2))
            return 3
    print(json.dumps(report, indent=2))
    if not cuda_devices:
        print("\nWARNING: CTranslate2 cannot currently use the NVIDIA GPU; CPU fallback will be used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
