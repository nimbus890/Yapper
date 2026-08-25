from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import sys
from typing import Callable

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from .paths import APP_DIR, FROZEN, MODELS_DIR
from .models import validate_faster_whisper
from .semantic import _complete_model


@dataclass(frozen=True, slots=True)
class DownloadSpec:
    key: str
    title: str
    description: str
    estimate: str
    required_bytes: int


DOWNLOADS = (
    DownloadSpec(
        "tiny", "Tiny dictation", "Fast local speech recognition and live preview.",
        "about 75 MB", 160_000_000,
    ),
    DownloadSpec(
        "medium", "Medium dictation (Recommended)", "Higher-accuracy local transcription; best with a capable GPU.",
        "about 1.5 GB", 2_400_000_000,
    ),
    DownloadSpec(
        "smart", "Local Smart Cleanup", "Gemma 3 1B removes speech-only filler while preserving your voice.",
        "about 1 GB", 1_800_000_000,
    ),
)


def target_for(key: str, app_dir: Path | None = None) -> Path:
    names = {
        "tiny": "faster-whisper-tiny.en",
        "medium": "faster-whisper-medium",
        "smart": "gemma-3-1b-it",
    }
    models_dir = MODELS_DIR if app_dir is None else app_dir / "models"
    return models_dir / names[key]


def installed_state(key: str, app_dir: Path | None = None) -> tuple[bool, int]:
    target = target_for(key, app_dir)
    installed = _complete_model(target) if key == "smart" else validate_faster_whisper(target).complete
    size = (
        sum(item.stat().st_size for item in target.rglob("*") if item.is_file())
        if target.exists() else 0
    )
    return installed, size


def format_bytes(value: int) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f} GB"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.0f} MB"
    return f"{value / 1_000:.0f} KB"


def command_for(
    key: str,
    force: bool = False,
    app_dir: Path = APP_DIR,
    frozen: bool = FROZEN,
) -> tuple[str, list[str]]:
    arguments = ["--install-model", key]
    if not frozen:
        arguments.insert(0, str(app_dir / "main.py"))
    if force:
        arguments.append("--force")
    return sys.executable, arguments


class DownloadsPanel(QWidget):
    """Install and select optional local models without leaving Settings."""

    def __init__(self, pipeline, on_saved: Callable[[], None], parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.on_saved = on_saved
        self.process: QProcess | None = None
        self.active_key = ""
        self.pending_downloads: list[str] = []
        self.batch_active = False
        self.rows: dict[str, dict[str, object]] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 18, 24, 18)
        title = QLabel("Downloads")
        title.setObjectName("pageTitle")
        detail = QLabel(
            "Add or repair local AI whenever you want. Downloads are optional, private after installation, and can be retried safely."
        )
        detail.setObjectName("hint")
        detail.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(detail)
        layout.addSpacing(18)

        setup_card = QFrame()
        setup_card.setObjectName("apiCard")
        setup_layout = QVBoxLayout(setup_card)
        setup_layout.setContentsMargins(22, 17, 22, 17)
        setup_title = QLabel("Choose your local models")
        setup_title.setObjectName("deckTitle")
        setup_detail = QLabel(
            "All three are selected for the complete offline experience. Uncheck anything you do not want, or skip setup and return later."
        )
        setup_detail.setObjectName("hint")
        setup_detail.setWordWrap(True)
        setup_layout.addWidget(setup_title)
        setup_layout.addWidget(setup_detail)
        setup_actions = QHBoxLayout()
        self.download_selected_button = QPushButton("Download selected models")
        self.download_selected_button.setObjectName("accentButton")
        self.download_selected_button.clicked.connect(self._start_selected)
        self.skip_setup_button = QPushButton("Skip for now")
        self.skip_setup_button.setObjectName("ghostButton")
        self.skip_setup_button.clicked.connect(self._skip_setup)
        setup_actions.addWidget(self.download_selected_button)
        setup_actions.addWidget(self.skip_setup_button)
        setup_actions.addStretch()
        setup_layout.addLayout(setup_actions)
        layout.addWidget(setup_card)

        for spec in DOWNLOADS:
            card = QFrame()
            card.setObjectName("apiCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(22, 17, 22, 17)
            heading = QHBoxLayout()
            selected = QCheckBox("Include")
            selected.setChecked(True)
            selected.setAccessibleName(f"Include {spec.title} in selected downloads")
            name = QLabel(spec.title)
            name.setObjectName("deckTitle")
            status = QLabel("Checking…")
            status.setObjectName("hint")
            heading.addWidget(selected)
            heading.addWidget(name)
            heading.addStretch()
            heading.addWidget(status)
            card_layout.addLayout(heading)
            description = QLabel(spec.description)
            description.setObjectName("hint")
            description.setWordWrap(True)
            card_layout.addWidget(description)

            token = None
            license_button = None
            if spec.key == "smart":
                license_row = QHBoxLayout()
                license_button = QPushButton("Accept Gemma license")
                license_button.setObjectName("ghostButton")
                license_button.clicked.connect(
                    lambda: QDesktopServices.openUrl(
                        QUrl("https://huggingface.co/google/gemma-3-1b-it")
                    )
                )
                token = QLineEdit()
                token.setEchoMode(QLineEdit.Password)
                token.setPlaceholderText("Hugging Face read token · used once, never saved")
                license_row.addWidget(license_button)
                license_row.addWidget(token, 1)
                card_layout.addLayout(license_row)

            actions = QHBoxLayout()
            download = QPushButton("Download")
            download.setObjectName("accentButton")
            download.clicked.connect(
                lambda checked=False, key=spec.key: self._start_download(key)
            )
            use = QPushButton("Use")
            use.clicked.connect(lambda checked=False, key=spec.key: self._select(key))
            progress = QProgressBar()
            progress.setRange(0, 0)
            progress.setTextVisible(False)
            progress.hide()
            actions.addWidget(download)
            if spec.key != "smart":
                actions.addWidget(use)
            actions.addWidget(progress, 1)
            card_layout.addLayout(actions)
            layout.addWidget(card)
            self.rows[spec.key] = {
                "spec": spec, "status": status, "download": download,
                "use": use, "progress": progress, "token": token,
                "license": license_button, "selected": selected,
            }

        self.activity = QLabel("Downloads use Hugging Face and require an internet connection.")
        self.activity.setObjectName("hint")
        self.activity.setWordWrap(True)
        layout.addWidget(self.activity)
        action_row = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel download")
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.hide()
        refresh = QPushButton("Refresh installed models")
        refresh.setObjectName("ghostButton")
        refresh.clicked.connect(self.refresh)
        action_row.addWidget(self.cancel_button)
        action_row.addWidget(refresh)
        action_row.addStretch()
        layout.addLayout(action_row)
        layout.addStretch()
        self.refresh()

    def refresh(self) -> None:
        config = self.pipeline.config
        for key, row in self.rows.items():
            installed, size = installed_state(key)
            spec: DownloadSpec = row["spec"]
            status: QLabel = row["status"]
            download: QPushButton = row["download"]
            use: QPushButton = row["use"]
            status.setText(
                f"Installed · {format_bytes(size)}" if installed else f"Not installed · {spec.estimate}"
            )
            download.setText("Repair" if installed else "Download")
            selected: QCheckBox = row["selected"]
            if installed:
                selected.setChecked(False)
            selected.setEnabled(not installed)
            use.setEnabled(installed)
            if key == "tiny":
                selected = config.model_name == "tiny.en" and installed
            elif key == "medium":
                selected = config.model_name == "medium" and installed
            else:
                selected = bool(config.semantic_formatting and installed)
            if key != "smart":
                use.setText("Selected" if selected else f"Use {spec.title.split()[0]}")
                use.setEnabled(installed and not selected)
            token = row["token"]
            if token is not None:
                token.setVisible(not installed)
                row["license"].setVisible(not installed)

    def _start_selected(self) -> None:
        if self.process and self.process.state() != QProcess.NotRunning:
            QMessageBox.information(self, "Download in progress", "Finish or cancel the current download first.")
            return
        selected = [
            key for key, row in self.rows.items()
            if row["selected"].isChecked() and not installed_state(key)[0]
        ]
        if not selected:
            self.activity.setText("Nothing selected. Choose at least one model or skip setup for now.")
            return
        if "smart" in selected:
            token: QLineEdit = self.rows["smart"]["token"]
            if not token.text().strip():
                QMessageBox.information(
                    self,
                    "Gemma access required",
                    "Accept the Gemma license, paste a Hugging Face read token, then choose Download selected models again.",
                )
                return
        self.pipeline.config.model_setup_completed = True
        self.pipeline.config.save()
        self.pending_downloads = selected
        self.batch_active = True
        self._start_next_selected()

    def _start_next_selected(self) -> None:
        if not self.pending_downloads:
            self.batch_active = False
            self.activity.setText("Selected models installed successfully. You can change them here at any time.")
            self.on_saved()
            self.refresh()
            return
        key = self.pending_downloads.pop(0)
        self._start_download(key)

    def _stop_selected_batch(self) -> None:
        self.pending_downloads.clear()
        self.batch_active = False

    def _skip_setup(self) -> None:
        self.pipeline.config.model_setup_completed = True
        self.pipeline.config.save()
        self.activity.setText("Model setup skipped. Return to Downloads whenever you are ready.")
        self.on_saved()

    def _start_download(self, key: str) -> None:
        if self.process and self.process.state() != QProcess.NotRunning:
            QMessageBox.information(self, "Download in progress", "Finish or cancel the current download first.")
            return
        row = self.rows[key]
        spec: DownloadSpec = row["spec"]
        installed, _ = installed_state(key)
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(MODELS_DIR).free
        if free < spec.required_bytes:
            self._stop_selected_batch()
            QMessageBox.warning(
                self, "Not enough disk space",
                f"{spec.title} needs temporary space during installation. Free at least {format_bytes(spec.required_bytes)} and try again.",
            )
            return
        token = ""
        token_widget = row["token"]
        if token_widget is not None:
            token = token_widget.text().strip()
            token_widget.clear()
        program, arguments = command_for(key, force=installed)
        process = QProcess(self)
        environment = QProcessEnvironment.systemEnvironment()
        environment.remove("HF_HUB_OFFLINE")
        environment.remove("TRANSFORMERS_OFFLINE")
        if token:
            environment.insert("HF_TOKEN", token)
        process.setProcessEnvironment(environment)
        process.setProgram(program)
        process.setArguments(arguments)
        process.setWorkingDirectory(str(APP_DIR))
        process.setProcessChannelMode(QProcess.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_output)
        process.readyReadStandardError.connect(self._read_output)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._process_error)
        self.process = process
        self.active_key = key
        self.cancel_button.show()
        row["progress"].show()
        self.activity.setText(f"Downloading {spec.title}… You can keep using Settings.")
        self._set_controls_enabled(False)
        process.start()

    def _read_output(self) -> None:
        if not self.process:
            return
        output = bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace")
        output += bytes(self.process.readAllStandardError()).decode("utf-8", "replace")
        lines = [line.strip() for line in output.replace("\r", "\n").splitlines() if line.strip()]
        if lines:
            self.activity.setText(lines[-1][-280:])

    def _finished(self, exit_code: int, exit_status) -> None:
        del exit_status
        key = self.active_key
        row = self.rows.get(key)
        if row:
            row["progress"].hide()
        self.cancel_button.hide()
        self._set_controls_enabled(True)
        completed = exit_code == 0
        if completed:
            self._apply_install(key)
            self.activity.setText(
                "Installed successfully. Restart yapper_ before switching dictation engines."
                if key in {"tiny", "medium"}
                else "Local Smart Cleanup is installed and ready."
            )
        else:
            self.activity.setText(
                "Download did not finish. Nothing working was replaced; check the message above and retry."
            )
            self._stop_selected_batch()
        self.process = None
        self.active_key = ""
        self.refresh()
        if completed and self.batch_active:
            QTimer.singleShot(0, self._start_next_selected)

    def _apply_install(self, key: str) -> None:
        target = target_for(key).resolve()
        config = self.pipeline.config
        if key == "tiny":
            config.partial_transcription = True
            config.partial_model_path = str(target)
        elif key == "medium":
            config.model_name = "medium"
            config.model_path = str(target)
        else:
            config.semantic_formatting = True
            config.semantic_model_path = str(target)
            config.cleanup_level = "smart"
        config.save()
        if key == "smart":
            self.pipeline.reload_api_formatter()
        self.on_saved()

    def _select(self, key: str) -> None:
        installed, _ = installed_state(key)
        if not installed:
            return
        config = self.pipeline.config
        config.model_name = "tiny.en" if key == "tiny" else "medium"
        config.model_path = str(target_for(key).resolve())
        config.save()
        self.activity.setText(f"{key.title()} selected · restart yapper_ to load it.")
        self.on_saved()
        self.refresh()

    def _cancel(self) -> None:
        if not self.process or self.process.state() == QProcess.NotRunning:
            return
        self.activity.setText("Cancelling download…")
        self._stop_selected_batch()
        self.process.terminate()
        QTimer.singleShot(
            2_000,
            lambda: self.process.kill()
            if self.process and self.process.state() != QProcess.NotRunning
            else None,
        )

    def _process_error(self, error) -> None:
        if not self.process:
            return
        self.activity.setText(f"Could not start the downloader: {self.process.errorString()}")
        if error == QProcess.FailedToStart:
            self._stop_selected_batch()
            row = self.rows.get(self.active_key)
            if row:
                row["progress"].hide()
            self.cancel_button.hide()
            self.process = None
            self.active_key = ""
            self._set_controls_enabled(True)
            self.refresh()

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.download_selected_button.setEnabled(enabled)
        self.skip_setup_button.setEnabled(enabled)
        for row in self.rows.values():
            row["download"].setEnabled(enabled)
            row["use"].setEnabled(enabled)
            row["selected"].setEnabled(enabled and not installed_state(row["spec"].key)[0])
