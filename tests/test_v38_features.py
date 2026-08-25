import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from aura_flow.config import AppConfig
from aura_flow.hotkeys import GlobalHotkeyController
from aura_flow.pipeline import DictationPipeline
from aura_flow.rickroll import discover_rick_media
from aura_flow.support import create_form_data_export, create_testing_export, sanitized_settings


class V38FeatureTests(unittest.TestCase):
    def test_sharing_options_are_opted_out_and_dark_is_default(self):
        config = AppConfig()
        self.assertEqual(config.theme_mode, "dark")
        self.assertFalse(config.share_anonymous_diagnostics)
        self.assertFalse(config.allow_selected_transcripts)
        self.assertFalse(config.enable_complete_data_export)

    def test_recall_hotkey_is_global_suppressed_and_fires_on_release(self):
        recalled = []
        controller = GlobalHotkeyController(
            "alt+z", Mock(), Mock(), Mock(),
            on_paste_last=lambda: recalled.append(True),
        )
        with (
            patch("aura_flow.hotkeys.keyboard.add_hotkey", side_effect=("down", "up", "recall")) as add,
            patch("aura_flow.hotkeys.keyboard.remove_hotkey"),
        ):
            controller.bind("push_to_talk")
            call = add.call_args_list[2]
            self.assertEqual(call.args[0], "ctrl+alt+v")
            self.assertTrue(call.kwargs["suppress"])
            self.assertTrue(call.kwargs["trigger_on_release"])
            call.args[1]()
        self.assertEqual(recalled, [True])

    def test_paste_latest_final_reads_history_not_age_limited_cache(self):
        pipeline = DictationPipeline.__new__(DictationPipeline)
        pipeline.history = Mock()
        pipeline.history.recent.return_value = [{"final": "An old but latest finished output."}]
        pipeline.context = Mock()
        pipeline.inserter = Mock()
        pipeline.inserter.insert.return_value = Mock(success=True, method="clipboard", message="ok")
        pipeline.emit = Mock()
        self.assertTrue(pipeline.paste_latest_final())
        pipeline.history.recent.assert_called_once_with(1)
        self.assertEqual(pipeline.inserter.insert.call_args.args[0], "An old but latest finished output.")

    def test_complete_export_contains_history_but_no_secrets(self):
        config = AppConfig(api_key_header="X-Secret-Key", feedback_email="owner@example.com")
        history = Mock()
        history.all_entries.return_value = [{
            "id": "entry", "timestamp": 1, "raw": "um raw", "final": "Raw.",
            "app": "notepad.exe", "cleanup_method": "local-minimal",
        }]
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            metrics = root / "metrics.jsonl"
            metrics.write_text('{"result":"inserted"}\n', encoding="utf-8")
            output = create_testing_export(config, history, metrics, root)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                settings = json.loads(archive.read("settings-sanitized.json"))
                exported_history = archive.read("history.jsonl").decode("utf-8")
            self.assertIn("report.html", names)
            self.assertIn("charts.svg", names)
            self.assertIn("um raw", exported_history)
            self.assertNotIn("api_key_header", settings)
            self.assertNotIn("feedback_email", settings)

    def test_form_export_is_plain_text_scoped_and_sanitized(self):
        config = AppConfig(api_key_header="X-Secret-Key", feedback_email="owner@example.com")
        entries = [{
            "id": "entry", "timestamp": 1, "raw": "um private example",
            "final": "Private example.", "app": "notepad.exe",
        }]
        with tempfile.TemporaryDirectory() as temp_name:
            output = create_form_data_export(
                config, entries, Path(temp_name), "selected dictation",
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(output.suffix, ".txt")
            self.assertEqual(payload["scope"], "selected dictation")
            self.assertEqual(payload["dictation_count"], 1)
            self.assertEqual(payload["dictations"][0]["raw"], "um private example")
            settings = payload["diagnostics"]["settings"]
            self.assertNotIn("api_key_header", settings)
            self.assertNotIn("feedback_email", settings)
            self.assertNotIn("feedback_data_form_url", settings)

    def test_rick_media_finds_a_file_dropped_in_the_test_folder(self):
        with tempfile.TemporaryDirectory() as temp_name:
            app_dir = Path(temp_name)
            dropped = app_dir / "Rick.mp4"
            dropped.touch()
            with patch("aura_flow.rickroll.ASSETS_DIR", app_dir / "assets"), patch(
                "aura_flow.rickroll.INSTALL_DIR", app_dir
            ):
                self.assertEqual(discover_rick_media(video=True), dropped)

    def test_packaged_audio_is_preferred_for_logo_dance(self):
        with tempfile.TemporaryDirectory() as temp_name:
            app_dir = Path(temp_name)
            assets = app_dir / "assets"
            assets.mkdir(parents=True)
            audio = assets / "rickroll-audio.mp3"
            video = assets / "rickroll.mp4"
            audio.touch()
            video.touch()
            with patch("aura_flow.rickroll.ASSETS_DIR", assets), patch(
                "aura_flow.rickroll.INSTALL_DIR", app_dir
            ):
                self.assertEqual(discover_rick_media(video=False), audio)

    def test_nested_packaged_video_is_found(self):
        with tempfile.TemporaryDirectory() as temp_name:
            app_dir = Path(temp_name)
            media_dir = app_dir / "assets" / "rickroll"
            media_dir.mkdir(parents=True)
            video = media_dir / "Rick.mp4"
            video.touch()
            with patch("aura_flow.rickroll.ASSETS_DIR", app_dir / "assets"), patch(
                "aura_flow.rickroll.INSTALL_DIR", app_dir
            ):
                self.assertEqual(discover_rick_media(video=True), video)


if __name__ == "__main__":
    unittest.main()
