import unittest
import time
from unittest.mock import patch

from aura_flow.hotkeys import GlobalHotkeyController


class HotkeyTests(unittest.TestCase):
    def test_alt_z_registers_suppressed_press_and_release_edges(self):
        calls: list[str] = []
        controller = GlobalHotkeyController(
            "alt+z",
            lambda: calls.append("press"),
            lambda: calls.append("release"),
            lambda: calls.append("toggle"),
        )
        with (
            patch(
                "aura_flow.hotkeys.keyboard.add_hotkey", side_effect=("press-hook", "release-hook")
            ) as add_hotkey,
            patch("aura_flow.hotkeys.keyboard.remove_hotkey") as remove_hotkey,
        ):
            controller.bind("push_to_talk")
            self.assertEqual(add_hotkey.call_count, 2)
            self.assertTrue(add_hotkey.call_args_list[0].kwargs["suppress"])
            self.assertFalse(add_hotkey.call_args_list[0].kwargs["trigger_on_release"])
            self.assertTrue(add_hotkey.call_args_list[1].kwargs["trigger_on_release"])
            add_hotkey.call_args_list[0].args[1]()
            add_hotkey.call_args_list[0].args[1]()
            add_hotkey.call_args_list[1].args[1]()
            self.assertEqual(calls, ["press", "release"])
            controller.unbind()
            self.assertEqual(remove_hotkey.call_count, 2)

    def test_smart_single_tap_finishes_push_to_talk_after_grace_window(self):
        calls: list[str] = []
        controller = GlobalHotkeyController(
            "alt+z",
            lambda: calls.append("press"),
            lambda: calls.append("release"),
            lambda: calls.append("toggle"),
            lambda: calls.append("latch"),
            double_tap_seconds=0.15,
        )
        controller._mode = "smart"
        controller._press()
        controller._release()
        time.sleep(0.19)
        self.assertEqual(calls, ["press", "release"])
        controller.unbind()

    def test_smart_double_tap_latches_same_recording_then_next_tap_stops(self):
        calls: list[str] = []
        controller = GlobalHotkeyController(
            "alt+z",
            lambda: calls.append("press"),
            lambda: calls.append("release"),
            lambda: calls.append("toggle"),
            lambda: calls.append("latch"),
            double_tap_seconds=0.20,
        )
        controller._mode = "smart"
        controller._press()
        controller._release()
        time.sleep(0.12)
        controller._press()
        controller._release()
        self.assertEqual(calls, ["press", "latch"])
        time.sleep(0.12)
        controller._press()
        controller._release()
        self.assertEqual(calls, ["press", "latch", "toggle"])
        controller.unbind()


if __name__ == "__main__":
    unittest.main()
