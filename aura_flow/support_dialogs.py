from __future__ import annotations

from urllib.parse import urlencode

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QTextEdit, QVBoxLayout,
)

from .support import diagnostics_preview


class FeedbackDialog(QDialog):
    def __init__(self, pipeline, parent=None, selected_entry=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.selected_entry = selected_entry
        self.setWindowTitle("Send feedback")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("WHAT KIND OF FEEDBACK?", objectName="fieldTitle"))
        self.category = QComboBox()
        self.category.addItems(("Bug", "Idea", "Cleanup mistake", "Other"))
        layout.addWidget(self.category)
        layout.addWidget(QLabel("DETAILS", objectName="fieldTitle"))
        self.description = QTextEdit()
        self.description.setPlaceholderText("What happened, and what did you expect?")
        layout.addWidget(self.description)
        self.include_latest = QCheckBox(
            "Include the selected raw and finished dictation"
            if selected_entry else "Include the latest raw and finished dictation"
        )
        self.include_latest.setVisible(pipeline.config.allow_selected_transcripts)
        self.include_latest.setChecked(False)
        layout.addWidget(self.include_latest)
        self.preview = QTextEdit(diagnostics_preview(pipeline.config, pipeline.history))
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(145)
        self.preview.setVisible(pipeline.config.share_anonymous_diagnostics)
        layout.addWidget(QLabel("DIAGNOSTICS PREVIEW", objectName="fieldTitle"))
        layout.addWidget(self.preview)
        note = QLabel(
            "Diagnostics are included only if enabled in Preferences. Transcripts are never "
            "included here unless you explicitly opted in."
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        send = buttons.addButton("Open GitHub issue", QDialogButtonBox.AcceptRole)
        copy = buttons.addButton("Copy feedback", QDialogButtonBox.ActionRole)
        send.clicked.connect(self._open_issue)
        copy.clicked.connect(self._copy_feedback)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _open_issue(self) -> None:
        base = self.pipeline.config.feedback_github_url.strip()
        if not base:
            QMessageBox.information(
                self, "Feedback setup pending",
                "The GitHub feedback address has not been configured yet. Your text remains here so you can copy it."
            )
            return
        body = self._body()
        if self.pipeline.config.share_anonymous_diagnostics:
            body += "\n\n---\nDiagnostics\n" + self.preview.toPlainText()
        query = urlencode({
            "title": f"[{self.category.currentText()}] ",
            "body": body,
        })
        separator = "&" if "?" in base else "?"
        QDesktopServices.openUrl(QUrl(base + separator + query))
        self.accept()

    def _body(self) -> str:
        body = self.description.toPlainText().strip()
        if self.include_latest.isVisible() and self.include_latest.isChecked():
            entries = [self.selected_entry] if self.selected_entry else self.pipeline.history.recent(1)
            if entries and entries[0]:
                body += (
                    "\n\n---\nSelected dictation\nRAW\n" + str(entries[0].get("raw", ""))
                    + "\n\nFINISHED\n" + str(entries[0].get("final", ""))
                )
        return body

    def _copy_feedback(self) -> None:
        QApplication.clipboard().setText(self._body())


class CoffeeDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Buy me a coffee")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        title = QLabel("Keep yapper_ brewing")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        detail = QLabel("If yapper_ saves you time, you can support its development. Thank you.")
        detail.setWordWrap(True)
        detail.setObjectName("hint")
        layout.addWidget(detail)
        row = QHBoxLayout()
        paypal = QPushButton("PayPal")
        upi = QPushButton("Copy UPI ID")
        paypal.setEnabled(bool(config.paypal_url.strip()))
        upi.setEnabled(bool(config.upi_id.strip()))
        paypal.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(config.paypal_url)))
        upi.clicked.connect(self._copy_upi)
        row.addWidget(paypal)
        row.addWidget(upi)
        layout.addLayout(row)
        if not (paypal.isEnabled() or upi.isEnabled()):
            pending = QLabel("Payment details will be added before the public release.")
            pending.setObjectName("hint")
            layout.addWidget(pending)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout.addWidget(close, 0, Qt.AlignRight)

    def _copy_upi(self) -> None:
        QApplication.clipboard().setText(self.config.upi_id)
        QMessageBox.information(self, "UPI copied", "UPI ID copied. Thank you!")
