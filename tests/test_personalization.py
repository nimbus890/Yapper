import tempfile
import unittest
from pathlib import Path

from aura_flow.personalization import PersonalizationStore


class PersonalizationTests(unittest.TestCase):
    def test_round_trip_and_hotwords(self):
        with tempfile.TemporaryDirectory() as folder:
            store = PersonalizationStore(Path(folder) / "personalization.json")
            store.add_vocabulary("PostgreSQL")
            store.set_replacement("post grass", "Postgres")
            store.set_snippet("Meeting Link", "https://meet.example")
            loaded = PersonalizationStore(store.path)
            self.assertEqual(loaded.data.snippets["meeting link"], "https://meet.example")
            self.assertIn("PostgreSQL", loaded.hotwords())
            self.assertIn("Postgres", loaded.hotwords())

    def test_remove_operations(self):
        with tempfile.TemporaryDirectory() as folder:
            store = PersonalizationStore(Path(folder) / "personalization.json")
            store.add_vocabulary("Aura")
            store.set_replacement("ora", "Aura")
            store.set_snippet("email", "person@example.com")
            store.remove_vocabulary("Aura")
            store.remove_replacement("ora")
            store.remove_snippet("email")
            self.assertEqual(store.data.vocabulary, [])
            self.assertEqual(store.data.replacements, {})
            self.assertEqual(store.data.snippets, {})

    def test_direct_edits_rename_vocabulary_and_mapping_cells(self):
        with tempfile.TemporaryDirectory() as folder:
            store = PersonalizationStore(Path(folder) / "personalization.json")
            store.add_vocabulary("Postgres")
            store.set_replacement("post grass", "Postgres")
            store.set_snippet("Meeting Link", "https://old.example")

            self.assertTrue(store.update_vocabulary("Postgres", "PostgreSQL"))
            self.assertTrue(
                store.update_pair("replacements", "post grass", "post grez", "PostgreSQL")
            )
            self.assertTrue(
                store.update_pair("snippets", "meeting link", "Team Link", "https://new.example")
            )

            loaded = PersonalizationStore(store.path)
            self.assertEqual(loaded.data.vocabulary, ["PostgreSQL"])
            self.assertEqual(loaded.data.replacements, {"post grez": "PostgreSQL"})
            self.assertEqual(loaded.data.snippets, {"team link": "https://new.example"})

    def test_direct_edits_reject_empty_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            store = PersonalizationStore(Path(folder) / "personalization.json")
            store.add_vocabulary("Alpha")
            store.add_vocabulary("Beta")
            store.set_replacement("one", "1")
            store.set_replacement("two", "2")
            self.assertFalse(store.update_vocabulary("Alpha", "Beta"))
            self.assertFalse(store.update_pair("replacements", "one", "two", "updated"))
            self.assertFalse(store.update_pair("replacements", "one", "", "updated"))


if __name__ == "__main__":
    unittest.main()
