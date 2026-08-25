from pathlib import Path
import tempfile
import unittest

from aura_flow.download_manager import DOWNLOADS, command_for, format_bytes, installed_state, target_for


class DownloadManagerTests(unittest.TestCase):
    def test_targets_are_version_local(self):
        root = Path("C:/portable/yapper")
        self.assertEqual(target_for("tiny", root), root / "models" / "faster-whisper-tiny.en")
        self.assertEqual(target_for("medium", root), root / "models" / "faster-whisper-medium")
        self.assertEqual(target_for("smart", root), root / "models" / "gemma-3-1b-it")

    def test_tiny_and_medium_require_complete_whisper_files(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            target = target_for("tiny", root)
            target.mkdir(parents=True)
            for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
                (target / name).write_bytes(b"model")
            installed, size = installed_state("tiny", root)
            self.assertTrue(installed)
            self.assertEqual(size, 20)

    def test_smart_requires_weights_tokenizer_and_config(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            target = target_for("smart", root)
            target.mkdir(parents=True)
            for name in ("config.json", "model.safetensors", "tokenizer.json"):
                (target / name).write_bytes(b"ai")
            self.assertTrue(installed_state("smart", root)[0])

    def test_commands_use_transactional_setup_scripts(self):
        root = Path("C:/portable/yapper")
        _, tiny = command_for("tiny", app_dir=root, frozen=False)
        _, medium = command_for("medium", force=True, app_dir=root, frozen=False)
        _, smart = command_for("smart", app_dir=root, frozen=True)
        self.assertEqual(Path(tiny[0]).name, "main.py")
        self.assertEqual(tiny[-2:], ["--install-model", "tiny"])
        self.assertIn("--force", medium)
        self.assertEqual(smart, ["--install-model", "smart"])

    def test_human_sizes(self):
        self.assertEqual(format_bytes(75_000_000), "75 MB")
        self.assertEqual(format_bytes(1_500_000_000), "1.5 GB")

    def test_medium_is_the_recommended_dictation_model(self):
        titles = {spec.key: spec.title for spec in DOWNLOADS}
        self.assertNotIn("Recommended", titles["tiny"])
        self.assertIn("(Recommended)", titles["medium"])
        self.assertNotIn("Recommended", titles["smart"])


if __name__ == "__main__":
    unittest.main()
