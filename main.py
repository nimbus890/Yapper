from __future__ import annotations

import multiprocessing
import sys

import aura_flow
from aura_flow.version import APP_DISPLAY_NAME, APP_NAME, PUBLISHER, VERSION


def _run_model_installer(arguments: list[str]) -> int | None:
    """Handle model installation in both Python and frozen executable builds."""

    if "--install-model" not in arguments:
        return None
    index = arguments.index("--install-model")
    if index + 1 >= len(arguments):
        stream = sys.stderr or sys.stdout
        if stream is not None:
            stream.write("ERROR: --install-model requires tiny, medium, or smart\n")
        return 2
    key = arguments[index + 1].casefold()
    force = "--force" in arguments
    try:
        if key == "smart":
            from setup_semantic import install

            install(force=force)
            return 0
        if key not in {"tiny", "medium"}:
            raise ValueError(f"unknown model target: {key}")
        from setup_models import install

        model_name = "tiny.en" if key == "tiny" else "medium"
        role = "partial" if key == "tiny" else "main"
        install(model_name, force=force, role=role)
        return 0
    except Exception as exc:
        stream = sys.stderr or sys.stdout
        if stream is not None:
            stream.write(f"ERROR: {exc}\n")
            stream.flush()
        return 1


def main() -> int:
    multiprocessing.freeze_support()
    installer_result = _run_model_installer(sys.argv[1:])
    if installer_result is not None:
        return installer_result

    # Keep Qt, audio, and inference imports out of the lightweight packaged
    # model-helper process.
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    from aura_flow.config import AppConfig
    from aura_flow.pipeline import DictationPipeline
    from aura_flow.startup import set_startup_enabled
    from aura_flow.ui import AuraFlowWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setOrganizationName(PUBLISHER)
    app.setApplicationVersion(VERSION)
    config = AppConfig.load()
    if config.run_at_startup:
        try:
            set_startup_enabled(True)
        except OSError:
            pass
    app.setQuitOnLastWindowClosed(
        not (config.close_to_tray and QSystemTrayIcon.isSystemTrayAvailable())
    )
    pipeline = DictationPipeline(config)
    window = AuraFlowWindow(pipeline)
    window.run(start_hidden="--startup" in sys.argv)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
