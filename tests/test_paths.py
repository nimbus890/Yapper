from pathlib import Path
import unittest

from aura_flow.paths import DATA_DIR, MODELS_DIR, SOURCE_DIR, USER_ROOT


class RuntimePathTests(unittest.TestCase):
    def test_personal_data_is_not_stored_in_source_tree(self):
        self.assertFalse(DATA_DIR.is_relative_to(SOURCE_DIR))
        self.assertEqual(DATA_DIR, USER_ROOT / "data")

    def test_downloaded_models_are_separate_from_source_tree(self):
        self.assertFalse(MODELS_DIR.is_relative_to(SOURCE_DIR))
        self.assertEqual(MODELS_DIR, USER_ROOT / "models")


if __name__ == "__main__":
    unittest.main()
