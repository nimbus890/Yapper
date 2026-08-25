from __future__ import annotations

import threading
import time
from typing import Callable

import keyboard


class GlobalHotkeyController:
    """Binds either hold-to-talk or toggle/hands-free behavior."""

    def __init__(
        self,
        hotkey: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        on_toggle: Callable[[], None],
        on_latch: Callable[[], None] | None = None,
        double_tap_seconds: float = 0.32,
        on_paste_last: Callable[[], None] | None = None,
        paste_hotkey: str = "ctrl+alt+v",
    ):
        self.hotkey = hotkey
        self.on_press = on_press
        self.on_release = on_release
        self.on_toggle = on_toggle
        self.on_latch = on_latch or (lambda: None)
        self.double_tap_seconds = max(0.15, float(double_tap_seconds))
        self.on_paste_last = on_paste_last
        self.paste_hotkey = paste_hotkey
        self._handles: list[tuple[str, object]] = []
        self._lock = threading.Lock()
        self._pressed = False
        self._down_keys: set[str] = set()
        self._last_press = 0.0
        self._mode = "push_to_talk"
        self._latched = False
        self._waiting_for_second = False
        self._release_timer: threading.Timer | None = None
        self._ignore_release_once = False

    def bind(self, mode: str) -> None:
        self.unbind()
        self._mode = mode
        if mode == "hands_free":
            handle = keyboard.add_hotkey(self.hotkey, self._toggle, suppress=False)
            self._handles.append(("hotkey", handle))
            self._bind_paste_last()
            return
        self._required_keys = {
            self._normalize_key(part) for part in self.hotkey.split("+") if part.strip()
        }
        self._down_keys.clear()
        if not self._required_keys:
            raise ValueError("The push-to-talk shortcut is empty")
        modifier_keys = {"alt", "ctrl", "shift", "windows"}
        if self._required_keys - modifier_keys:
            press = keyboard.add_hotkey(
                self.hotkey, self._press, suppress=True, trigger_on_release=False
            )
            release = keyboard.add_hotkey(
                self.hotkey, self._release, suppress=True, trigger_on_release=True
            )
            self._handles.extend((("hotkey", press), ("hotkey", release)))
            self._bind_paste_last()
            return
        handle = keyboard.hook(self._key_event, suppress=False)
        self._handles.append(("hook", handle))
        self._bind_paste_last()

    def _bind_paste_last(self) -> None:
        if not self.on_paste_last or not self.paste_hotkey.strip():
            return
        if self.paste_hotkey.casefold().replace(" ", "") == self.hotkey.casefold().replace(" ", ""):
            return
        handle = keyboard.add_hotkey(
            self.paste_hotkey,
            self.on_paste_last,
            suppress=True,
            trigger_on_release=True,
        )
        self._handles.append(("hotkey", handle))

    @staticmethod
    def _normalize_key(value: str) -> str:
        key = value.strip().casefold()
        aliases = {"control": "ctrl", "left control": "ctrl", "right control": "ctrl"}
        key = aliases.get(key, key)
        for prefix in ("left ", "right "):
            if key.startswith(prefix):
                key = key[len(prefix) :]
        return key

    def _key_event(self, event) -> None:
        name = self._normalize_key(getattr(event, "name", ""))
        if name not in self._required_keys:
            return
        event_type = getattr(event, "event_type", "")
        if event_type == keyboard.KEY_DOWN:
            self._down_keys.add(name)
            if self._required_keys.issubset(self._down_keys):
                self._press()
        elif event_type == keyboard.KEY_UP:
            self._down_keys.discard(name)
            if self._pressed:
                self._release()

    def _press(self) -> None:
        action = "press"
        with self._lock:
            now = time.monotonic()
            if self._pressed or now - self._last_press < 0.08:
                return
            self._pressed = True
            self._last_press = now
            if self._mode == "smart" and self._latched:
                self._latched = False
                self._ignore_release_once = True
                action = "toggle"
            elif self._mode == "smart" and self._waiting_for_second:
                self._waiting_for_second = False
                if self._release_timer:
                    self._release_timer.cancel()
                    self._release_timer = None
                self._latched = True
                action = "latch"
        if action == "toggle":
            self.on_toggle()
        elif action == "latch":
            self.on_latch()
        else:
            self.on_press()

    def _release(self) -> None:
        release_now = False
        with self._lock:
            if not self._pressed:
                return
            self._pressed = False
            if self._ignore_release_once:
                self._ignore_release_once = False
                return
            if self._mode == "smart":
                if self._latched:
                    return
                self._waiting_for_second = True
                self._release_timer = threading.Timer(
                    self.double_tap_seconds,
                    self._finish_smart_release,
                )
                self._release_timer.daemon = True
                self._release_timer.start()
            else:
                release_now = True
        if release_now:
            self.on_release()

    def _finish_smart_release(self) -> None:
        with self._lock:
            if not self._waiting_for_second or self._latched:
                return
            self._waiting_for_second = False
            self._release_timer = None
        self.on_release()

    def _toggle(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now - self._last_press < 0.15:
                return
            self._last_press = now
        self.on_toggle()

    def unbind(self) -> None:
        for kind, handle in self._handles:
            try:
                if kind == "hook":
                    keyboard.unhook(handle)
                else:
                    keyboard.remove_hotkey(handle)
            except Exception:
                pass
        self._handles.clear()
        with self._lock:
            if self._release_timer:
                self._release_timer.cancel()
                self._release_timer = None
            self._pressed = False
            self._down_keys.clear()
            self._latched = False
            self._waiting_for_second = False
            self._ignore_release_once = False
