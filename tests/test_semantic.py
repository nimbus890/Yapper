import unittest

from aura_flow.semantic import (
    SMART_INSTRUCTION,
    extract_protected_literals,
    verify_not_truncated,
    verify_preserved_intent,
    verify_protected_literals,
)


class SemanticSafetyTests(unittest.TestCase):
    def test_smart_prompt_is_compact_and_preservation_first(self):
        self.assertLess(len(SMART_INSTRUCTION), 2_000)
        self.assertIn("Copy-edit this voice transcript", SMART_INSTRUCTION)
        self.assertIn('never change meaningful "yeah" to "yes"', SMART_INSTRUCTION)
        self.assertIn("very very very important", SMART_INSTRUCTION)
        self.assertIn('never turn the\ncorrection marker "no" into "not"', SMART_INSTRUCTION)
        self.assertIn("Do not omit the beginning\nor ending", SMART_INSTRUCTION)
        self.assertIn('preserve informal but meaningful openings', SMART_INSTRUCTION)
        self.assertIn('Raw: Yo, okay, this is test number one', SMART_INSTRUCTION)
        self.assertIn("That's it, thanks", SMART_INSTRUCTION)

    def test_rejects_three_word_fragment_from_long_dictation(self):
        source = "This is a complete dictation with several important details about the release plan tomorrow morning."
        with self.assertRaisesRegex(ValueError, "unexpectedly shortened"):
            verify_not_truncated(source, "Release plan tomorrow.")

    def test_accepts_normal_filler_and_repeat_cleanup(self):
        source = "Um I think I think we should send the complete report to Maya tomorrow morning."
        generated = "I think we should send the complete report to Maya tomorrow morning."
        self.assertEqual(verify_not_truncated(source, generated), generated)

    def test_rejects_output_that_keeps_length_but_drops_content(self):
        source = "Please send the complete quarterly report to Maya before the planning meeting tomorrow morning."
        generated = "This unrelated response contains enough words to look long while losing the dictated content entirely."
        with self.assertRaisesRegex(ValueError, "dropped too much"):
            verify_not_truncated(source, generated)

    def test_rejects_v36_output_that_dropped_the_opening(self):
        source = (
            "Hi, this is Yapper. Well, you might be wondering what all I can do. "
            "Number one, I can capture everything you say. Number two, I can clean it up. "
            "It is useful and I hope you like it because I made it in one afternoon let's go."
        )
        generated = (
            "1. I can capture everything you say. 2. I can clean it up. "
            "It is useful and I hope you like it because I made it in one afternoon."
        )
        with self.assertRaisesRegex(ValueError, "beginning"):
            verify_preserved_intent(source, generated)

    def test_rejects_short_output_that_dropped_a_meaningful_yo(self):
        source = "Yo, this is how it's gonna work, and I do not like these overlapping lines."
        generated = "This is how it's gonna work, and I do not like these overlapping lines."
        with self.assertRaisesRegex(ValueError, "beginning"):
            verify_preserved_intent(source, generated)

    def test_rejects_removed_three_word_emphasis(self):
        source = "This is very very very important, and I want the emphasis to stay exactly."
        generated = "This is very important, and I want the emphasis to stay exactly."
        with self.assertRaisesRegex(ValueError, "intentional repetition"):
            verify_preserved_intent(source, generated)

    def test_rejects_v36_output_that_dropped_the_ending(self):
        source = (
            "Hi, this is Yapper and it can transcribe anything you say. It will format everything. "
            "It is a smart thing too. This was made in one afternoon, so I hope you like it."
        )
        generated = (
            "Hi, this is Yapper and it can transcribe anything you say. It will format everything. "
            "It is a smart thing too. This was made in one."
        )
        with self.assertRaisesRegex(ValueError, "end"):
            verify_preserved_intent(source, generated)

    def test_rejects_correction_reversal_from_v36(self):
        source = "It is going to launch on Thursday, no Friday morning."
        generated = "It is going to launch on Thursday, not Friday morning."
        with self.assertRaisesRegex(ValueError, "reversed"):
            verify_preserved_intent(source, generated)

    def test_accepts_preserved_opening_correction_and_ending(self):
        source = (
            "Hi, this is Yapper and here is the release update. It launches Thursday, no Friday morning. "
            "The build is stable and I really hope you like it thank you."
        )
        generated = (
            "Hi, this is Yapper, and here is the release update. It launches Friday morning. "
            "The build is stable, and I really hope you like it. Thank you."
        )
        self.assertEqual(verify_preserved_intent(source, generated), generated)

    def test_typographic_apostrophes_do_not_look_like_lost_content(self):
        source = (
            "Well, it's a complete thought about the design and that's exactly how "
            "I'd like the finished version to read when it's ready."
        )
        generated = (
            "Well, it’s a complete thought about the design, and that’s exactly how "
            "I’d like the finished version to read when it’s ready."
        )
        self.assertEqual(verify_preserved_intent(source, generated), generated)

    def test_extracts_amount_version_email_and_url_exactly(self):
        source = "Send ₹2,500.50 to maya@example.com at https://example.com/report for v2.4."
        self.assertEqual(
            extract_protected_literals(source),
            ["₹2,500.50", "maya@example.com", "https://example.com/report", "v2.4"],
        )

    def test_unchanged_literals_are_accepted(self):
        source = "Send 25 dollars to maya@example.com."
        generated = "Please send 25 dollars to maya@example.com."
        self.assertEqual(verify_protected_literals(source, generated), generated)

    def test_changed_missing_duplicated_or_new_literal_is_rejected(self):
        cases = (
            ("Send 25 dollars.", "Send 50 dollars."),
            ("Version 2.4 ships.", "It ships."),
            ("Use 25GB.", "Use 25GB and another 25GB."),
            ("Send the report.", "Send 50 copies of the report."),
        )
        for source, generated in cases:
            with self.subTest(source=source, generated=generated):
                with self.assertRaisesRegex(ValueError, "protected literal"):
                    verify_protected_literals(source, generated)


if __name__ == "__main__":
    unittest.main()
