import unittest
from unittest.mock import patch

from main import _run_model_installer


class PackagedHelperTests(unittest.TestCase):
    def test_missing_model_name_is_rejected(self):
        self.assertEqual(_run_model_installer(["--install-model"]), 2)

    @patch("setup_models.install")
    def test_tiny_download_uses_partial_role(self, install):
        self.assertEqual(_run_model_installer(["--install-model", "tiny"]), 0)
        install.assert_called_once_with("tiny.en", force=False, role="partial")

    @patch("setup_semantic.install", side_effect=RuntimeError("gated"))
    def test_model_installer_returns_failure_without_starting_the_ui(self, install):
        self.assertEqual(_run_model_installer(["--install-model", "smart"]), 1)
        install.assert_called_once_with(force=False)


if __name__ == "__main__":
    unittest.main()

