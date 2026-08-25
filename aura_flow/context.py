from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass, replace

import psutil

from .formatting import FormatContext


@dataclass(frozen=True, slots=True)
class TargetWindow:
    hwnd: int | None
    process_id: int | None
    process_name: str
    title: str
    category: str
    control_name: str = ""
    control_type: str = ""
    before_cursor: str = ""
    selected_text: str = ""
    after_cursor: str = ""
    context_available: bool = False
    direct_insertion_available: bool = False


APP_CATEGORIES = {
    "personal": {"whatsapp.exe", "telegram.exe", "signal.exe", "discord.exe"},
    "work": {"slack.exe", "teams.exe", "ms-teams.exe"},
    "email": {"outlook.exe", "olk.exe", "thunderbird.exe"},
}


def _category(process_name: str, title: str) -> str:
    name = process_name.lower()
    lower_title = title.lower()
    for category, processes in APP_CATEGORIES.items():
        if name in processes:
            return category
    if name in {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"}:
        if any(term in lower_title for term in ("gmail", "outlook", "mail")):
            return "email"
        if any(term in lower_title for term in ("slack", "teams", "discord", "chat")):
            return "work"
    return "other"


class WindowsContextProvider:
    """Captures app identity and, when available, focused UIA text context."""

    def __init__(self, enabled: bool = True):
        self.enabled = False
        self.own_pid = os.getpid()
        self.last_external = TargetWindow(None, None, "", "", "other")
        self.uia = None
        self.set_enabled(enabled)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if self.enabled and self.uia is None and os.name == "nt":
            try:
                import uiautomation as auto

                auto.SetGlobalSearchTimeout(0.35)
                self.uia = auto
            except Exception:
                self.uia = None

    @property
    def accessibility_available(self) -> bool:
        return self.uia is not None

    def _window_identity(self) -> TargetWindow:
        if os.name != "nt":
            return TargetWindow(None, None, "", "", "other")
        user32 = ctypes.windll.user32
        raw_hwnd = user32.GetForegroundWindow()
        if not raw_hwnd:
            return TargetWindow(None, None, "", "", "other")
        hwnd = int(raw_hwnd)
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        try:
            process_name = psutil.Process(pid.value).name()
        except (psutil.Error, OSError):
            process_name = ""
        return TargetWindow(hwnd, int(pid.value), process_name, buffer.value, _category(process_name, buffer.value))

    def _with_accessibility_context(self, target: TargetWindow) -> TargetWindow:
        if not self.uia or target.process_id == self.own_pid:
            return target
        try:
            control = self.uia.GetFocusedControl()
            if not control or bool(getattr(control, "IsPassword", False)):
                return target
            control_pid = int(getattr(control, "ProcessId", 0) or 0)
            if control_pid and target.process_id and control_pid != target.process_id:
                return target
            control_name = str(getattr(control, "Name", "") or "")[:120]
            control_type = str(getattr(control, "ControlTypeName", "") or "")
            full_text = ""
            selected = ""
            before = ""
            after = ""
            try:
                value_pattern = control.GetValuePattern()
                full_text = str(getattr(value_pattern, "Value", "") or "")
            except Exception:
                value_pattern = None
            try:
                text_pattern = control.GetTextPattern()
                if text_pattern:
                    if not full_text:
                        full_text = str(text_pattern.DocumentRange.GetText(4_000) or "")
                    selections = text_pattern.GetSelection() or []
                    if selections:
                        selection = selections[0]
                        selected = str(selection.GetText(1_000) or "")

                        # A TextPattern selection is also the caret range when
                        # its text is empty. Clone and extend that range by at
                        # most 500 characters on either side, so formatting gets
                        # exact cursor context without reading whole documents.
                        endpoint = self.uia.TextPatternRangeEndpoint
                        character = self.uia.TextUnit.Character
                        before_range = selection.Clone()
                        before_range.MoveEndpointByUnit(endpoint.Start, character, -500, waitTime=0)
                        before_range.MoveEndpointByRange(endpoint.End, selection, endpoint.Start, waitTime=0)
                        before = str(before_range.GetText(500) or "")
                        after_range = selection.Clone()
                        after_range.MoveEndpointByRange(endpoint.Start, selection, endpoint.End, waitTime=0)
                        after_range.MoveEndpointByUnit(endpoint.End, character, 500, waitTime=0)
                        after = str(after_range.GetText(500) or "")
            except Exception:
                text_pattern = None
            if not before and not after and selected and full_text:
                index = full_text.find(selected)
                if index >= 0:
                    before = full_text[max(0, index - 500):index]
                    after = full_text[index + len(selected):index + len(selected) + 500]
            elif not before and not after and full_text:
                # UIA ValuePattern exposes content but not the caret. Supplying a
                # bounded suffix still improves proper nouns without pretending
                # that it is exact cursor context.
                before = full_text[-500:]
            editable = bool(value_pattern or text_pattern) and control_type in {"EditControl", "DocumentControl", "CustomControl"}
            return replace(
                target,
                control_name=control_name,
                control_type=control_type,
                before_cursor=before,
                selected_text=selected,
                after_cursor=after,
                context_available=bool(full_text or selected),
                direct_insertion_available=editable,
            )
        except Exception:
            return target

    def current_target(self) -> TargetWindow:
        target = self._window_identity()
        if target.process_id and target.process_id != self.own_pid:
            if self.enabled:
                target = self._with_accessibility_context(target)
            self.last_external = target
        return target

    def best_external_target(self) -> TargetWindow:
        current = self.current_target()
        return current if current.process_id != self.own_pid else self.last_external

    @staticmethod
    def formatting_context(target: TargetWindow) -> FormatContext:
        return FormatContext(
            app_category=target.category,
            before_cursor=target.before_cursor,
            selected_text=target.selected_text,
            after_cursor=target.after_cursor,
        )
