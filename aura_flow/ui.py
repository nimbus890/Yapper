from __future__ import annotations

import math
import os
import time
from pathlib import Path

import psutil

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    Property,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCloseEvent,
    QConicalGradient,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
    QTextCursor,
    QKeyEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .dialogs import HistoryPanel, PersonalizationPanel
from .support_dialogs import CoffeeDialog, FeedbackDialog
from .hotkeys import GlobalHotkeyController
from .icons import create_app_icon
from .models import discover_models
from .pipeline import DictationPipeline, PipelineState
from .paths import APP_DIR, MODELS_DIR
from .rickroll import AudioPlaybackWorker, RickrollScreen, discover_rick_media
from .theme import (
    COLORS, THEME_COLORS, apply_soft_shadow, load_application_fonts,
    resolve_theme, stylesheet_for,
)
from .version import VERSION


class EventBridge(QObject):
    received = Signal(dict)


def _label(text: str, object_name: str = "", alignment=Qt.AlignLeft) -> QLabel:
    label = QLabel(text)
    if object_name:
        label.setObjectName(object_name)
    label.setAlignment(alignment)
    return label


class BrandLabel(QLabel):
    underscore_clicked = Signal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.underscore_clicked.emit()
        super().mousePressEvent(event)


def _brand_label() -> BrandLabel:
    label = BrandLabel("yapper<span style='color:#FF7557'>_</span>")
    label.setObjectName("brand")
    label.setTextFormat(Qt.RichText)
    label.setAccessibleName("yapper")
    label.setMinimumHeight(36)
    label.setCursor(Qt.PointingHandCursor)
    return label


def _friendly_app_name(process_name: str) -> str:
    stem = Path(process_name).stem.casefold()
    friendly = {
        "chatgpt": "ChatGPT",
        "brave": "Brave",
        "chrome": "Chrome",
        "msedge": "Microsoft Edge",
        "firefox": "Firefox",
        "outlook": "Outlook",
        "olk": "Outlook",
        "slack": "Slack",
        "teams": "Microsoft Teams",
        "ms-teams": "Microsoft Teams",
        "discord": "Discord",
        "telegram": "Telegram",
        "whatsapp": "WhatsApp",
        "notepad": "Notepad",
        "winword": "Microsoft Word",
    }
    if stem in friendly:
        return friendly[stem]
    return stem.replace("-", " ").replace("_", " ").title() if stem else "your active app"


def _theme_icon(show_sun: bool, color: str) -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.8, Qt.SolidLine, Qt.RoundCap))
    if show_sun:
        painter.drawEllipse(QPoint(12, 12), 4, 4)
        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            painter.drawLine(
                QPoint(12 + round(math.cos(radians) * 7), 12 + round(math.sin(radians) * 7)),
                QPoint(12 + round(math.cos(radians) * 9), 12 + round(math.sin(radians) * 9)),
            )
    else:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QRectF(5, 4, 14, 16))
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.drawEllipse(QRectF(9, 2, 12, 14))
    painter.end()
    return QIcon(pixmap)


def _coffee_icon(color: str) -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.6, Qt.SolidLine, Qt.RoundCap))
    painter.drawRoundedRect(QRectF(4, 8, 12, 9), 2, 2)
    painter.drawArc(QRectF(14, 10, 6, 6), -90 * 16, 180 * 16)
    painter.drawLine(3, 20, 18, 20)
    painter.drawArc(QRectF(7, 3, 3, 5), 30 * 16, 120 * 16)
    painter.drawArc(QRectF(12, 2, 3, 5), 30 * 16, 120 * 16)
    painter.end()
    return QIcon(pixmap)


class DashboardCanvas(QWidget):
    """The continuously travelling, audio-reactive field from v3.2."""

    def __init__(self):
        super().__init__()
        self.setObjectName("appRoot")
        self.phase = 0.0
        self.level = 0.0
        self.visual_level = 0.0
        self.state = "loading"
        self.theme = "dark"
        self.retro = False
        self.ambient_timer = QTimer(self)
        self.ambient_timer.timeout.connect(self._animate)
        self.ambient_timer.start(40)

    def set_level(self, level: float) -> None:
        self.level = max(0.0, min(1.0, float(level)))

    def set_state(self, state: str) -> None:
        self.state = state

    def set_theme(self, theme: str) -> None:
        self.theme = resolve_theme(theme)
        self.retro = False
        self.update()

    def set_retro(self, enabled: bool) -> None:
        self.retro = enabled
        self.update()

    def _animate(self) -> None:
        speed = 0.020 if self.theme == "light" else 0.007
        if self.state == "recording":
            speed += (0.040 if self.theme == "light" else 0.020) + self.visual_level * 0.055
        elif self.state == "processing":
            speed += 0.012
        self.phase += speed
        self.visual_level += (self.level - self.visual_level) * 0.12
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        width, height = max(1, self.width()), max(1, self.height())
        if self.retro:
            painter.fillRect(self.rect(), QColor("#15170F"))
            grid = QPen(QColor(213, 203, 91, 28), 1)
            painter.setPen(grid)
            for x in range(0, width, 28):
                painter.drawLine(x, 0, x, height)
            for y in range(0, height, 28):
                painter.drawLine(0, y, width, y)
            return
        if self.theme == "light":
            painter.fillRect(self.rect(), QColor("#F4F1EA"))
            sweep = QLinearGradient(
                width * (0.08 + 0.18 * math.sin(self.phase * 0.83)),
                height * (0.04 + 0.13 * math.cos(self.phase * 0.71)),
                width * (0.91 + 0.16 * math.cos(self.phase * 0.59)),
                height * (0.96 + 0.12 * math.sin(self.phase * 0.67)),
            )
            sweep.setColorAt(0.0, QColor(255, 253, 248, 172))
            sweep.setColorAt(0.38, QColor(214, 207, 250, 130))
            sweep.setColorAt(0.69, QColor(249, 226, 156, 112))
            sweep.setColorAt(1.0, QColor(238, 224, 216, 170))
            painter.fillRect(self.rect(), sweep)
            violet = QRadialGradient(
                QPoint(
                    int(width * (0.28 + 0.20 * math.sin(self.phase * 1.11))),
                    int(height * (0.36 + 0.19 * math.cos(self.phase * 0.91))),
                ),
                max(width, height) * 0.54,
            )
            violet.setColorAt(0.0, QColor(125, 114, 232, 72))
            violet.setColorAt(1.0, QColor(125, 114, 232, 0))
            painter.fillRect(self.rect(), violet)
            warm = QRadialGradient(
                QPoint(
                    int(width * (0.72 + 0.17 * math.cos(self.phase * 0.88))),
                    int(height * (0.58 + 0.21 * math.sin(self.phase * 1.04))),
                ),
                max(width, height) * 0.48,
            )
            warm.setColorAt(0.0, QColor(227, 191, 91, 66))
            warm.setColorAt(0.55, QColor(232, 120, 112, 34))
            warm.setColorAt(1.0, QColor(227, 191, 91, 0))
            painter.fillRect(self.rect(), warm)
            painter.setPen(QPen(QColor(54, 55, 50, 12), 1))
            for x in range(10, width, 34):
                painter.drawLine(x, 0, x, height)
            for y in range(10, height, 34):
                painter.drawLine(0, y, width, y)
            return
        painter.fillRect(self.rect(), QColor("#090B10"))

        sweep = QLinearGradient(
            width * (-0.18 + 0.26 * math.sin(self.phase * 0.71)),
            height * (0.08 + 0.22 * math.cos(self.phase * 0.43)),
            width * (1.15 + 0.22 * math.cos(self.phase * 0.57)),
            height * (0.92 + 0.20 * math.sin(self.phase * 0.83)),
        )
        coral_stop = 0.25 + 0.12 * math.sin(self.phase * 0.91)
        violet_stop = 0.72 + 0.11 * math.cos(self.phase * 0.67)
        sweep.setColorAt(0.0, QColor("#090B10"))
        sweep.setColorAt(coral_stop, QColor(62, 25, 28, 215))
        sweep.setColorAt(0.50, QColor(21, 17, 34, 228))
        sweep.setColorAt(violet_stop, QColor(39, 28, 74, 210))
        sweep.setColorAt(1.0, QColor("#0B0D14"))
        painter.fillRect(self.rect(), sweep)

        cross = QLinearGradient(
            width * (0.85 + 0.18 * math.cos(self.phase * 0.37)),
            height * (-0.10 + 0.20 * math.sin(self.phase * 0.59)),
            width * (0.08 + 0.16 * math.sin(self.phase * 0.49)),
            height * (1.12 + 0.16 * math.cos(self.phase * 0.76)),
        )
        warm_stop = 0.42 + 0.18 * math.sin(self.phase * 0.52 + 1.2)
        cross.setColorAt(0.0, QColor(0, 0, 0, 0))
        cross.setColorAt(warm_stop, QColor(106, 47, 28, 40))
        cross.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), cross)


class HeroCard(QFrame):
    def __init__(self):
        super().__init__()
        load_application_fonts()
        self.setObjectName("recordingStage")
        self.setMinimumSize(480, 420)


class FlowOrb(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(154, 154)
        self.state = "loading"
        self.level = 0.0
        self.visual_level = 0.0
        self.phase = 0.0
        self.theme = "dark"
        self.dance_started_at = 0.0
        self.dance_until = 0.0
        self.animation = QTimer(self)
        self.animation.timeout.connect(self._animate)
        self.animation.start(35)
        self.setCursor(Qt.PointingHandCursor)

    def set_state(self, state: str) -> None:
        self.state = state
        self.update()

    def set_level(self, level: float) -> None:
        self.level = max(0.0, min(1.0, float(level)))
        self.update()

    def set_theme(self, theme: str) -> None:
        self.theme = resolve_theme(theme)
        self.update()

    def start_dance(self, seconds: float = 8.0) -> None:
        now = time.monotonic()
        self.dance_started_at = now
        self.dance_until = now + seconds
        self.update()

    @staticmethod
    def _dance_pose(elapsed: float) -> tuple[float, ...]:
        """Interpolate an eight-beat side-step and alternating-point routine."""
        poses = (
            (0, 0, -53, -10, -62, 9, 53, -10, 62, 9, -25, 52, -34, 67, 25, 52, 35, 67),
            (-8, -4, -55, -18, -67, -35, 46, 2, 62, 15, -20, 51, -10, 68, 22, 51, 39, 64),
            (8, -3, -46, 2, -62, 15, 55, -18, 67, -35, -22, 51, -39, 64, 20, 51, 10, 68),
            (5, -6, -52, -8, -69, -12, 52, -8, 69, -12, -19, 51, -5, 68, 22, 51, 38, 65),
            (-4, -2, -54, -18, -64, -38, 54, -18, 64, -38, -23, 50, -38, 63, 21, 50, 9, 68),
            (0, -7, -52, -14, -69, -28, 52, -14, 69, -28, -20, 51, -7, 69, 20, 51, 7, 69),
            (-7, -3, -48, 1, -69, -11, 53, -16, 63, -36, -22, 51, -39, 65, 19, 51, 5, 68),
            (7, -7, -53, -16, -63, -42, 53, -16, 63, -42, -19, 51, -5, 68, 22, 51, 39, 64),
            (0, 0, -53, -10, -62, 9, 53, -10, 62, 9, -25, 52, -34, 67, 25, 52, 35, 67),
        )
        beat = max(0.0, min(7.999, elapsed))
        index = int(beat)
        mix = beat - index
        mix = (1.0 - math.cos(mix * math.pi)) * 0.5
        return tuple(a + (b - a) * mix for a, b in zip(poses[index], poses[index + 1]))

    def _animate(self) -> None:
        self.phase += 0.12 if self.state in {"recording", "processing"} else 0.045
        self.visual_level += (self.level - self.visual_level) * 0.18
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.parentWidget().window().pipeline.toggle()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = self.rect().center()
        pulse = (math.sin(self.phase) + 1) / 2

        if self.state in {"recording", "processing", "ready"}:
            glow_radius = 65 + pulse * 5 + self.visual_level * 10
            glow = QRadialGradient(center, glow_radius)
            glow.setColorAt(0.50, QColor(255, 117, 87, 46 if self.state == "ready" else 78))
            glow.setColorAt(1.0, QColor(255, 117, 87, 0))
            painter.setBrush(glow)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(center, int(glow_radius), int(glow_radius))

        now = time.monotonic()
        dancing = now < self.dance_until
        dance_arms = None
        x, y = center.x(), center.y()
        if dancing:
            elapsed = min(7.999, max(0.0, now - self.dance_started_at))
            pose = self._dance_pose(elapsed)
            x += round(pose[0])
            y += round(pose[1])
            limb = QColor("#34332F") if self.theme == "light" else QColor("#F5F3F0")
            accent = QColor("#D95F4A") if self.theme == "light" else QColor("#FF7557")
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(40, 38, 34, 36) if self.theme == "light" else QColor(0, 0, 0, 90))
            painter.drawEllipse(QRectF(x - 48, y + 66, 96, 9))
            painter.setPen(QPen(limb, 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            joints = [QPoint(round(x + pose[i]), round(y + pose[i + 1])) for i in range(2, 18, 2)]
            left_elbow, left_hand, right_elbow, right_hand = joints[:4]
            left_knee, left_foot, right_knee, right_foot = joints[4:]
            left_shoulder, right_shoulder = QPoint(x - 40, y - 1), QPoint(x + 40, y - 1)
            left_hip, right_hip = QPoint(x - 17, y + 43), QPoint(x + 17, y + 43)
            painter.drawLine(left_shoulder, left_elbow)
            painter.drawLine(right_shoulder, right_elbow)
            for start, middle, end in (
                (left_hip, left_knee, left_foot),
                (right_hip, right_knee, right_foot),
            ):
                painter.drawLine(start, middle)
                painter.drawLine(middle, end)
            painter.setPen(QPen(limb, 5, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(left_foot.x() - 5, left_foot.y(), left_foot.x() + 5, left_foot.y())
            painter.drawLine(right_foot.x() - 5, right_foot.y(), right_foot.x() + 5, right_foot.y())
            dance_arms = (left_elbow, left_hand, right_elbow, right_hand, limb, accent)
        orb_center = QPoint(x, y)
        surface = QRadialGradient(orb_center, 60)
        if self.theme == "light":
            surface.setColorAt(0.0, QColor("#FFFDF8"))
            surface.setColorAt(1.0, QColor("#D8D5CD"))
        else:
            surface.setColorAt(0.0, QColor("#252A36"))
            surface.setColorAt(1.0, QColor("#151820"))
        painter.setBrush(surface)
        painter.setPen(QPen(QColor(92, 90, 83, 55) if self.theme == "light" else QColor(255, 255, 255, 32), 1))
        orb_radius = 53 if dancing else 58
        painter.drawEllipse(orb_center, orb_radius, orb_radius)
        if dance_arms:
            left_elbow, left_hand, right_elbow, right_hand, limb, accent = dance_arms
            painter.setPen(QPen(limb, 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(left_elbow, left_hand)
            painter.drawLine(right_elbow, right_hand)
            painter.setBrush(limb)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(left_hand, 4, 4)
            painter.drawEllipse(right_hand, 4, 4)
            painter.setPen(QPen(accent, 2.5, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(left_elbow, left_elbow + QPoint(6, 2))
            painter.drawLine(right_elbow, right_elbow + QPoint(-6, 2))
        mic_color = QColor("#34332F") if self.theme == "light" else QColor(255, 255, 255, 245)
        painter.setPen(QPen(mic_color, 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(x - 7, y - 22, 14, 31), 7, 7)
        painter.setPen(QPen(mic_color, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawArc(QRectF(x - 16, y - 8, 32, 29), 180 * 16, 180 * 16)
        painter.drawLine(x, y + 21, x, y + 31)
        painter.drawLine(x - 8, y + 31, x + 8, y + 31)


class OverlayAudioDot(QWidget):
    """Ambient white idle dot that becomes an audio-reactive gradient orb."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(36, 36)
        self.state = "idle"
        self.level = 0.0
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(33)

    def set_state(self, state: str) -> None:
        self.state = state
        self.update()

    def set_level(self, level: float) -> None:
        self.level = max(0.0, min(1.0, float(level)))
        self.update()

    def _animate(self) -> None:
        self.phase = (self.phase + 2.4 + self.level * 8.0) % 360
        if self.state != "idle":
            self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = self.rect().center()
        if self.state == "idle":
            painter.setPen(QPen(QColor(255, 255, 255, 225), 1.2))
            painter.setBrush(QColor(255, 255, 255, 150))
            painter.drawEllipse(center, 4, 4)
            return

        pulse = (math.sin(math.radians(self.phase * 2)) + 1.0) / 2.0
        radius = 10 + self.level * 2.5 + pulse * 0.75
        glow = QRadialGradient(center, radius + 4)
        glow.setColorAt(0.45, QColor(231, 118, 82, 90 + int(self.level * 50)))
        glow.setColorAt(1.0, QColor(231, 118, 82, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, int(radius + 4), int(radius + 4))

        gradient = QConicalGradient(center, self.phase)
        gradient.setColorAt(0.0, QColor("#FF8A65"))
        gradient.setColorAt(0.34, QColor("#E86BA8"))
        gradient.setColorAt(0.68, QColor("#8B7CF6"))
        gradient.setColorAt(1.0, QColor("#FF8A65"))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(255, 255, 255, 195), 1))
        painter.drawEllipse(center, int(radius), int(radius))

        inner = 2.5 + self.level * 2.5
        painter.setBrush(QColor(255, 255, 255, 205))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, int(inner), int(inner))


class SlidingPreview(QWidget):
    """Single-line preview that glides between rolling ten-word captions."""

    def __init__(self):
        super().__init__()
        self._previous = ""
        self._current = ""
        self._transition = 1.0
        self.setMinimumHeight(20)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        font = QFont("Bahnschrift", 9)
        self.setFont(font)
        self.animation = QPropertyAnimation(self, b"transition", self)
        self.animation.setDuration(240)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)

    def get_transition(self) -> float:
        return self._transition

    def set_transition(self, value: float) -> None:
        self._transition = max(0.0, min(1.0, float(value)))
        self.update()

    transition = Property(float, get_transition, set_transition)

    def set_text(self, text: str) -> None:
        value = text.strip()
        if value == self._current:
            return
        self._previous = self._current
        self._current = value
        self.animation.stop()
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.start()

    def clear(self) -> None:
        self.animation.stop()
        self._previous = ""
        self._current = ""
        self._transition = 1.0
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setClipRect(self.rect())
        metrics = painter.fontMetrics()
        width = max(1, self.width() - 2)
        shift = 20
        base = self.rect().adjusted(0, 0, -2, 0)
        if self._previous and self._transition < 1.0:
            previous = metrics.elidedText(f"… {self._previous}", Qt.ElideLeft, width)
            painter.setOpacity(1.0 - self._transition)
            painter.setPen(QColor(195, 201, 214))
            painter.drawText(
                base.translated(round(-shift * self._transition), 0),
                Qt.AlignLeft | Qt.AlignVCenter,
                previous,
            )
        current = self._current or "Listening for speech…"
        current = metrics.elidedText(f"… {current}" if self._current else current, Qt.ElideLeft, width)
        painter.setOpacity(max(0.15, self._transition))
        painter.setPen(QColor(235, 238, 244))
        painter.drawText(
            base.translated(round(shift * (1.0 - self._transition)), 0),
            Qt.AlignLeft | Qt.AlignVCenter,
            current,
        )


class CompactOverlay(QFrame):
    COLLAPSED_SIZE = (36, 36)
    EXPANDED_SIZE = (420, 64)

    def __init__(self, hotkey: str):
        super().__init__(
            None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._state = "idle"
        self._expanded = False
        self._collapse_after_animation = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.dot = OverlayAudioDot()
        # The dot stays bottom-left in both geometries, giving it one fixed
        # global center while the panel grows upward and to the right.
        layout.addWidget(self.dot, 0, Qt.AlignLeft | Qt.AlignBottom)

        self.text_panel = QWidget()
        text_layout = QVBoxLayout(self.text_panel)
        text_layout.setContentsMargins(4, 7, 14, 7)
        text_layout.setSpacing(2)
        header = QHBoxLayout()
        self.message = QLabel("Listening…")
        self.message.setStyleSheet("font-size: 13px; font-weight: 700; color: #F5F3F0;")
        self.detail = QLabel(hotkey.upper().replace("+", " + "))
        self.detail.setStyleSheet(
            "font-size: 9px; color: rgba(190, 197, 211, 175); letter-spacing: 1px;"
        )
        header.addWidget(self.message)
        header.addStretch()
        header.addWidget(self.detail)
        text_layout.addLayout(header)
        self.preview = SlidingPreview()
        text_layout.addWidget(self.preview)
        layout.addWidget(self.text_panel, 1)
        self.text_panel.hide()

        self.animation = QPropertyAnimation(self, b"geometry", self)
        self.animation.setDuration(190)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.finished.connect(self._animation_finished)
        self.setGeometry(self._target_geometry(False))

    def set_hotkey(self, hotkey: str) -> None:
        self.detail.setText(hotkey.upper().replace("+", " + "))

    def set_level(self, level: float) -> None:
        self.dot.set_level(level)

    def show_idle(self) -> None:
        self._state = "idle"
        self.dot.set_state("idle")
        self.preview.clear()
        self._animate_expansion(False)

    def show_state(self, state: str, message: str) -> None:
        self._state = state
        self.dot.set_state(state)
        self.message.setText(message)
        self.text_panel.show()
        self._animate_expansion(True)

    def show_preview(self, text: str) -> None:
        self.preview.set_text(text)

    def _target_geometry(self, expanded: bool) -> QRect:
        width, height = self.EXPANDED_SIZE if expanded else self.COLLAPSED_SIZE
        screen = QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1280, 720)
        return QRect(area.left() + 22, area.bottom() - height - 22, width, height)

    def _animate_expansion(self, expanded: bool) -> None:
        was_visible = self.isVisible()
        if not was_visible:
            self.setGeometry(self._target_geometry(False if expanded else expanded))
            self.show()
        self._expanded = expanded
        self._collapse_after_animation = not expanded
        self.animation.stop()
        self.animation.setStartValue(self.geometry())
        self.animation.setEndValue(self._target_geometry(expanded))
        self.animation.start()
        self.raise_()

    def _animation_finished(self) -> None:
        if self._collapse_after_animation:
            self.text_panel.hide()
        else:
            self.text_panel.show()

    def paintEvent(self, event) -> None:
        del event
        if not self._expanded:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        panel = QRectF(42, 0, self.width() - 44, self.height())
        painter.setPen(QPen(QColor(255, 255, 255, 38), 1))
        painter.setBrush(QColor(14, 17, 24, 226))
        painter.drawRoundedRect(panel, 25, 25)


class TextCard(QFrame):
    def __init__(self, title: str, copy_button: bool = False):
        super().__init__()
        self.setObjectName("outputSection")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(19, 17, 19, 17)
        header = QHBoxLayout()
        header.addWidget(_label(title, "cardTitle"))
        header.addStretch()
        self.copy_button = None
        if copy_button:
            self.copy_button = QPushButton("COPY")
            self.copy_button.setFixedHeight(32)
            header.addWidget(self.copy_button)
        layout.addLayout(header)
        self.editor = QTextEdit()
        self.editor.setObjectName("transcriptEditor")
        self.editor.setAutoFillBackground(False)
        self.editor.setAttribute(Qt.WA_TranslucentBackground, True)
        self.editor.viewport().setAutoFillBackground(False)
        self.editor.viewport().setAttribute(Qt.WA_TranslucentBackground, True)
        self.editor.setReadOnly(True)
        self.editor.setPlaceholderText("Your words will appear here…")
        layout.addWidget(self.editor)


class AuraFlowWindow(QMainWindow):
    def __init__(self, pipeline: DictationPipeline):
        super().__init__()
        self.pipeline = pipeline
        self.bridge = EventBridge()
        self.bridge.received.connect(self._handle_event)
        self.pipeline.event_callback = self.bridge.received.emit
        self.recording_started: float | None = None
        self.current_category = "other"
        self.current_level = 0.0
        self._background_mode = False
        self._quitting = False
        self._tray_notified = False
        self.hotkeys: GlobalHotkeyController | None = None
        self._fade_animations: dict[QWidget, QPropertyAnimation] = {}
        self._konami: list[int] = []
        self.current_theme = resolve_theme(self.pipeline.config.theme_mode)
        self.theme_colors = THEME_COLORS[self.current_theme]
        self.setWindowTitle(f"yapper_ · v{VERSION}")
        self.setMinimumSize(1040, 700)
        self.resize(1480, 900)
        self.setStyleSheet(stylesheet_for(self.pipeline.config.theme_mode))
        self.setWindowIcon(self._app_icon())
        self._process = psutil.Process(os.getpid())
        self._process.cpu_percent(None)
        self._build()
        self._create_tray()
        self._bind_hotkeys()
        self.clock = QTimer(self)
        self.clock.timeout.connect(self._tick)
        self.clock.start(100)
        self.context_timer = QTimer(self)
        self.context_timer.timeout.connect(self.pipeline.poll_context)
        self.context_timer.start(600)
        self.resource_timer = QTimer(self)
        self.resource_timer.timeout.connect(self._update_resource_usage)
        self.resource_timer.start(2_000)
        self._update_resource_usage()
        QTimer.singleShot(0, self.pipeline.start)

    def _build(self) -> None:
        self.canvas = DashboardCanvas()
        self.setCentralWidget(self.canvas)
        outer = QVBoxLayout(self.canvas)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        header = QHBoxLayout()
        brand_column = QVBoxLayout()
        brand_column.setSpacing(4)
        self.brand = _brand_label()
        self.brand.underscore_clicked.connect(self._start_dance)
        brand_column.addWidget(self.brand)
        brand_column.addWidget(_label("PRIVATE  ·  LOCAL  ·  YOURS", "eyebrow"))
        header.addLayout(brand_column)
        header.addStretch()
        self.theme_button = QPushButton("")
        self.theme_button.setObjectName("ghostButton")
        self.theme_button.setAccessibleName("Switch to light theme" if self.current_theme == "dark" else "Switch to dark theme")
        self.theme_button.setToolTip(self.theme_button.accessibleName())
        self.theme_button.setFixedWidth(44)
        self.theme_button.setIcon(_theme_icon(self.current_theme == "dark", self.theme_colors["muted"]))
        self.theme_button.clicked.connect(self._toggle_theme)
        header.addWidget(self.theme_button)
        self.model_badge = QPushButton("OFFLINE")
        self.model_badge.setObjectName("connectionButton")
        self.model_badge.setFixedWidth(105)
        self.model_badge.setCursor(Qt.PointingHandCursor)
        self.model_badge.setToolTip("Open API connection settings")
        self.model_badge.clicked.connect(self._toggle_connection_mode)
        header.addWidget(self.model_badge)
        self.history_button = QPushButton("HISTORY")
        self.history_button.setObjectName("ghostButton")
        self.history_button.clicked.connect(self.open_history)
        header.addWidget(self.history_button)
        self.personalize_button = QPushButton("PERSONALIZE")
        self.personalize_button.setObjectName("ghostButton")
        self.personalize_button.clicked.connect(self.open_personalization)
        header.addWidget(self.personalize_button)
        self.clock_label = _label("--:--:--", "eyebrow")
        header.addWidget(self.clock_label)
        outer.addLayout(header)

        self.view_stack = QStackedWidget()
        dashboard = QWidget()
        dashboard.setObjectName("dashboardPage")
        dashboard_layout = QVBoxLayout(dashboard)
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        dashboard_layout.setSpacing(14)

        body = QSplitter(Qt.Horizontal)
        body.setHandleWidth(7)
        body.setChildrenCollapsible(False)
        body.setOpaqueResize(True)
        self.stats_card = self._build_stats()
        body.addWidget(self.stats_card)
        self.hero_card = self._build_hero()
        body.addWidget(self.hero_card)
        self.right_column = self._build_output_column()
        body.addWidget(self.right_column)
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 2)
        body.setStretchFactor(2, 2)
        body.setSizes([230, 600, 600])
        self.body_splitter = body
        dashboard_layout.addWidget(body, 1)
        self.control_dock = self._build_dock()
        dashboard_layout.addWidget(self.control_dock)
        self.view_stack.addWidget(dashboard)
        self.personalization_panel = PersonalizationPanel(
            self.pipeline,
            self._settings_saved,
            self._show_main_dashboard,
            self._run_calibration,
            self.open_history_entry,
        )
        self.view_stack.addWidget(self.personalization_panel)
        self.history_panel = HistoryPanel(
            self.pipeline,
            self._show_main_dashboard,
            self._open_feedback_entry,
        )
        self.view_stack.addWidget(self.history_panel)
        outer.addWidget(self.view_stack, 1)
        self.overlay = CompactOverlay(self.pipeline.config.hotkey)
        self.canvas.set_theme(self.current_theme)
        self.orb.set_theme(self.current_theme)
        self._apply_theme(self.pipeline.config.theme_mode, persist=False)
        self._refresh_connection_badge()
        self._update_stats(self.pipeline.usage_stats())

    def _build_stats(self) -> QFrame:
        card = QFrame()
        card.setObjectName("statSection")
        card.setMinimumWidth(210)
        card.setMaximumWidth(275)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 20)
        layout.setSpacing(8)
        layout.addWidget(_label("VOICE ENGINE", "cardTitle"))
        active = QHBoxLayout()
        self.health_dot = QLabel("●")
        self.health_dot.setStyleSheet("color: #9C8B7F;")
        self.health_label = QLabel("Starting")
        self.health_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        active.addWidget(self.health_dot)
        active.addWidget(self.health_label)
        active.addStretch()
        layout.addLayout(active)
        layout.addSpacing(12)
        self.stat_labels: dict[str, QLabel] = {}
        for key, title, suffix in (
            ("words_today", "WORDS TODAY", ""),
            ("speaking_wpm", "SPEAKING SPEED", " wpm"),
            ("time_saved_minutes", "TIME SAVED TODAY", " min"),
            ("total_words", "TOTAL WORDS", ""),
        ):
            layout.addWidget(_label(title, "cardTitle"))
            value = _label("0" + suffix, "bigStat")
            value.setProperty("suffix", suffix)
            layout.addWidget(value)
            self.stat_labels[key] = value
            layout.addSpacing(6)
        layout.addStretch()
        layout.addWidget(_label("AUDIO LEVEL", "cardTitle"))
        self.audio_level = QProgressBar()
        self.audio_level.setRange(0, 100)
        self.audio_level.setTextVisible(False)
        self.audio_animation = QPropertyAnimation(self.audio_level, b"value", self)
        self.audio_animation.setDuration(120)
        self.audio_animation.setEasingCurve(QEasingCurve.OutCubic)
        layout.addWidget(self.audio_level)
        self.system_label = _label("GPU checking  ·  context checking", "metric")
        self.system_label.setWordWrap(True)
        layout.addWidget(self.system_label)
        self.resource_label = _label("CPU —  ·  RAM —  ·  VRAM —", "resourceMetric")
        self.resource_label.setWordWrap(True)
        layout.addWidget(self.resource_label)
        return card

    def _build_hero(self) -> QFrame:
        card = HeroCard()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(26, 22, 26, 26)
        top = QHBoxLayout()
        self.target_label = _label("Waiting for target app", "eyebrow")
        top.addWidget(self.target_label)
        top.addStretch()
        self.context_badge = QPushButton("CONTEXT · CHECKING")
        self.context_badge.setEnabled(False)
        top.addWidget(self.context_badge)
        layout.addLayout(top)
        layout.addStretch()
        center = QHBoxLayout()
        center.setSpacing(28)
        state_column = QVBoxLayout()
        self.state_label = _label("●  LOADING", "statusText", Qt.AlignRight)
        self.timer_label = _label("00:00.0", "timer", Qt.AlignRight)
        state_column.addWidget(self.state_label)
        state_column.addWidget(self.timer_label)
        center.addLayout(state_column, 1)
        self.orb = FlowOrb()
        center.addWidget(self.orb)
        hint_column = QVBoxLayout()
        self.hotkey_label = _label(self.pipeline.config.hotkey.upper().replace("+", " + "), "cardTitle")
        self.mode_hint = _label("hold to talk", "hint")
        hint_column.addWidget(self.hotkey_label)
        hint_column.addWidget(self.mode_hint)
        center.addLayout(hint_column, 1)
        layout.addLayout(center)
        layout.addSpacing(20)
        self.hero_status = _label("Loading the local speech engine…", "hint", Qt.AlignCenter)
        self.hero_status.setWordWrap(True)
        layout.addWidget(self.hero_status)
        self.primary_button = QPushButton("PLEASE WAIT")
        self.primary_button.setObjectName("accentButton")
        self.primary_button.setEnabled(False)
        self.primary_button.setFixedWidth(190)
        self.primary_button.clicked.connect(self.pipeline.toggle)
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.primary_button)
        button_row.addStretch()
        layout.addLayout(button_row)
        layout.addStretch()
        self.timing_label = _label("ASR —  FORMAT —  INSERT —", "metric", Qt.AlignCenter)
        self.timing_label.setToolTip(
            "ASR: audio → raw text  ·  FORMAT: cleanup and layout  ·  "
            "INSERT: placing finished text into the target app"
        )
        layout.addWidget(self.timing_label)
        return card

    def _build_output_column(self) -> QWidget:
        container = QWidget()
        container.setMinimumWidth(460)
        container.setMaximumWidth(760)
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        output_row = QVBoxLayout()
        output_row.setSpacing(16)
        self.raw_card = TextCard("RAW DICTATION", copy_button=True)
        self.raw_card.setMinimumHeight(170)
        self.raw_card.copy_button.setText("COPY RAW")
        self.raw_card.copy_button.clicked.connect(self._copy_raw)
        output_row.addWidget(self.raw_card, 1)

        self.final_card = TextCard("FINISHED OUTPUT", copy_button=True)
        self.final_card.setMinimumHeight(170)
        self.final_card.copy_button.setText("COPY OUTPUT")
        self.final_card.copy_button.clicked.connect(self._copy_final)
        output_row.addWidget(self.final_card, 1)
        layout.addLayout(output_row, 1)

        formatter = QFrame()
        formatter.setObjectName("outputSection")
        formatter_layout = QVBoxLayout(formatter)
        formatter_layout.setContentsMargins(19, 12, 19, 12)
        title_row = QHBoxLayout()
        title_row.addWidget(_label("CLEANUP MODE", "cardTitle"))
        self.formatter_state = _label("AI LOADING", "deviceReady")
        title_row.addStretch()
        title_row.addWidget(self.formatter_state)
        formatter_layout.addLayout(title_row)
        cleanup_well = QFrame()
        cleanup_well.setObjectName("cleanupWell")
        level_row = QHBoxLayout(cleanup_well)
        level_row.setContentsMargins(12, 9, 12, 9)
        self.cleanup_combo = QComboBox()
        self.cleanup_tooltips = {
            "minimal": "Word-preserving · punctuation, capitalization, spacing, commands, lists, and saved replacements.",
            "smart": "AI cleanup · removes speech-only filler and resolves clear corrections while preserving your voice.",
        }
        for label, level in (
            ("Minimal", "minimal"),
            ("Smart", "smart"),
        ):
            self.cleanup_combo.addItem(label, level)
            index = self.cleanup_combo.count() - 1
            self.cleanup_combo.setItemData(index, self.cleanup_tooltips[level], Qt.ToolTipRole)
        self.cleanup_combo.view().setMouseTracking(True)
        selected_level = self.pipeline.config.cleanup_level
        selected_index = self.cleanup_combo.findData(selected_level)
        self.cleanup_combo.setCurrentIndex(max(0, selected_index))
        self.cleanup_combo.setToolTip(self.cleanup_tooltips[selected_level])
        self.cleanup_combo.currentIndexChanged.connect(
            lambda index: self._cleanup_changed(str(self.cleanup_combo.itemData(index) or ""))
        )
        level_row.addWidget(self.cleanup_combo)
        self.cleanup_description = _label(
            self.cleanup_tooltips[self.pipeline.config.cleanup_level], "hint"
        )
        self.cleanup_description.setWordWrap(True)
        level_row.addWidget(self.cleanup_description, 1)
        formatter_layout.addWidget(cleanup_well)
        layout.addWidget(formatter)
        return container

    def _build_dock(self) -> QFrame:
        dock = QFrame()
        dock.setObjectName("controlBar")
        layout = QHBoxLayout(dock)
        layout.setContentsMargins(20, 14, 20, 14)
        self.push_button = QPushButton("SMART ALT+Z")
        self.push_button.setObjectName("modeButton")
        self.push_button.setCheckable(True)
        self.push_button.clicked.connect(lambda: self._set_recording_mode("smart"))
        self.hands_button = QPushButton("HANDS-FREE")
        self.hands_button.setObjectName("modeButton")
        self.hands_button.setCheckable(True)
        self.hands_button.clicked.connect(lambda: self._set_recording_mode("hands_free"))
        layout.addWidget(self.push_button)
        layout.addWidget(self.hands_button)
        layout.addStretch()

        engine_column = QVBoxLayout()
        engine_column.addWidget(_label("TRANSCRIPTION MODEL", "fieldTitle"))
        self.engine_combo = QComboBox()
        app_dir = APP_DIR
        complete = [
            model for model in discover_models(app_dir)
            if model.complete and model.name in {"medium", "tiny.en"}
        ]
        complete.sort(key=lambda model: (not model.path.is_relative_to(MODELS_DIR), model.name))
        self.engine_models = {}
        for model in complete:
            self.engine_models.setdefault(model.name, model.path)
        if not self.engine_models:
            self.engine_models["medium"] = MODELS_DIR / "faster-whisper-medium"
        selected_index = 0
        for name in self.engine_models:
            display_name = "Tiny" if name == "tiny.en" else "Medium"
            self.engine_combo.addItem(display_name, name)
            if name == self.pipeline.config.model_name:
                selected_index = self.engine_combo.count() - 1
        self.engine_combo.setCurrentIndex(selected_index)
        self.engine_combo.setFixedWidth(120)
        self.engine_combo.setToolTip(
            "Medium uses Tiny for live preview and Medium for the final pass. Tiny English uses one fast shared engine."
        )
        self.engine_combo.currentIndexChanged.connect(self._engine_changed)
        engine_column.addWidget(self.engine_combo)
        layout.addLayout(engine_column)
        layout.addSpacing(18)

        microphone_column = QVBoxLayout()
        microphone_column.addWidget(_label("MICROPHONE", "fieldTitle"))
        self.microphone_combo = QComboBox()
        self.microphone_combo.setFixedWidth(380)
        self._load_microphones()
        self.microphone_combo.currentIndexChanged.connect(self._microphone_changed)
        microphone_column.addWidget(self.microphone_combo)
        layout.addLayout(microphone_column)
        layout.addStretch()
        self.feedback_button = QPushButton("Feedback")
        self.feedback_button.setObjectName("ghostButton")
        self.feedback_button.clicked.connect(self._open_feedback)
        self.coffee_button = QPushButton("Buy me a coffee")
        self.coffee_button.setObjectName("ghostButton")
        self.coffee_button.clicked.connect(self._open_coffee)
        self.coffee_button.setIcon(_coffee_icon(self.theme_colors["muted"]))
        layout.addWidget(self.feedback_button, 0, Qt.AlignBottom)
        layout.addWidget(self.coffee_button, 0, Qt.AlignBottom)
        self._sync_mode_buttons()
        return dock

    def _create_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        menu = QMenu()
        show_action = QAction("Show yapper_", self)
        toggle_action = QAction("Start / stop dictation", self)
        quit_action = QAction("Quit", self)
        show_action.triggered.connect(self._show_dashboard)
        toggle_action.triggered.connect(self.pipeline.toggle)
        quit_action.triggered.connect(self._quit)
        menu.addAction(show_action)
        menu.addAction(toggle_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setToolTip("yapper_ · private local dictation")
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._show_dashboard() if reason == QSystemTrayIcon.DoubleClick else None
        )
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _bind_hotkeys(self) -> None:
        if self.hotkeys:
            self.hotkeys.unbind()
        self.hotkeys = GlobalHotkeyController(
            self.pipeline.config.hotkey,
            lambda: self.bridge.received.emit({"type": "hotkey_press"}),
            lambda: self.bridge.received.emit({"type": "hotkey_release"}),
            lambda: self.bridge.received.emit({"type": "toggle"}),
            lambda: self.bridge.received.emit({"type": "hands_free_latched"}),
            self.pipeline.config.hotkey_double_tap_seconds,
            lambda: self.bridge.received.emit({"type": "paste_last"}),
        )
        try:
            self.hotkeys.bind(self.pipeline.config.recording_mode)
        except Exception as exc:
            self._handle_event({"type": "error", "message": f"Global hotkey unavailable: {exc}"})

    def _handle_event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "hotkey_press":
            if self.pipeline.config.recording_mode in {"push_to_talk", "smart"}:
                self.pipeline.start_recording()
        elif kind == "hotkey_release":
            if self.pipeline.config.recording_mode in {"push_to_talk", "smart"}:
                self.pipeline.stop_recording()
        elif kind == "toggle":
            self.pipeline.toggle()
        elif kind == "paste_last":
            self.pipeline.paste_latest_final()
        elif kind == "hands_free_latched":
            self.hero_status.setText("Hands-free latched — tap Alt + Z to stop")
            if self._overlay_enabled():
                self.overlay.show_state("recording", "Hands-free listening…")
        elif kind == "state":
            self._apply_state(str(event.get("state", "")))
        elif kind == "status":
            message = str(event.get("message", ""))
            self.hero_status.setText(message)
            self._pulse(self.hero_status)
            if self._overlay_enabled() and self.pipeline.state == PipelineState.PROCESSING:
                self.overlay.show_state("processing", message)
        elif kind == "level":
            self.current_level = float(event.get("value", 0))
            self.canvas.set_level(self.current_level)
            self.audio_animation.stop()
            self.audio_animation.setStartValue(self.audio_level.value())
            self.audio_animation.setEndValue(round(self.current_level * 100))
            self.audio_animation.start()
            self.orb.set_level(self.current_level)
            self.overlay.set_level(self.current_level)
        elif kind == "model":
            device = str(event.get("device", ""))
            compute = str(event.get("compute_type", ""))
            self._refresh_connection_badge()
            self.system_label.setText(
                f"{event.get('name')}  ·  {device}/{compute}  ·  private local processing"
            )
            self.health_dot.setStyleSheet(f"color: {self.theme_colors['green']};")
            self.health_label.setText("Active")
        elif kind == "raw":
            self.raw_card.editor.setPlainText(str(event.get("text", "")))
        elif kind == "partial":
            cumulative = str(event.get("text", ""))
            if cumulative != self.raw_card.editor.toPlainText():
                self.raw_card.editor.setPlainText(cumulative)
                self.raw_card.editor.moveCursor(QTextCursor.End)
                self.raw_card.editor.ensureCursorVisible()
            if self._overlay_enabled() and self.pipeline.state == PipelineState.RECORDING:
                self.overlay.show_preview(str(event.get("preview", "")))
        elif kind == "partial_status":
            if "unavailable" in str(event.get("message", "")).lower():
                self.hero_status.setText(str(event.get("message", "")))
        elif kind == "semantic_status":
            ready = bool(event.get("ready"))
            self.formatter_state.setText("AI READY" if ready else "AI UNAVAILABLE")
            message = str(event.get("message", ""))
            if self.pipeline.config.cleanup_level == "smart":
                self.cleanup_description.setText(
                    f"{message} · preservation checks active" if ready else message
                )
        elif kind == "final":
            self.final_card.editor.setPlainText(str(event.get("text", "")))
            method = str(event.get("cleanup", "safe-local"))
            level = str(event.get("level", self.pipeline.config.cleanup_level))
            state_labels = {
                "local-minimal": "MINIMAL",
                "ai-smart": "SMART",
                "safe-verbatim": "EXACT SNIPPET",
            }
            self.formatter_state.setText(state_labels.get(method, method.replace("-", " ").upper()))
            if event.get("fallback"):
                self.formatter_state.setText("SAFE FALLBACK")
                self.cleanup_description.setText(self._cleanup_reason(str(event.get("detail", "")), method))
            elif method == "ai-smart":
                self.cleanup_description.setText(
                    f"{self.cleanup_tooltips.get(level, '')} · preservation checks passed"
                )
            else:
                self.cleanup_description.setText(self.cleanup_tooltips.get(level, ""))
            self._pulse(self.formatter_state)
        elif kind == "context":
            ready = bool(event.get("accessibility"))
            self.context_badge.setText("CONTEXT · READY" if ready else "CONTEXT · LIMITED")
        elif kind == "context_target":
            self.current_category = str(event.get("category", "other"))
            app = _friendly_app_name(str(event.get("app", "")))
            self.target_label.setText(f"Typing into  ·  {app}")
        elif kind == "timing":
            self.timing_label.setText(
                f"ASR {event.get('asr_ms', 0):.0f} ms   ·   "
                f"FORMAT {event.get('format_ms', 0):.0f} ms   ·   "
                f"INSERT {event.get('insert_ms', 0):.0f} ms"
            )
        elif kind == "history":
            self._update_stats(event.get("stats", {}))
        elif kind == "insertion":
            if event.get("success") and self._overlay_enabled():
                self.overlay.show_state("ready", "Inserted")
                QTimer.singleShot(900, self._restore_idle_overlay)
            elif not event.get("success") and self._overlay_enabled():
                self.overlay.show_state("error", str(event.get("message", "Insertion failed")))
        elif kind == "error":
            message = str(event.get("message", "Unknown error"))
            self.hero_status.setText(message)
            self.state_label.setText("●  ERROR")
            self.state_label.setStyleSheet(f"color: {self.theme_colors['red']};")
            self._pulse(self.state_label)
            if self._overlay_enabled():
                self.overlay.show_state("error", message)

    def _apply_state(self, state: str) -> None:
        self.orb.set_state(state)
        self.canvas.set_state(state)
        if state == "ready":
            self.state_label.setText("●  READY")
            self.state_label.setStyleSheet(f"color: {self.theme_colors['green']};")
            self.primary_button.setText("START DICTATING")
            self.primary_button.setEnabled(True)
            self.recording_started = None
            if self._overlay_enabled() and self.overlay._state != "ready":
                self.overlay.show_idle()
        elif state == "recording":
            self.state_label.setText("●  LISTENING")
            self.state_label.setStyleSheet(f"color: {self.theme_colors['accent']};")
            self.primary_button.setText("STOP")
            self.primary_button.setEnabled(True)
            self.recording_started = time.monotonic()
            self.raw_card.editor.clear()
            self.final_card.editor.clear()
            if self._overlay_enabled():
                self.overlay.show_preview("")
                self.overlay.show_state("recording", "Listening…")
        elif state == "processing":
            self.state_label.setText("●  PROCESSING")
            self.state_label.setStyleSheet(f"color: {self.theme_colors['accent_alt']};")
            self.primary_button.setText("WORKING")
            self.primary_button.setEnabled(False)
            if self._overlay_enabled():
                self.overlay.show_state("processing", "Transcribing…")
        elif state == "loading":
            self.primary_button.setText("PLEASE WAIT")
            self.primary_button.setEnabled(False)
        elif state in {"error", "closed"}:
            self.primary_button.setText(state.upper())
            self.primary_button.setEnabled(False)
        self._pulse(self.state_label)

    def _tick(self) -> None:
        self.clock_label.setText(time.strftime("%H:%M:%S"))
        if self.recording_started is not None:
            elapsed = time.monotonic() - self.recording_started
            self.timer_label.setText(f"{int(elapsed // 60):02d}:{elapsed % 60:04.1f}")
        elif self.pipeline.state != PipelineState.PROCESSING:
            self.timer_label.setText("00:00.0")

    def _update_stats(self, stats: dict) -> None:
        for key, label in self.stat_labels.items():
            value = int(stats.get(key, 0) or 0)
            suffix = label.property("suffix") or ""
            label.setText(f"{value:,}{suffix}")

    def _set_recording_mode(self, mode: str) -> None:
        if self.pipeline.state == PipelineState.RECORDING:
            self.pipeline.stop_recording()
        self.pipeline.config.recording_mode = mode
        self.pipeline.config.save()
        self._sync_mode_buttons()
        self._bind_hotkeys()

    def _sync_mode_buttons(self) -> None:
        smart = self.pipeline.config.recording_mode == "smart"
        self.push_button.setChecked(smart)
        self.hands_button.setChecked(self.pipeline.config.recording_mode == "hands_free")
        self.mode_hint.setText(
            "hold once · double-tap to latch" if smart else "tap to start / stop"
        )

    def _cleanup_changed(self, level: str) -> None:
        if not level:
            return
        self.pipeline.config.cleanup_level = level
        self.pipeline.config.save()
        description = self.cleanup_tooltips.get(level, "")
        self.cleanup_combo.setToolTip(description)
        self.cleanup_description.setText(description)
        self.formatter_state.setText("SMART SELECTED" if level == "smart" else "MINIMAL")

    def _load_microphones(self) -> None:
        self.microphone_combo.blockSignals(True)
        self.microphone_combo.clear()
        self.microphone_combo.addItem("System default", None)
        try:
            import sounddevice as sd

            for index, device in enumerate(sd.query_devices()):
                if int(device.get("max_input_channels", 0)) > 0:
                    full_name = str(device.get("name", f"Device {index}"))
                    self.microphone_combo.addItem(full_name, index)
                    self.microphone_combo.setItemData(
                        self.microphone_combo.count() - 1, full_name, Qt.ToolTipRole
                    )
            configured = self.pipeline.config.audio_device
            for index in range(self.microphone_combo.count()):
                if self.microphone_combo.itemData(index) == configured:
                    self.microphone_combo.setCurrentIndex(index)
                    break
        except Exception:
            pass
        self.microphone_combo.blockSignals(False)
        self.microphone_combo.setToolTip(self.microphone_combo.currentText())

    def _microphone_changed(self, index: int) -> None:
        self.microphone_combo.setToolTip(self.microphone_combo.itemText(index))
        self.pipeline.set_audio_device(self.microphone_combo.itemData(index))

    def _engine_changed(self, index: int) -> None:
        name = str(self.engine_combo.itemData(index) or "")
        path = self.engine_models.get(name)
        if not name or not path or name == self.pipeline.config.model_name:
            return
        self.pipeline.config.model_name = name
        self.pipeline.config.model_path = str(path.resolve())
        self.pipeline.config.save()
        self.hero_status.setText(f"{name} selected · restart yapper_ to load it")

    def _copy_final(self) -> None:
        QApplication.clipboard().setText(self.final_card.editor.toPlainText())
        self.hero_status.setText("Finished output copied")

    def _copy_raw(self) -> None:
        QApplication.clipboard().setText(self.raw_card.editor.toPlainText())
        self.hero_status.setText("Raw dictation copied")

    def _apply_theme(self, mode: str, persist: bool = True) -> None:
        if mode not in {"system", "light", "dark"}:
            mode = "dark"
        if persist:
            self.pipeline.config.theme_mode = mode
            self.pipeline.config.save()
        self.current_theme = resolve_theme(mode)
        self.theme_colors = THEME_COLORS[self.current_theme]
        self.setStyleSheet(stylesheet_for(mode))
        self.canvas.set_theme(self.current_theme)
        self.orb.set_theme(self.current_theme)
        self.theme_button.setIcon(_theme_icon(self.current_theme == "dark", self.theme_colors["muted"]))
        self.coffee_button.setIcon(_coffee_icon(self.theme_colors["muted"]))
        if hasattr(self, "personalization_panel"):
            index = self.personalization_panel.theme_combo.findData(mode)
            if index >= 0:
                self.personalization_panel.theme_combo.setCurrentIndex(index)
        for widget, blur, y_offset in (
            (self.raw_card, 28, 7),
            (self.final_card, 28, 7),
            (self.control_dock, 34, 9),
            (self.orb, 26, 7),
        ):
            if self.current_theme == "light":
                effect = QGraphicsDropShadowEffect(widget)
                effect.setBlurRadius(blur)
                effect.setOffset(0, y_offset)
                effect.setColor(QColor(64, 60, 52, 54))
                widget.setGraphicsEffect(effect)
            else:
                widget.setGraphicsEffect(None)
        action = "light" if self.current_theme == "dark" else "dark"
        self.theme_button.setAccessibleName(f"Switch to {action} theme")
        self.theme_button.setToolTip(self.theme_button.accessibleName())
        self._apply_state(self.pipeline.state.value)

    def _toggle_theme(self) -> None:
        self._apply_theme("light" if self.current_theme == "dark" else "dark")

    def _open_feedback(self) -> None:
        FeedbackDialog(self.pipeline, self).exec()

    def _open_feedback_entry(self, entry: dict[str, object]) -> None:
        FeedbackDialog(self.pipeline, self, entry).exec()

    def _open_coffee(self) -> None:
        CoffeeDialog(self.pipeline.config, self).exec()

    def _start_dance(self) -> None:
        self.orb.start_dance(8.0)
        self.hero_status.setText("Never gonna give this mic up…")
        path = discover_rick_media(video=False)
        if path:
            previous = getattr(self, "_rick_audio", None)
            if previous and previous.isRunning():
                previous.stop()
                previous.wait(500)
            self._rick_audio = AudioPlaybackWorker(path, max_seconds=8.0, parent=self)
            self._rick_audio.failed.connect(
                lambda message: self.hero_status.setText(f"Dance audio unavailable · {message}")
            )
            self._rick_audio.start()

    def _run_calibration(self) -> None:
        path = discover_rick_media(video=True)
        if not path:
            QMessageBox.information(
                self,
                "Rickroll media not found",
                "Add a Rick MP4 to the project folder or its assets folder, then try again.",
            )
            return
        screen = RickrollScreen(path, self)
        screen.playback_failed.connect(
            lambda message: QMessageBox.warning(self, "Video playback", message)
        )
        self._rick_screen = screen
        screen.start()

    def open_history_entry(self, entry_id: str) -> None:
        self.history_panel.refresh()
        self.history_panel.select_entry(entry_id)
        self.view_stack.setCurrentWidget(self.history_panel)

    def open_history(self) -> None:
        self.history_panel.refresh()
        self.view_stack.setCurrentWidget(self.history_panel)

    def open_personalization(self) -> None:
        self.personalization_panel.refresh_stats()
        self.view_stack.setCurrentIndex(1)
        self.personalize_button.setText("DASHBOARD")
        self.personalize_button.clicked.disconnect()
        self.personalize_button.clicked.connect(self._show_main_dashboard)

    def open_api_connection(self) -> None:
        self.open_personalization()
        self.personalization_panel._select_page(6)

    def _toggle_connection_mode(self) -> None:
        config = self.pipeline.config
        if self.personalization_panel.connection_ready():
            config.api_enabled = False
            config.save()
            self.pipeline.reload_api_formatter()
            self._refresh_connection_badge()
            self.hero_status.setText("Offline mode · AI cleanup is local")
            return
        if self.personalization_panel.saved_connection_available():
            config.api_enabled = True
            config.save()
            self.pipeline.reload_api_formatter()
            self._refresh_connection_badge()
            self.hero_status.setText(
                f"Online mode · {config.api_provider} · {config.api_model}"
            )
            return
        config.api_enabled = False
        self.open_api_connection()

    def _refresh_connection_badge(self) -> None:
        online = (
            hasattr(self, "personalization_panel")
            and self.personalization_panel.connection_ready()
        )
        self.model_badge.setText("ONLINE" if online else "OFFLINE")
        self.model_badge.setProperty("online", bool(online))
        if online:
            config = self.pipeline.config
            self.model_badge.setToolTip(
                f"{config.api_provider} · {config.api_model}\nClick to change the connection"
            )
        else:
            if (
                hasattr(self, "personalization_panel")
                and self.personalization_panel.saved_connection_available()
            ):
                config = self.pipeline.config
                self.model_badge.setToolTip(
                    f"Offline · saved {config.api_provider} profile\nClick to go online"
                )
            else:
                self.model_badge.setToolTip("Fully local · click to add an API")
        self.model_badge.style().unpolish(self.model_badge)
        self.model_badge.style().polish(self.model_badge)

    def _show_main_dashboard(self) -> None:
        self.view_stack.setCurrentIndex(0)
        self.personalize_button.setText("PERSONALIZE")
        self.personalize_button.clicked.disconnect()
        self.personalize_button.clicked.connect(self.open_personalization)

    def _show_first_run_model_setup(self) -> None:
        if self.pipeline.config.model_setup_completed:
            return
        self.open_personalization()
        self.personalization_panel._select_page(5)

    def _settings_saved(self) -> None:
        self.pipeline.context.set_enabled(self.pipeline.config.context_awareness)
        self.pipeline.inserter.set_direct_enabled(self.pipeline.config.direct_insertion)
        if self.pipeline.config.partial_transcription and not self.pipeline.partial.ready:
            self.pipeline.partial.load_async(
                lambda message: self.pipeline.emit("partial_status", message=message)
            )
        elif not self.pipeline.config.partial_transcription:
            self.pipeline.partial.stop_session()
        self._refresh_connection_badge()
        self._apply_theme(self.pipeline.config.theme_mode, persist=False)
        QApplication.instance().setQuitOnLastWindowClosed(
            not (
                self.pipeline.config.close_to_tray
                and QSystemTrayIcon.isSystemTrayAvailable()
            )
        )
        self._sync_mode_buttons()
        self._bind_hotkeys()
        self.overlay.set_hotkey(self.pipeline.config.hotkey)
        self.hero_status.setText("Personalization saved")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        sequence = [
            Qt.Key_Up, Qt.Key_Up, Qt.Key_Down, Qt.Key_Down,
            Qt.Key_Left, Qt.Key_Right, Qt.Key_Left, Qt.Key_Right,
            Qt.Key_B, Qt.Key_A,
        ]
        self._konami.append(int(event.key()))
        self._konami = self._konami[-len(sequence):]
        if self._konami == [int(key) for key in sequence]:
            self.canvas.set_retro(True)
            self.hero_status.setText("1996 precision mode unlocked")
            self._konami.clear()
            QTimer.singleShot(18_000, lambda: self.canvas.set_retro(False))
        super().keyPressEvent(event)

    def _update_resource_usage(self) -> None:
        try:
            cpu = self._process.cpu_percent(None) / max(1, psutil.cpu_count() or 1)
            ram_mb = self._process.memory_info().rss / (1024 * 1024)
            vram = "N/A"
            try:
                import torch

                if torch.cuda.is_available():
                    vram = f"{torch.cuda.memory_allocated() / (1024 ** 2):.0f} MB"
            except Exception:
                pass
            compact_vram = vram.replace(" MB", "M")
            self.resource_label.setText(
                f"CPU {cpu:.1f}%  ·  RAM {ram_mb:.0f}M  ·  VRAM {compact_vram}"
            )
        except (psutil.Error, RuntimeError):
            self.resource_label.setText("APP RESOURCE USE UNAVAILABLE")

    def _overlay_enabled(self) -> bool:
        return self._background_mode and self.pipeline.config.show_compact_overlay

    def _restore_idle_overlay(self) -> None:
        if self._overlay_enabled():
            self.overlay.show_idle()
        else:
            self.overlay.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.stats_card.setVisible(self.width() >= 1120)
        self.right_column.setMinimumWidth(400 if self.width() < 1260 else 520)
        self.microphone_combo.setFixedWidth(300 if self.width() < 1260 else 380)

    def closeEvent(self, event: QCloseEvent) -> None:
        if (
            not self._quitting
            and self.pipeline.config.close_to_tray
            and QSystemTrayIcon.isSystemTrayAvailable()
        ):
            event.ignore()
            self._background_mode = True
            self.hide()
            if self.pipeline.config.show_compact_overlay:
                if self.pipeline.state == PipelineState.RECORDING:
                    self.overlay.show_state("recording", "Listening…")
                elif self.pipeline.state == PipelineState.PROCESSING:
                    self.overlay.show_state("processing", "Transcribing…")
                else:
                    self.overlay.show_idle()
            if not self._tray_notified:
                self.tray.showMessage(
                    "yapper_ is still running",
                    f"Use {self.pipeline.config.hotkey.upper()} or the tray menu to return.",
                    QSystemTrayIcon.Information,
                    2500,
                )
                self._tray_notified = True
            return
        self._shutdown()
        event.accept()

    def _show_dashboard(self) -> None:
        self._background_mode = False
        self.overlay.hide()
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _animate_intro(self, widget: QWidget) -> None:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(420)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.finished.connect(lambda: widget.setGraphicsEffect(None))
        self._intro_animation = animation
        animation.start()

    def _pulse(self, widget: QWidget) -> None:
        previous = self._fade_animations.pop(widget, None)
        if previous is not None:
            previous.stop()
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(220)
        animation.setStartValue(0.38)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.finished.connect(
            lambda: widget.setGraphicsEffect(None)
            if widget.graphicsEffect() is effect
            else None
        )
        self._fade_animations[widget] = animation
        animation.start()

    @staticmethod
    def _cleanup_reason(detail: str, method: str) -> str:
        lowered = detail.casefold()
        if "protected literal" in lowered:
            return "The AI formatter changed a protected value, so yapper_ kept the original"
        if "unexpectedly shortened" in lowered or "dropped too much" in lowered:
            return "The AI formatter returned an incomplete fragment, so yapper_ kept the full dictation"
        if "dropped the beginning" in lowered or "dropped the end" in lowered:
            return "The AI formatter omitted part of the dictation, so yapper_ kept the complete version"
        if "reversed an explicit correction" in lowered:
            return "The AI formatter reversed a correction, so yapper_ kept the safe version"
        if method == "safe-timeout":
            return "The AI formatter took too long, so yapper_ kept the original"
        if detail:
            return f"{detail} · original wording preserved"
        return "The AI formatter was unavailable · original wording preserved"

    def _quit(self) -> None:
        self._quitting = True
        self._shutdown()
        QApplication.quit()

    def _shutdown(self) -> None:
        self.overlay.hide()
        audio = getattr(self, "_rick_audio", None)
        if audio and audio.isRunning():
            audio.stop()
            audio.wait(1_000)
        screen = getattr(self, "_rick_screen", None)
        if screen and screen.isVisible():
            screen.close()
        if self.hotkeys:
            self.hotkeys.unbind()
        self.pipeline.close()
        self.tray.hide()

    @staticmethod
    def _app_icon() -> QIcon:
        return create_app_icon()

    def run(self, start_hidden: bool = False) -> None:
        if start_hidden and QSystemTrayIcon.isSystemTrayAvailable():
            self._background_mode = True
            self.hide()
        else:
            self.show()
            if not self.pipeline.config.model_setup_completed:
                QTimer.singleShot(350, self._show_first_run_model_setup)
