import unittest

from aura_flow.pipeline import (
    choose_recovered_transcript,
    final_asr_is_incomplete,
    tiny_live_is_final,
)


class FinalAsrRecoveryTests(unittest.TestCase):
    live = (
        "This is the full rolling preview with every important point from the dictation "
        "and several more details that must not disappear when recording stops."
    )

    def test_short_final_is_detected_against_full_live_preview(self):
        self.assertTrue(final_asr_is_incomplete("A few words.", self.live))

    def test_normal_final_is_not_replaced(self):
        final = "This is the accurate final transcript with every important point and all requested details."
        self.assertFalse(final_asr_is_incomplete(final, self.live))

    def test_full_no_vad_retry_wins_over_short_first_pass(self):
        retry = "This is the complete retry containing every important point and all the requested details."
        text, method = choose_recovered_transcript("A few words.", retry, self.live)
        self.assertEqual(text, retry)
        self.assertEqual(method, "final-retry")

    def test_live_preview_is_preserved_when_both_final_passes_are_short(self):
        text, method = choose_recovered_transcript("A few words.", "Still too short.", self.live)
        self.assertEqual(text, self.live)
        self.assertEqual(method, "live-preview-recovery")

    def test_tiny_mode_uses_live_transcript_without_second_pass(self):
        self.assertTrue(tiny_live_is_final("tiny.en", self.live))
        self.assertFalse(tiny_live_is_final("medium", self.live))
        self.assertFalse(tiny_live_is_final("tiny.en", "two words"))


if __name__ == "__main__":
    unittest.main()
