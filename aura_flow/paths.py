"""Read-only application resources and writable user storage locations."""

from __future__ import annotations

import os
from pathlib import Path
import sys

from .version import PUBLISHER


SOURCE_DIR = Path(__file__).resolve().parents[1]
FROZEN = bool(getattr(sys, "frozen", False))
INSTALL_DIR = Path(sys.executable).resolve().parent if FROZEN else SOURCE_DIR
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", SOURCE_DIR)).resolve()


def _default_user_root() -> Path:
    override = os.environ.get("YAPPER_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if os.environ.get("YAPPER_PORTABLE", "").strip() == "1" or (
        INSTALL_DIR / "portable.flag"
    ).is_file():
        return INSTALL_DIR
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data) / PUBLISHER / "Yapper"
    return Path.home() / "AppData" / "Local" / PUBLISHER / "Yapper"


# APP_DIR remains as a compatibility alias for code that needs the install root.
APP_DIR = INSTALL_DIR
USER_ROOT = _default_user_root()
DATA_DIR = USER_ROOT / "data"
MODELS_DIR = USER_ROOT / "models"
LOGS_DIR = USER_ROOT / "logs"
ASSETS_DIR = RESOURCE_DIR / "assets"

