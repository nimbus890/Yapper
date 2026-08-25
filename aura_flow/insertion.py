from __future__ import annotations

import ctypes
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import keyboard
import pyperclip

from .context import TargetWindow


@dataclass(frozen=True, slots=True)
class InsertionResult:
    success: bool
    method: str
    message: str
    elapsed_ms: float


def _escape_uia_keys(text: str) -> str:
    # uiautomation SendKeys uses braces for special keys. Literal braces are
    # escaped; newlines deliberately become Enter key presses.
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    escaped = {"{": "{{}", "}": "{}}", "\n": "{Enter}"}
    return "".join(escaped.get(character, character) for character in normalized)


def _safe_for_direct_sendkeys(text: str) -> bool:
    """SendKeys cannot safely insert paragraphs into apps where Enter submits."""

    return "\n" not in text and "\r" not in text


class TextInserter:
    def __init__(self, last_transcript_path: Path, restore_clipboard: bool = True, direct_enabled: bool = True):
        self.last_transcript_path = last_transcript_path
        self.restore_clipboard = restore_clipboard
        self.direct_enabled = False
        self.uia = None
        self.set_direct_enabled(direct_enabled)

    def set_direct_enabled(self, enabled: bool) -> None:
        self.direct_enabled = bool(enabled)
        if self.direct_enabled and self.uia is None and os.name == "nt":
            try:
                import uiautomation as auto

                auto.SetGlobalSearchTimeout(0.35)
                self.uia = auto
            except Exception:
                self.uia = None

    @staticmethod
    def _focus(target: TargetWindow) -> bool:
        if os.name != "nt" or not target.hwnd:
            return True
        user32 = ctypes.windll.user32
        foreground = user32.GetForegroundWindow()
        if foreground and int(foreground) == target.hwnd:
            return True
        user32.ShowWindow(target.hwnd, 5)
        user32.SetForegroundWindow(target.hwnd)
        deadline = time.monotonic() + 0.8
        while time.monotonic() < deadline:
            foreground = user32.GetForegroundWindow()
            if foreground and int(foreground) == target.hwnd:
                return True
            time.sleep(0.02)
        return False

    def _direct_insert(self, text: str, target: TargetWindow, press_enter: bool) -> bool:
        if (
            not self.direct_enabled
            or not self.uia
            or not target.direct_insertion_available
            or not _safe_for_direct_sendkeys(text)
        ):
            return False
        try:
            control = self.uia.GetFocusedControl()
            if not control or bool(getattr(control, "IsPassword", False)):
                return False
            if target.process_id and int(getattr(control, "ProcessId", 0) or 0) != target.process_id:
                return False
            keys = _escape_uia_keys(text) + ("{Enter}" if press_enter else "")
            control.SendKeys(keys, waitTime=0, interval=0)
            return True
        except Exception:
            return False

    def perform_action(self, action: str, target: TargetWindow) -> InsertionResult:
        start = time.perf_counter()
        if not self._focus(target):
            return InsertionResult(False, "none", "The original text field could not be focused.", (time.perf_counter() - start) * 1_000)
        try:
            if action == "undo":
                keyboard.press_and_release("ctrl+z")
                message = "Undid the last edit"
            elif action == "paste_last":
                if not self.last_transcript_path.exists():
                    raise RuntimeError("No previous transcript is available")
                pyperclip.copy(self.last_transcript_path.read_text(encoding="utf-8"))
                keyboard.press_and_release("ctrl+v")
                message = "Pasted the last transcript"
            elif action == "copy_last":
                if not self.last_transcript_path.exists():
                    raise RuntimeError("No previous transcript is available")
                pyperclip.copy(self.last_transcript_path.read_text(encoding="utf-8"))
                message = "Copied the last transcript"
            else:
                raise RuntimeError(f"Unknown voice action: {action}")
            return InsertionResult(True, "voice-action", message, (time.perf_counter() - start) * 1_000)
        except Exception as exc:
            return InsertionResult(False, "voice-action", str(exc), (time.perf_counter() - start) * 1_000)

    def insert(self, text: str, target: TargetWindow, press_enter: bool = False) -> InsertionResult:
        start = time.perf_counter()
        self.last_transcript_path.parent.mkdir(parents=True, exist_ok=True)
        self.last_transcript_path.write_text(text, encoding="utf-8")
        if not self._focus(target):
            pyperclip.copy(text)
            return InsertionResult(False, "clipboard", "The original text field could not be focused; transcript is on the clipboard.", (time.perf_counter() - start) * 1_000)

        if self._direct_insert(text, target, press_enter):
            return InsertionResult(True, "uia-direct", "Inserted directly through Windows accessibility", (time.perf_counter() - start) * 1_000)

        try:
            previous = pyperclip.paste()
        except Exception:
            previous = None
        try:
            pyperclip.copy(text)
        except Exception as exc:
            return InsertionResult(False, "file", f"Clipboard unavailable: {exc}", (time.perf_counter() - start) * 1_000)
        try:
            keyboard.press_and_release("ctrl+v")
            if press_enter:
                time.sleep(0.05)
                keyboard.press_and_release("enter")
        except Exception as exc:
            return InsertionResult(False, "clipboard", f"Paste failed: {exc}", (time.perf_counter() - start) * 1_000)

        if self.restore_clipboard and previous is not None:
            def restore() -> None:
                time.sleep(1.25)
                try:
                    pyperclip.copy(previous)
                except Exception:
                    pass

            threading.Thread(target=restore, name="clipboard-restore", daemon=True).start()
        return InsertionResult(True, "clipboard-paste", "Inserted with clipboard fallback", (time.perf_counter() - start) * 1_000)
