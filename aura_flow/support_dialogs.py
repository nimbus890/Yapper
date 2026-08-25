from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QFileDialog, QMessageBox, QPushButton, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from .support import create_form_data_export, diagnostics_preview


class FeedbackDialog(QDialog):
    def __init__(self, pipeline, parent=None, selected_entry=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.selected_entry = selected_entry
        self.setWindowTitle("Send feedback")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._feedback_tab(), "Feedback")
        tabs.addTab(self._send_data_tab(), "Send data")
        layout.addWidget(tabs)

    def _feedback_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
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
            if self.selected_entry else "Include the latest raw and finished dictation"
        )
        self.include_latest.setVisible(self.pipeline.config.allow_selected_transcripts)
        self.include_latest.setChecked(False)
        layout.addWidget(self.include_latest)
        self.preview = QTextEdit(diagnostics_preview(self.pipeline.config, self.pipeline.history))
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(145)
        self.preview.setVisible(self.pipeline.config.share_anonymous_diagnostics)
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
        return page

    def _send_data_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("SEND TESTING DATA", objectName="fieldTitle")
        layout.addWidget(title)
        explanation = QLabel(
            "Choose what to include. Yapper creates a plain-text report locally, then opens "
            "the private Google Form. Nothing is uploaded automatically."
        )
        explanation.setObjectName("hint")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.data_scope = QComboBox()
        if self.selected_entry:
            self.data_scope.addItem("This selected dictation", "selected")
        else:
            self.data_scope.addItem("Latest dictation", "latest")
        self.data_scope.addItem("Complete history", "complete")
        self.data_scope.currentIndexChanged.connect(self._refresh_data_preview)
        layout.addWidget(self.data_scope)
        layout.addWidget(QLabel("PREVIEW", objectName="fieldTitle"))
        self.data_preview = QTextEdit()
        self.data_preview.setReadOnly(True)
        self.data_preview.setMaximumHeight(190)
        layout.addWidget(self.data_preview)
        self.data_consent = QCheckBox(
            "I reviewed this scope and understand that dictations may contain private text"
        )
        layout.addWidget(self.data_consent)
        note = QLabel(
            "Never included: passwords, API keys, tokens, clipboard contents, personal "
            "vocabulary, audio files, or unrelated files."
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QHBoxLayout()
        prepare = QPushButton("Prepare file & open Google Form")
        prepare.clicked.connect(self._prepare_data)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(prepare)
        buttons.addStretch()
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self._refresh_data_preview()
        return page

    def _data_entries(self) -> tuple[list[dict[str, object]], str]:
        scope = str(self.data_scope.currentData() or "latest")
        if scope == "complete":
            return self.pipeline.history.all_entries(), "complete history"
        if scope == "selected" and self.selected_entry:
            return [self.selected_entry], "selected dictation"
        return self.pipeline.history.recent(1), "latest dictation"

    def _refresh_data_preview(self) -> None:
        entries, scope = self._data_entries()
        lines = [f"Scope: {scope}", f"Dictations: {len(entries)}", ""]
        if entries:
            visible = entries if len(entries) <= 3 else entries[:3]
            for index, entry in enumerate(visible, 1):
                final = str(entry.get("final", "")).replace("\n", " ").strip()
                lines.append(f"{index}. {final[:240] or '(empty dictation)'}")
            if len(entries) > len(visible):
                lines.append(f"…and {len(entries) - len(visible)} more dictations.")
        else:
            lines.append("No stored dictations are available for this scope.")
        self.data_preview.setPlainText("\n".join(lines))

    def _prepare_data(self) -> None:
        if not self.data_consent.isChecked():
            QMessageBox.information(
                self, "Review required", "Review the scope and tick the confirmation first."
            )
            return
        entries, scope = self._data_entries()
        if not entries:
            QMessageBox.information(self, "Nothing to export", "No stored dictations were found.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose where to save the Yapper data file")
        if not folder:
            return
        try:
            output = create_form_data_export(
                self.pipeline.config, entries, Path(folder), scope,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        form_url = self.pipeline.config.feedback_data_form_url.strip()
        QApplication.clipboard().setText(str(output))
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(output.parent)))
        if form_url:
            QDesktopServices.openUrl(QUrl(form_url))
        QMessageBox.information(
            self,
            "Data file ready",
            f"Created {output.name}. Its path is copied. Upload only this file to the Google Form.",
        )

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
