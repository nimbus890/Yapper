import tempfile
import unittest
from pathlib import Path

from aura_flow.models import REQUIRED_FASTER_WHISPER_FILES, validate_faster_whisper


class ModelValidationTests(unittest.TestCase):
    def test_incomplete_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "config.json").write_text("{}", encoding="utf-8")
            candidate = validate_faster_whisper(path)
            self.assertFalse(candidate.complete)
            self.assertIn("model.bin", candidate.missing)

    def test_required_files_are_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            for name in REQUIRED_FASTER_WHISPER_FILES:
                (path / name).write_bytes(b"ok")
            self.assertTrue(validate_faster_whisper(path).complete)

    def test_cache_snapshot_uses_repository_model_name(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "models--Systran--faster-whisper-medium" / "snapshots" / "commit"
            path.mkdir(parents=True)
            for name in REQUIRED_FASTER_WHISPER_FILES:
                (path / name).write_bytes(b"ok")
            self.assertEqual(validate_faster_whisper(path).name, "medium")


if __name__ == "__main__":
    unittest.main()
