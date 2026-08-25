import json
import tempfile
import unittest
from pathlib import Path

from aura_flow.config import AppConfig


class CleanupConfigTests(unittest.TestCase):
    def _load_level(self, legacy_level: str) -> str:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({"cleanup_level": legacy_level}), encoding="utf-8")
            return AppConfig.load(path).cleanup_level

    def test_old_code_modes_migrate_to_minimal(self):
        self.assertEqual(self._load_level("light"), "minimal")
        self.assertEqual(self._load_level("medium"), "minimal")

    def test_old_ai_modes_migrate_to_smart(self):
        self.assertEqual(self._load_level("ai_light"), "smart")
        self.assertEqual(self._load_level("ai_medium"), "smart")

    def test_unknown_mode_uses_smart_default(self):
        self.assertEqual(self._load_level("experimental"), "smart")


if __name__ == "__main__":
    unittest.main()
