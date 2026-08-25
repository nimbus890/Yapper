from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from .paths import APP_DIR, DATA_DIR, MODELS_DIR

CONFIG_PATH = DATA_DIR / "settings.json"


@dataclass(slots=True)
class AppConfig:
    sample_rate: int = 16_000
    block_size: int = 1_024
    max_recording_seconds: int = 300
    min_recording_seconds: float = 0.35
    min_speech_seconds: float = 0.25
    vad_rms_threshold: float = 0.006
    hotkey: str = "alt+z"
    audio_device: int | None = None
    model_name: str = "medium"
    model_path: str | None = None
    device: str = "auto"
    cuda_compute_type: str = "float16"
    cpu_compute_type: str = "int8"
    language: str | None = None
    semantic_formatting: bool = True
    semantic_model_path: str | None = str(MODELS_DIR / "gemma-3-1b-it")
    formatter_timeout_seconds: float = 8.0
    cleanup_level: str = "smart"
    restore_clipboard: bool = True
    play_sounds: bool = True
    store_history: bool = True
    context_awareness: bool = True
    direct_insertion: bool = True
    partial_transcription: bool = True
    partial_model_path: str | None = None
    partial_interval_seconds: float = 0.75
    partial_tail_seconds: float = 6.0
    partial_preview_words: int = 10
    recording_mode: str = "smart"
    hotkey_double_tap_seconds: float = 0.32
    show_compact_overlay: bool = True
    close_to_tray: bool = True
    run_at_startup: bool = False
    typing_wpm_baseline: int = 40
    api_provider: str = "OpenAI"
    api_base_url: str = "https://api.openai.com/v1"
    api_models_path: str = "/models"
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer"
    api_model: str = ""
    api_enabled: bool = False
    theme_mode: str = "dark"
    share_anonymous_diagnostics: bool = False
    allow_selected_transcripts: bool = False
    enable_complete_data_export: bool = False
    model_setup_completed: bool = False
    feedback_github_url: str = "https://github.com/nimbus890/Yapper/issues"
    feedback_email: str = ""
    paypal_url: str = ""
    upi_id: str = ""
    upi_display_name: str = ""

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "AppConfig":
        config = cls()
        if not path.exists():
            return config
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return config
        allowed = {item.name for item in fields(cls)}
        for key, value in payload.items():
            if key in allowed:
                setattr(config, key, value)
        legacy_cleanup = {
            "light": "minimal",
            "medium": "minimal",
            "ai_light": "smart",
            "ai_medium": "smart",
        }
        config.cleanup_level = legacy_cleanup.get(config.cleanup_level, config.cleanup_level)
        if config.cleanup_level not in {"minimal", "smart"}:
            config.cleanup_level = "smart"
        if config.theme_mode not in {"system", "light", "dark"}:
            config.theme_mode = "dark"
        return config

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        os.replace(temporary, path)

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)
