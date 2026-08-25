from __future__ import annotations

import threading
import time
from pathlib import Path

import av
import numpy as np
import sounddevice as sd
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QImage, QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

from .paths import ASSETS_DIR, INSTALL_DIR


MEDIA_EXTENSIONS = (".mp4", ".m4a", ".mp3", ".wav", ".aac")


def discover_rick_media(video: bool = False) -> Path | None:
    """Find packaged media, with a development-folder fallback for new drops."""
    folders = (ASSETS_DIR / "rickroll", ASSETS_DIR, INSTALL_DIR)
    audio_names = (
        "rickroll-audio.wav", "rickroll-audio.mp3", "rickroll-audio.m4a",
        "rick.wav", "rick.mp3", "rick.m4a",
    )
    video_names = ("rickroll.mp4", "rick.mp4")
    for names in ((video_names,) if video else (audio_names, video_names)):
        for folder in folders:
            for name in names:
                candidate = folder / name
                if candidate.is_file():
                    return candidate
    extension_groups = ((".mp4",),) if video else ((".wav", ".mp3", ".m4a", ".aac"), (".mp4",))
    for extensions in extension_groups:
        for folder in folders:
            if not folder.is_dir():
                continue
            for candidate in folder.iterdir():
                if (
                    candidate.is_file()
                    and candidate.suffix.casefold() in extensions
                    and "rick" in candidate.stem.casefold()
                ):
                    return candidate
    return None


class AudioPlaybackWorker(QThread):
    failed = Signal(str)

    def __init__(self, path: Path, max_seconds: float | None = None, parent=None):
        super().__init__(parent)
        self.path = path
        self.max_seconds = max_seconds
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            with av.open(str(self.path)) as container:
                if not container.streams.audio:
                    raise RuntimeError("The Rickroll file has no audio track")
                stream = container.streams.audio[0]
                rate = 48_000
                resampler = av.AudioResampler(format="flt", layout="stereo", rate=rate)
                started = time.monotonic()
                with sd.OutputStream(samplerate=rate, channels=2, dtype="float32") as output:
                    for frame in container.decode(stream):
                        if self._stop_event.is_set():
                            break
                        converted_frames = resampler.resample(frame)
                        for converted in converted_frames:
                            samples = converted.to_ndarray()
                            if samples.ndim == 2 and samples.shape[0] == 1:
                                samples = samples.reshape(-1, 2)
                            elif samples.ndim == 2 and samples.shape[0] == 2:
                                samples = samples.T
                            samples = np.ascontiguousarray(samples, dtype=np.float32)
                            if self._stop_event.is_set():
                                break
                            output.write(samples)
                        if self.max_seconds and time.monotonic() - started >= self.max_seconds:
                            break
        except Exception as exc:
            self.failed.emit(str(exc))


class VideoPlaybackWorker(QThread):
    frame_ready = Signal(QImage)
    failed = Signal(str)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = path
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            with av.open(str(self.path)) as container:
                if not container.streams.video:
                    raise RuntimeError("The Rickroll file has no video track")
                stream = container.streams.video[0]
                started = time.monotonic()
                first_timestamp: float | None = None
                for frame in container.decode(stream):
                    if self._stop_event.is_set():
                        break
                    timestamp = float(frame.time or 0.0)
                    if first_timestamp is None:
                        first_timestamp = timestamp
                    target = timestamp - first_timestamp
                    delay = target - (time.monotonic() - started)
                    while delay > 0 and not self._stop_event.wait(min(0.02, delay)):
                        delay = target - (time.monotonic() - started)
                    if self._stop_event.is_set():
                        break
                    if delay < -0.18:
                        continue
                    rgb = frame.to_ndarray(format="rgb24")
                    height, width, _ = rgb.shape
                    image = QImage(
                        rgb.data, width, height, rgb.strides[0], QImage.Format_RGB888
                    ).copy()
                    self.frame_ready.emit(image)
        except Exception as exc:
            self.failed.emit(str(exc))


class RickrollScreen(QDialog):
    """Frameless in-app video surface; Escape or any click immediately exits."""

    playback_failed = Signal(str)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Window)
        self.path = path
        self._pixmap = QPixmap()
        self.setStyleSheet("background: black;")
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.video = QLabel()
        self.video.setAlignment(Qt.AlignCenter)
        self.video.setStyleSheet("background: black;")
        self.video.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.video)
        self.hint = QLabel("ESC OR CLICK ANYWHERE TO CLOSE", self)
        self.hint.setStyleSheet(
            "color: rgba(255,255,255,150); background: rgba(0,0,0,90); "
            "padding: 8px 12px; font-size: 11px; font-weight: 700;"
        )
        self.hint.adjustSize()
        self.hint.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.StrongFocus)
        self.video_worker = VideoPlaybackWorker(path, self)
        self.audio_worker = AudioPlaybackWorker(path, parent=self)
        self.video_worker.frame_ready.connect(self._show_frame)
        self.video_worker.failed.connect(self.playback_failed)
        self.audio_worker.failed.connect(self.playback_failed)
        self.video_worker.finished.connect(self.close)

    def start(self) -> None:
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.OtherFocusReason)
        self.video_worker.start()
        self.audio_worker.start()

    def _show_frame(self, image: QImage) -> None:
        self._pixmap = QPixmap.fromImage(image)
        self._fit_frame()

    def _fit_frame(self) -> None:
        if not self._pixmap.isNull():
            self.video.setPixmap(
                self._pixmap.scaled(self.video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_frame()
        self.hint.move(max(16, self.width() - self.hint.width() - 22), 20)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.close()
        event.accept()

    def closeEvent(self, event) -> None:
        self.video_worker.stop()
        self.audio_worker.stop()
        self.video_worker.wait(1_000)
        self.audio_worker.wait(1_000)
        super().closeEvent(event)
