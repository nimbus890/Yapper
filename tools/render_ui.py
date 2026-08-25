"""Render the three primary surfaces for visual regression checks."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import aura_flow  # noqa: F401 - initializes the version-local import path
from PySide6.QtWidgets import QApplication

from aura_flow.config import AppConfig
from aura_flow.pipeline import DictationPipeline
from aura_flow.ui import AuraFlowWindow


def render() -> list[Path]:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    pipeline = DictationPipeline(AppConfig.load())
    pipeline.start = lambda: None

    # Rendering is a visual check, not a live app session.
    AuraFlowWindow._create_tray = lambda self: None
    AuraFlowWindow._bind_hotkeys = lambda self: None

    window = AuraFlowWindow(pipeline)
    window.resize(1420, 900)
    window.show()
    app.processEvents()
    window._apply_state("ready")
    window.target_label.setText("Typing into  /  ChatGPT")
    window.hero_status.setText("Ready. Hold Alt + Z and speak naturally.")
    window.raw_card.editor.setPlainText(
        "Hey team, quick update on the launch plan. We need to move the review "
        "to Thursday, actually no, Friday morning. Before then I need a few "
        "things colon number one finish the onboarding copy, number two check "
        "the Windows installer, number three send Maya the final screenshots."
    )
    window.final_card.editor.setPlainText(
        "Hey team, quick update on the launch plan. We need to move the review "
        "to Friday morning. Before then, I need a few things:\n"
        "1. Finish the onboarding copy\n"
        "2. Check the Windows installer\n"
        "3. Send Maya the final screenshots"
    )
    window._update_stats(
        {"words_today": 1248, "speaking_wpm": 147, "time_saved_minutes": 38, "total_words": 48290}
    )
    app.processEvents()

    target = PROJECT_ROOT / "docs" / "screenshots"
    target.mkdir(parents=True, exist_ok=True)
    if "--github" in sys.argv:
        window._apply_theme("dark", persist=False)
        window._show_main_dashboard()
        app.processEvents()
        window._apply_state("ready")
        window.health_dot.setStyleSheet(f"color: {window.theme_colors['green']};")
        window.health_label.setText("Active")
        window.system_label.setText("Medium  ·  CPU/INT8  ·  private local processing")
        window.context_badge.setText("CONTEXT · READY")
        window.formatter_state.setText("SMART")
        window.cleanup_description.setText(
            f"{window.cleanup_tooltips['smart']} · preservation checks passed"
        )
        app.processEvents()
        path = target / "v39-dashboard-dark.png"
        window.grab().save(str(path))
        window.hide()
        return [path]

    renders = []
    for name, action in (
        ("redesign-dictate.png", window._show_main_dashboard),
        ("redesign-library.png", window.open_history),
        ("redesign-tune.png", window.open_personalization),
        ("redesign-words.png", lambda: window.personalization_panel._select_page(1)),
        ("redesign-corrections.png", lambda: window.personalization_panel._select_page(2)),
        ("redesign-behaviour.png", lambda: window.personalization_panel._select_page(4)),
        ("redesign-downloads.png", lambda: window.personalization_panel._select_page(5)),
        ("redesign-connections.png", lambda: window.personalization_panel._select_page(6)),
    ):
        action()
        app.processEvents()
        window.repaint()
        time.sleep(0.06)
        app.processEvents()
        path = target / name
        window.grab().save(str(path))
        renders.append(path)
    for mode in ("light", "dark"):
        window._apply_theme(mode, persist=False)
        window._show_main_dashboard()
        app.processEvents()
        path = target / f"v39-dashboard-{mode}.png"
        window.grab().save(str(path))
        renders.append(path)
        window.orb.start_dance(8.0)
        window.orb.dance_started_at = time.monotonic() - 3.35
        window.orb.update()
        app.processEvents()
        path = target / f"v39-rick-dance-{mode}.png"
        window.grab().save(str(path))
        renders.append(path)
        window.orb.dance_until = 0.0
        window.resize(1040, 700)
        window._show_main_dashboard()
        window._apply_state("ready")
        app.processEvents()
        path = target / f"v39-dashboard-{mode}-minimum.png"
        window.grab().save(str(path))
        renders.append(path)
        window.resize(1420, 900)
        window.open_personalization()
        window.personalization_panel._select_page(4)
        app.processEvents()
        path = target / f"v39-preferences-{mode}.png"
        window.grab().save(str(path))
        renders.append(path)
    window.hide()
    return renders


if __name__ == "__main__":
    for output in render():
        print(output)
