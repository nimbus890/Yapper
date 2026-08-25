import threading
import time
import unittest
from types import SimpleNamespace

import numpy as np

from aura_flow.partial import PartialTranscriber, last_words, merge_partial_transcript


class PartialTranscriptTests(unittest.TestCase):
    def test_shared_tiny_engine_is_reused(self):
        engine = object()
        config = SimpleNamespace(partial_transcription=True, partial_model_path=None)
        partial = PartialTranscriber(config, SimpleNamespace(), lambda *_args: None)
        partial.use_shared_engine(engine)
        self.assertIs(partial.engine, engine)
        self.assertTrue(partial.ready)

    def test_extending_window_becomes_cumulative(self):
        current = merge_partial_transcript("", "Hello this is a test")
        current = merge_partial_transcript(current, "this is a test of Aura Flow")
        self.assertEqual(current, "Hello this is a test of Aura Flow")

    def test_punctuation_does_not_break_overlap(self):
        merged = merge_partial_transcript("Hello there, how are", "there how are you today?")
        self.assertEqual(merged, "Hello there, how are you today?")

    def test_no_overlap_preserves_both_windows(self):
        self.assertEqual(merge_partial_transcript("First thought.", "Second thought."), "First thought. Second thought.")

    def test_revised_rolling_window_replaces_tail_instead_of_doubling_it(self):
        current = "Hi there I am testing the raw dictation in the dashboard right now"
        latest = "testing raw dictation in dashboard right now and it should stay clean"
        merged = merge_partial_transcript(current, latest)
        self.assertEqual(merged.count("raw dictation"), 1)
        self.assertTrue(merged.endswith("and it should stay clean"))

    def test_overlapping_window_with_punctuation_revision_is_not_duplicated(self):
        current = "This is one sentence and here comes another sentence"
        latest = "and here comes another sentence, with several new words"
        merged = merge_partial_transcript(current, latest)
        self.assertEqual(
            merged,
            "This is one sentence and here comes another sentence, with several new words",
        )

    def test_overlay_keeps_latest_ten_words(self):
        text = "one two three four five six seven eight nine ten eleven twelve"
        self.assertEqual(
            last_words(text),
            "three four five six seven eight nine ten eleven twelve",
        )

    def test_session_joins_model_that_finishes_loading_after_recording_starts(self):
        class Buffer:
            @staticmethod
            def snapshot():
                return SimpleNamespace(samples=np.ones(20, dtype=np.float32))

        class Engine:
            @staticmethod
            def transcribe(_samples):
                return SimpleNamespace(text="one two three four five six seven eight nine ten eleven")

        config = SimpleNamespace(
            partial_transcription=True,
            partial_interval_seconds=0.02,
            partial_tail_seconds=1.0,
            partial_preview_words=10,
            sample_rate=20,
        )
        received = []
        delivered = threading.Event()
        partial = PartialTranscriber(
            config,
            SimpleNamespace(buffer=Buffer()),
            lambda preview, cumulative: (received.append((preview, cumulative)), delivered.set()),
        )
        partial.start_session()
        time.sleep(0.04)
        partial.engine = Engine()
        partial.ready = True
        self.assertTrue(delivered.wait(0.7))
        cumulative = partial.stop_session()
        self.assertEqual(received[0][0], "two three four five six seven eight nine ten eleven")
        self.assertEqual(cumulative, received[-1][1])


if __name__ == "__main__":
    unittest.main()
