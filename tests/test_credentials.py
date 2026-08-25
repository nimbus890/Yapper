import os
import tempfile
import unittest
from pathlib import Path

from aura_flow.credentials import ApiCredentialStore


@unittest.skipUnless(os.name == "nt", "Windows DPAPI is required")
class ApiCredentialStoreTests(unittest.TestCase):
    def test_dpapi_round_trip_and_clear(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "api_key.bin"
            store = ApiCredentialStore(path)
            store.save("test-key-not-real")
            self.assertEqual(store.load(), "test-key-not-real")
            self.assertNotIn(b"test-key-not-real", path.read_bytes())
            store.clear()
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
