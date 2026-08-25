"""Application identity icons shared by the UI and release tooling."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def create_app_icon(size: int = 64) -> QIcon:
    scale = size / 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#F3EEE4"))
    painter.setPen(QPen(QColor("#CFC8BA"), 1.5 * scale))
    painter.drawRoundedRect(
        QRectF(4 * scale, 4 * scale, 56 * scale, 56 * scale),
        18 * scale,
        18 * scale,
    )
    letter = QPainterPath()
    letter.moveTo(18 * scale, 20 * scale)
    letter.cubicTo(20 * scale, 30 * scale, 22 * scale, 37 * scale, 28 * scale, 37 * scale)
    letter.cubicTo(34 * scale, 37 * scale, 35 * scale, 29 * scale, 37 * scale, 20 * scale)
    letter.moveTo(37 * scale, 20 * scale)
    letter.lineTo(35 * scale, 41 * scale)
    letter.cubicTo(34 * scale, 48 * scale, 30 * scale, 52 * scale, 24 * scale, 52 * scale)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(
        QPen(QColor("#1B1B18"), 5 * scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    )
    painter.drawPath(letter)
    painter.setPen(
        QPen(QColor("#6D58F5"), 4 * scale, Qt.SolidLine, Qt.RoundCap)
    )
    painter.drawLine(
        round(39 * scale), round(48 * scale), round(51 * scale), round(48 * scale)
    )
    painter.end()
    return QIcon(pixmap)
