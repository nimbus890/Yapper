from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtGui import QFontDatabase


# Restored from the v3.2 design system: cinematic near-black surfaces, coral
# action energy, violet depth, and minimal translucent structure.
COLORS = {
    "canvas": "#090B10",
    "surface": "#12151C",
    "surface_alt": "#181C25",
    "text": "#F5F3F0",
    "muted": "#9299A8",
    "accent": "#FF7557",
    "accent_alt": "#9A7BFF",
    "accent_soft": "#3B2021",
    "green": "#6DDBA5",
    "red": "#FF6B6B",
    "line": "#282D38",
}

LIGHT_COLORS = {
    "canvas": "#F4F1EA",
    "surface": "#FFFDF8",
    "surface_alt": "#E8E5DE",
    "text": "#272725",
    "muted": "#716F69",
    "accent": "#7D72E8",
    "accent_alt": "#E3BF5B",
    "accent_soft": "#ECE8FF",
    "green": "#3D9676",
    "red": "#E87870",
    "line": "#C8C5BD",
}

THEME_COLORS = {"dark": COLORS, "light": LIGHT_COLORS}


def load_application_fonts() -> None:
    """Register the same display stack used by v3.2."""
    font_root = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for name in (
        "bahnschrift.ttf",
        "segoeui.ttf",
        "segoeuib.ttf",
        "CascadiaMono.ttf",
        "consola.ttf",
    ):
        path = font_root / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))


def apply_soft_shadow(widget, blur: float = 0, y_offset: float = 0) -> None:
    """Compatibility hook; v3.2 intentionally uses no detached card shadows."""
    del blur, y_offset
    widget.setGraphicsEffect(None)


APP_STYLESHEET = """
* { font-family: "Bahnschrift", "Segoe UI Variable", "Segoe UI"; color: #F5F3F0; }
QMainWindow, QDialog { background: #090B10; }
QWidget#appRoot, QWidget#dashboardPage, QWidget#personalizationRoot, QWidget#historyRoot,
QStackedWidget { background: transparent; }
QFrame#statSection, QFrame#recordingStage, QFrame#outputSection,
QFrame#historyDeck, QFrame#machineShell, QFrame#topRail {
    background: transparent; border: none;
}
QFrame#cleanupWell {
    background: rgba(10, 13, 18, 86); border: none;
    border-left: 1px solid rgba(255, 255, 255, 22); border-radius: 0;
}
QFrame#controlBar, QFrame#meterRail {
    background: rgba(12, 15, 21, 145); border: none;
    border-top: 1px solid rgba(255, 255, 255, 26); border-radius: 0;
}
QFrame#readout { background: transparent; border: none; }
QFrame#segmentedBar { background: transparent; border: none; }
QFrame#personalNav {
    background: rgba(12, 15, 21, 112); border: none;
    border-right: 1px solid rgba(255, 255, 255, 24); border-radius: 0;
}
QFrame#apiCard {
    background: rgba(12, 15, 21, 105); border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 12px;
}
QLabel#brand { font-size: 25px; font-weight: 800; letter-spacing: 2px; }
QLabel#pageTitle { font-size: 27px; font-weight: 700; letter-spacing: .4px; }
QLabel#deckTitle { font-size: 18px; font-weight: 700; }
QLabel#eyebrow, QLabel#cardTitle, QLabel#fieldTitle {
    color: #9299A8; font-size: 12px; font-weight: 700; letter-spacing: 1.5px;
}
QLabel#bigStat { color: #FF7557; font-size: 30px; font-weight: 700; }
QLabel#overviewStat { color: #F5F3F0; font-size: 38px; font-weight: 700; }
QLabel#insightStat { color: #FF8B70; font-size: 19px; font-weight: 650; }
QLabel#sectionLead { color: #D8D9DE; font-size: 18px; }
QLabel#statusText { color: #F5F3F0; font-size: 13px; font-weight: 700; letter-spacing: 1px; }
QLabel#timer { font-family: "Cascadia Mono", "Consolas"; font-size: 24px; font-weight: 600; }
QLabel#muted, QLabel#metric, QLabel#hint { color: #9299A8; }
QLabel#resourceMetric { color: #6F7582; font-size: 9px; letter-spacing: .3px; }
QLabel#deviceReady, QLabel#successText { color: #6DDBA5; font-weight: 700; }
QLabel#errorText { color: #FF6B6B; font-weight: 700; }
QLabel#stepNumber {
    background: #FF7557; color: #090B10; border-radius: 13px;
    min-width: 26px; min-height: 26px; font-weight: 800;
}
QPushButton {
    background: rgba(26, 30, 39, 188); border: 1px solid rgba(255, 255, 255, 28);
    border-radius: 14px; padding: 9px 16px; font-weight: 700;
}
QPushButton:hover { background: #222733; border-color: #FF7557; }
QPushButton:pressed, QPushButton:checked { background: #FF7557; border-color: #FF7557; color: #090B10; }
QPushButton:disabled { color: #666D7A; background: #151820; border-color: #222630; }
QPushButton#accentButton { background: #FF7557; color: #090B10; border: none; }
QPushButton#accentButton:hover { background: #FF8B70; }
QPushButton#ghostButton, QPushButton#navTab {
    background: transparent; border: none; color: #9299A8; padding: 9px 14px;
}
QPushButton#ghostButton:hover, QPushButton#navTab:hover { color: #F5F3F0; }
QPushButton#navTab:checked { color: #FF8B70; background: transparent; }
QPushButton#connectionButton { background: rgba(18, 22, 30, 190); color: #9299A8; }
QPushButton#connectionButton[online="true"] { color: #6DDBA5; border-color: #366B57; }
QPushButton#modeButton { padding: 10px 20px; }
QPushButton#navButton {
    background: transparent; border: none; border-radius: 10px; color: #9299A8;
    padding: 11px 12px; text-align: left; font-weight: 600;
}
QPushButton#navButton:hover { background: rgba(255, 255, 255, 12); color: #F5F3F0; }
QPushButton#navButton:checked { background: rgba(255, 117, 87, 28); color: #FF8B70; }
QComboBox, QLineEdit, QSpinBox {
    background: rgba(24, 28, 37, 205); border: 1px solid rgba(255, 255, 255, 28);
    border-radius: 11px; padding: 8px 12px; min-height: 20px; selection-background-color: #513029;
}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover { border-color: #505866; }
QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border-color: #FF7557; }
QComboBox::drop-down { width: 24px; border: none; }
QComboBox QAbstractItemView {
    background: #181C25; selection-background-color: #FF7557;
    selection-color: #090B10; border: 1px solid #303642; outline: none;
}
QTextEdit, QListWidget, QTableWidget {
    background: rgba(12, 15, 21, 105); border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 12px; selection-background-color: #513029;
    font-size: 13px; gridline-color: #282D38;
}
QTextEdit#transcriptEditor {
    background: rgba(10, 13, 18, 86); border: none;
    border-left: 1px solid rgba(255, 255, 255, 22);
    border-radius: 0; padding: 10px 14px; font-family: "Segoe UI Variable", "Segoe UI";
}
QHeaderView::section { background: #181C25; color: #9299A8; border: none; padding: 8px; font-weight: 700; }
QScrollBar:vertical { width: 8px; background: transparent; }
QScrollBar::handle:vertical { background: #363C48; border-radius: 4px; min-height: 22px; }
QProgressBar { background: #272C36; border: none; border-radius: 4px; height: 8px; }
QProgressBar::chunk { background: #FF7557; border-radius: 4px; }
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab { background: transparent; color: #9299A8; padding: 10px 16px; font-weight: 700; }
QTabBar::tab:selected { color: #FF7557; border-bottom: 2px solid #FF7557; }
QCheckBox { spacing: 10px; }
QCheckBox::indicator {
    width: 18px; height: 18px; background: #151820;
    border: 1px solid #3A404D; border-radius: 5px;
}
QCheckBox::indicator:checked { background: #FF7557; border-color: #FF7557; }
QSplitter::handle { background: transparent; }
QSplitter::handle:hover { background: #222733; border-radius: 3px; }
QMenu { background: #181C25; border: 1px solid #303642; padding: 6px; }
QMenu::item { padding: 8px 20px; border-radius: 8px; }
QMenu::item:selected { background: #2A2022; color: #FF8B70; }
QToolTip { background: #222733; color: #F5F3F0; border: 1px solid #363C48; padding: 6px; }
"""


LIGHT_STYLESHEET = """
* { font-family: "Bahnschrift", "Segoe UI Variable", "Segoe UI"; color: #272725; }
QMainWindow, QDialog { background: #F4F1EA; }
QWidget#appRoot, QWidget#dashboardPage, QWidget#personalizationRoot, QWidget#historyRoot,
QStackedWidget { background: transparent; }
QFrame#statSection, QFrame#recordingStage { background: transparent; border: none; }
QFrame#outputSection {
    background: rgba(255, 253, 248, 48); border: 1px solid rgba(126, 121, 111, 64);
    border-radius: 18px;
}
QFrame#historyDeck, QFrame#machineShell, QFrame#apiCard {
    background: rgba(255, 253, 248, 174); border: 1px solid rgba(162, 157, 146, 120); border-radius: 16px;
}
QFrame#topRail { background: rgba(255, 253, 248, 112); border: none; border-bottom: 1px solid rgba(164, 159, 148, 96); }
QFrame#cleanupWell {
    background: rgba(255, 253, 248, 72); border: 1px solid rgba(174, 168, 157, 92);
    border-radius: 15px; padding: 10px 14px;
}
QTextEdit#transcriptEditor, QTextEdit#transcriptEditor QWidget {
    background: transparent; border: none;
}
QFrame#controlBar, QFrame#meterRail {
    background: rgba(229, 226, 218, 92); border: 1px solid rgba(166, 161, 151, 92); border-radius: 18px;
}
QFrame#readout, QFrame#segmentedBar { background: transparent; border: none; }
QFrame#personalNav { background: rgba(225, 222, 214, 126); border: none; border-right: 1px solid rgba(166, 161, 151, 100); }
QLabel#brand { font-size: 25px; font-weight: 800; letter-spacing: 2px; }
QLabel#pageTitle { font-size: 27px; font-weight: 700; letter-spacing: .4px; }
QLabel#deckTitle { font-size: 18px; font-weight: 700; }
QLabel#eyebrow, QLabel#cardTitle, QLabel#fieldTitle { color: #716F69; font-size: 12px; font-weight: 700; letter-spacing: 1.5px; }
QLabel#bigStat { color: #5E54B9; font-size: 30px; font-weight: 700; }
QLabel#overviewStat { color: #272725; font-size: 38px; font-weight: 700; }
QLabel#insightStat { color: #675CC8; font-size: 19px; font-weight: 650; }
QLabel#sectionLead { color: #45443F; font-size: 18px; }
QLabel#statusText { color: #272725; font-size: 13px; font-weight: 700; letter-spacing: 1px; }
QLabel#timer { font-family: "Cascadia Mono", "Consolas"; font-size: 24px; font-weight: 600; }
QLabel#muted, QLabel#metric, QLabel#hint { color: #716F69; }
QLabel#resourceMetric { color: #8A877F; font-size: 9px; }
QLabel#deviceReady, QLabel#successText { color: #358A6A; font-weight: 700; }
QLabel#errorText { color: #C7534D; font-weight: 700; }
QLabel#stepNumber { background: #E3BF5B; color: #272725; border-radius: 13px; min-width: 26px; min-height: 26px; font-weight: 800; }
QPushButton {
    background: rgba(228, 225, 217, 188); border: 1px solid rgba(163, 158, 147, 135); border-radius: 14px;
    padding: 9px 16px; font-weight: 700;
}
QPushButton:hover { background: #F0EDFF; border-color: #9C93E8; }
QPushButton:pressed, QPushButton:checked { background: #DCD7FF; border-color: #9C93E8; color: #272725; }
QPushButton:disabled { color: #9C9992; background: #DDDAD2; border-color: #CFCCC4; }
QPushButton#accentButton { background: #7D72E8; color: #FFFFFF; border-color: #665BC9; }
QPushButton#accentButton:hover { background: #9187EC; }
QPushButton#ghostButton, QPushButton#navTab { background: transparent; border: none; color: #716F69; padding: 9px 14px; }
QPushButton#ghostButton:hover, QPushButton#navTab:hover { color: #272725; background: rgba(125, 114, 232, 38); }
QPushButton#navTab:checked { color: #5E54B9; }
QPushButton#connectionButton { background: #E6E3DC; color: #716F69; }
QPushButton#connectionButton[online="true"] { color: #2E775D; border-color: #72C9AA; }
QPushButton#modeButton { padding: 10px 20px; }
QPushButton#navButton { background: transparent; border: none; border-radius: 10px; color: #716F69; padding: 11px 12px; text-align: left; }
QPushButton#navButton:hover { background: rgba(125, 114, 232, 36); color: #272725; }
QPushButton#navButton:checked { background: rgba(125, 114, 232, 70); color: #5E54B9; }
QComboBox, QLineEdit, QSpinBox {
    background: rgba(255, 253, 248, 190); border: 1px solid rgba(163, 158, 147, 135); border-radius: 11px;
    padding: 8px 12px; min-height: 20px; selection-background-color: #DED9FF;
}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover { border-color: #9C9991; }
QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border: 2px solid #7D72E8; }
QComboBox::drop-down { width: 24px; border: none; }
QComboBox QAbstractItemView { background: #FFFDF8; selection-background-color: #DED9FF; selection-color: #272725; border: 1px solid #C6C3BB; outline: none; }
QTextEdit, QListWidget, QTableWidget { background: rgba(255, 253, 248, 178); border: 1px solid rgba(174, 168, 157, 142); border-radius: 12px; selection-background-color: #DED9FF; gridline-color: #D2CFC7; }
QHeaderView::section { background: #E5E2DA; color: #716F69; border: none; padding: 8px; font-weight: 700; }
QScrollBar:vertical { width: 8px; background: transparent; }
QScrollBar::handle:vertical { background: #B9B6AE; border-radius: 4px; min-height: 22px; }
QProgressBar { background: #D5D2CA; border: none; border-radius: 4px; height: 8px; }
QProgressBar::chunk { background: #7D72E8; border-radius: 4px; }
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab { background: transparent; color: #716F69; padding: 10px 16px; font-weight: 700; }
QTabBar::tab:selected { color: #5E54B9; border-bottom: 2px solid #7D72E8; }
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 18px; height: 18px; background: #E5E2DA; border: 1px solid #A9A69E; border-radius: 5px; }
QCheckBox::indicator:checked { background: #7D72E8; border-color: #665BC9; }
QSplitter::handle { background: transparent; }
QMenu { background: #FFFDF8; border: 1px solid #C6C3BB; padding: 6px; }
QMenu::item { padding: 8px 20px; border-radius: 8px; }
QMenu::item:selected { background: #ECE8FF; color: #5E54B9; }
QToolTip { background: #FFFDF8; color: #272725; border: 1px solid #C6C3BB; padding: 6px; }
"""


def resolve_theme(mode: str) -> str:
    """Resolve System against Windows while remaining safe on other platforms."""
    if mode in {"light", "dark"}:
        return mode
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if int(value) else "dark"
    except Exception:
        return "dark"


def stylesheet_for(mode: str) -> str:
    return LIGHT_STYLESHEET if resolve_theme(mode) == "light" else APP_STYLESHEET
