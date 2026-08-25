import unittest

from aura_flow.insertion import _escape_uia_keys, _safe_for_direct_sendkeys


class InsertionTests(unittest.TestCase):
    def test_uia_literal_braces_and_newlines(self):
        self.assertEqual(_escape_uia_keys("a{b}\nc}"), "a{{}b{}}{Enter}c{}}")

    def test_multiline_text_bypasses_direct_sendkeys(self):
        self.assertTrue(_safe_for_direct_sendkeys("one complete line"))
        self.assertFalse(_safe_for_direct_sendkeys("first line\nsecond line"))
        self.assertFalse(_safe_for_direct_sendkeys("first line\r\nsecond line"))


if __name__ == "__main__":
    unittest.main()
