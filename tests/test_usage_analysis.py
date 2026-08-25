import unittest
from datetime import datetime, timedelta

from aura_flow.usage_analysis import analyze_usage


class UsageAnalysisTests(unittest.TestCase):
    def test_local_language_insights(self):
        today = datetime.now()
        entries = [
            {
                "timestamp": (today - timedelta(days=1)).timestamp(),
                "raw": "Yeah, so, gradient gradient motion.",
                "final": "Gradient gradient motion.",
            },
            {
                "timestamp": today.timestamp(),
                "raw": "Um, gradient motion works.",
                "final": "Gradient motion works.",
            },
        ]
        result = analyze_usage(entries)
        self.assertEqual(result["favorite_word"], "gradient")
        self.assertEqual(result["favorite_word_count"], 3)
        self.assertEqual(result["longest_streak"], 2)
        self.assertGreater(result["filler_rate"], 0)
        self.assertGreater(result["cleanup_reduction"], 0)

    def test_empty_history(self):
        result = analyze_usage([])
        self.assertEqual(result["favorite_word"], "—")
        self.assertEqual(result["average_words"], 0)
        self.assertEqual(result["longest_streak"], 0)


if __name__ == "__main__":
    unittest.main()
