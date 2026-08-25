from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .paths import FROZEN, SOURCE_DIR


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "yapper"
LEGACY_RUN_VALUE = "YapKey"


def startup_command() -> str:
    executable = Path(sys.executable)
    if FROZEN:
        return subprocess.list2cmdline([str(executable.resolve()), "--startup"])
    pythonw = executable.with_name("pythonw.exe")
    if pythonw.is_file():
        executable = pythonw
    return subprocess.list2cmdline(
        [str(executable.resolve()), str((SOURCE_DIR / "main.py").resolve()), "--startup"]
    )


def is_startup_enabled() -> bool:
    if os.name != "nt":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
        return bool(str(value).strip())
    except OSError:
        return False


def set_startup_enabled(enabled: bool) -> None:
    if os.name != "nt":
        if enabled:
            raise RuntimeError("Run at startup is available on Windows only")
        return
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, startup_command())
            try:
                winreg.DeleteValue(key, LEGACY_RUN_VALUE)
            except FileNotFoundError:
                pass
        else:
            for value_name in (RUN_VALUE, LEGACY_RUN_VALUE):
                try:
                    winreg.DeleteValue(key, value_name)
                except FileNotFoundError:
                    pass
