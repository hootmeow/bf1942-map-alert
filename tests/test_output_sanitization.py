import unittest
from utils.validation import sanitize_text, sanitize_for_codeblock

class TestOutputSanitization(unittest.TestCase):
    def test_sanitize_text_basic(self):
        self.assertEqual(sanitize_text("normal"), "normal")
        self.assertEqual(sanitize_text(""), "")
        self.assertEqual(sanitize_text(None), "")

    def test_sanitize_text_markdown(self):
        # escape_markdown should escape these
        self.assertEqual(sanitize_text("**bold**"), r"\*\*bold\*\*")
        self.assertEqual(sanitize_text("_italic_"), r"\_italic\_")
        self.assertEqual(sanitize_text("`code`"), r"\`code\`")

    def test_sanitize_text_mentions(self):
        # escape_mentions should escape these
        self.assertIn("@\u200beveryone", sanitize_text("@everyone"))
        self.assertIn("@\u200bhere", sanitize_text("@here"))

    def test_sanitize_for_codeblock(self):
        # Should replace backticks with visually similar character
        self.assertEqual(sanitize_for_codeblock("`test`"), "\u02cbtest\u02cb")
        self.assertEqual(sanitize_for_codeblock("```triple```"), "\u02cb\u02cb\u02cbtriple\u02cb\u02cb\u02cb")
        self.assertEqual(sanitize_for_codeblock("no backticks"), "no backticks")
        self.assertEqual(sanitize_for_codeblock(""), "")
        self.assertEqual(sanitize_for_codeblock(None), "")

if __name__ == '__main__':
    unittest.main()
