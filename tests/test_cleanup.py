import time
import unittest

from aura_flow.cleanup import CleanupService, GrammarPolisher


class SemanticStub:
    available = False


class SlowSemanticStub:
    available = True

    def format(self, text, category, level, style, original_text=None):
        del text, category, level, style, original_text
        time.sleep(0.15)
        return "should not arrive"


class RejectingSemanticStub:
    available = True

    @staticmethod
    def format(*_args, **_kwargs):
        raise ValueError("AI output dropped the beginning of the dictation")


class RecordingSemanticStub:
    available = True

    def __init__(self):
        self.calls = []

    def format(self, text, category, level, style, original_text=None):
        self.calls.append((text, category, level, style, original_text))
        return text


class CleanupTests(unittest.TestCase):
    def test_minimal_preserves_fillers_repeats_and_wording(self):
        self.assertEqual(
            GrammarPolisher.polish("um, i i do not need need that.", "minimal"),
            "Um, I I do not need need that.",
        )

    def test_none_is_verbatim(self):
        source = "i i do not"
        self.assertEqual(GrammarPolisher.polish(source, "none"), source)

    def test_mid_sentence_keeps_spacing_and_lowercase(self):
        self.assertEqual(
            GrammarPolisher.polish(" sounds good ", "minimal", mid_sentence=True),
            " sounds good ",
        )

    def test_explicit_concise_rewrite_can_change_wording(self):
        self.assertEqual(
            GrammarPolisher.rewrite_selection(
                "in order to ship due to the fact that it is ready.",
                "rewrite_concise",
            ),
            "To ship because it's ready.",
        )

    def test_bullet_rewrite(self):
        self.assertEqual(
            GrammarPolisher.rewrite_selection("apples, bananas and pears", "rewrite_bullets"),
            "• Apples\n• Bananas\n• Pears",
        )

    def test_minimal_never_calls_ai(self):
        semantic = RecordingSemanticStub()
        result = CleanupService(semantic).clean("Hello there.", "minimal", "default", "other")
        self.assertEqual(result.method, "local-minimal")
        self.assertEqual(semantic.calls, [])

    def test_smart_receives_near_original_text_once(self):
        semantic = RecordingSemanticStub()
        source = "Um, I really really like this."
        result = CleanupService(semantic).clean(
            source, "smart", "default", "other", original_text=source
        )
        self.assertEqual(result.method, "ai-smart")
        self.assertEqual(len(semantic.calls), 1)
        self.assertEqual(semantic.calls[0][0], source)
        self.assertEqual(semantic.calls[0][2], "smart")

    def test_semantic_timeout_returns_word_preserving_fallback(self):
        service = CleanupService(SlowSemanticStub(), timeout_seconds=0.02)
        result = service.clean("um, i i do not know.", "smart", "default", "other")
        self.assertEqual(result.text, "Um, I I do not know.")
        self.assertTrue(result.fallback)
        self.assertEqual(result.method, "safe-timeout")

    def test_numbered_list_keeps_structure_when_ai_is_unavailable(self):
        result = CleanupService(SemanticStub()).clean(
            "1. First item\n2. Second item", "smart", "default", "other"
        )
        self.assertEqual(result.text, "1. First item\n2. Second item")
        self.assertEqual(result.method, "safe-local")
        self.assertTrue(result.fallback)

    def test_rejection_reason_is_returned_to_the_ui(self):
        result = CleanupService(RejectingSemanticStub()).clean(
            "Hi there.", "smart", "default", "other"
        )
        self.assertEqual(result.method, "safe-rejected")
        self.assertIn("dropped the beginning", result.detail)


if __name__ == "__main__":
    unittest.main()
