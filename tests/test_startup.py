import unittest
from unittest.mock import patch

from aura_flow.startup import startup_command


class StartupTests(unittest.TestCase):
    def test_source_startup_command_uses_pythonw_and_main(self):
        command = startup_command().casefold()
        self.assertIn("pythonw.exe", command)
        self.assertIn("main.py", command)
        self.assertIn("--startup", command)

    @patch("aura_flow.startup.FROZEN", True)
    @patch("aura_flow.startup.sys.executable", r"C:\Program Files\Yapper\Yapper.exe")
    def test_frozen_startup_command_runs_the_executable_directly(self):
        command = startup_command().casefold()
        self.assertIn("yapper.exe", command)
        self.assertIn("--startup", command)
        self.assertNotIn("main.py", command)


if __name__ == "__main__":
    unittest.main()
