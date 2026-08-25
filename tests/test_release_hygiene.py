from pathlib import Path
import tomllib
import unittest

from aura_flow.paths import SOURCE_DIR
from aura_flow.version import PUBLISHER, VERSION


class ReleaseHygieneTests(unittest.TestCase):
    def test_source_tree_has_no_runtime_state_directories(self):
        for name in ("data", "models", "vendor"):
            self.assertFalse((SOURCE_DIR / name).exists(), name)

    def test_metadata_uses_central_release_identity(self):
        metadata = tomllib.loads((SOURCE_DIR / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(metadata["project"]["version"], VERSION)
        self.assertEqual(metadata["project"]["authors"][0]["name"], PUBLISHER)

    def test_required_media_decoder_is_declared(self):
        requirements = (SOURCE_DIR / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("av==", requirements)


if __name__ == "__main__":
    unittest.main()

