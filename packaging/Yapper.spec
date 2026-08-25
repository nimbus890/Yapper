from pathlib import Path
import importlib.util

from PyInstaller.utils.hooks import collect_data_files


PROJECT_ROOT = Path(SPECPATH).parent
ICON = PROJECT_ROOT / "assets" / "app.ico"

datas = [(str(PROJECT_ROOT / "assets"), "assets")]
datas += collect_data_files("faster_whisper")

uiautomation_spec = importlib.util.find_spec("uiautomation")
uiautomation_root = Path(uiautomation_spec.origin).parent
binaries = [
    (str(path), "uiautomation/bin")
    for path in (uiautomation_root / "bin").glob("UIAutomationClient_*.dll")
]

analysis = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=["setup_models", "setup_semantic", "uiautomation"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Yapper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(ICON) if ICON.is_file() else None,
    version=str(PROJECT_ROOT / "packaging" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Yapper",
)
