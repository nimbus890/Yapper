import unittest

from aura_flow.ui import _friendly_app_name


class UiHelperTests(unittest.TestCase):
    def test_friendly_target_hides_executable_suffix(self):
        self.assertEqual(_friendly_app_name("ChatGPT.exe"), "ChatGPT")
        self.assertEqual(_friendly_app_name("ms-teams.exe"), "Microsoft Teams")
        self.assertEqual(_friendly_app_name("custom-editor.exe"), "Custom Editor")


if __name__ == "__main__":
    unittest.main()
