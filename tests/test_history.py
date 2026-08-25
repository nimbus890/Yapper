import tempfile
import unittest
from pathlib import Path

from aura_flow.history import HistoryStore


class HistoryTests(unittest.TestCase):
    def test_entry_id_search_and_stats(self):
        with tempfile.TemporaryDirectory() as folder:
            store = HistoryStore(Path(folder) / "history.jsonl", True)
            entry = store.append("raw words", "Final words here", {"audio_seconds": 2.0})
            self.assertEqual(store.get(str(entry["id"]))["raw"], "raw words")
            self.assertEqual(len(store.recent(query="final")), 1)
            stats = store.stats(typing_wpm=40)
            self.assertEqual(stats["words_today"], 3)
            self.assertEqual(stats["total_words"], 3)


if __name__ == "__main__":
    unittest.main()
