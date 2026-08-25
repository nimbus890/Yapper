"""Export the runtime app icon as PNG and a multi-size Windows ICO."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QApplication

from aura_flow.icons import create_app_icon
from aura_flow.paths import SOURCE_DIR


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    assets = SOURCE_DIR / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    png_path = assets / "app-icon.png"
    ico_path = assets / "app.ico"
    pixmap = create_app_icon(1024).pixmap(1024, 1024)
    if not pixmap.save(str(png_path), "PNG"):
        raise RuntimeError(f"Could not write {png_path}")
    with Image.open(png_path) as image:
        image.save(
            ico_path,
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
    print(f"Created {png_path} and {ico_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
