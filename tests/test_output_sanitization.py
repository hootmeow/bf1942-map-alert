import unittest
from utils.validation import sanitize_for_codeblock, sanitize_text

class TestOutputSanitization(unittest.TestCase):
    def test_sanitize_for_codeblock(self):
        # Normal text should remain unchanged
        self.assertEqual(sanitize_for_codeblock("normal"), "normal")

        # Backticks should be replaced by \u02cb
        self.assertEqual(sanitize_for_codeblock("`code`"), "\u02cbcode\u02cb")
        self.assertEqual(sanitize_for_codeblock("```"), "\u02cb\u02cb\u02cb")

        # Mixed content
        self.assertEqual(sanitize_for_codeblock("Player ` name"), "Player \u02cb name")

    def test_sanitize_for_codeblock_empty(self):
        self.assertEqual(sanitize_for_codeblock(""), "")
        self.assertEqual(sanitize_for_codeblock(None), "")

    def test_sanitize_text_integration(self):
        # Ensure sanitize_text still works as expected (it's already tested but good to have here)
        self.assertEqual(sanitize_text("**bold**"), r"\*\*bold\*\*")
        self.assertEqual(sanitize_text("@everyone"), "@\u200beveryone")

if __name__ == '__main__':
    unittest.main()
