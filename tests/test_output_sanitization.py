import unittest
from utils.validation import sanitize_text, sanitize_for_codeblock

class TestOutputSanitization(unittest.TestCase):
    def test_sanitize_text(self):
        # Basic markdown escaping
        self.assertEqual(sanitize_text("**bold**"), r"\*\*bold\*\*")
        self.assertEqual(sanitize_text("`code`"), r"\`code\`")
        # Mentions escaping
        self.assertEqual(sanitize_text("@everyone"), "@\u200beveryone")

    def test_sanitize_for_codeblock(self):
        # Should replace backticks with a similar character
        self.assertEqual(sanitize_for_codeblock("foo`bar"), "foo\u02cbbar")
        self.assertEqual(sanitize_for_codeblock("```"), "\u02cb\u02cb\u02cb")
        # Should handle None/empty
        self.assertEqual(sanitize_for_codeblock(None), "")
        self.assertEqual(sanitize_for_codeblock(""), "")
        # Should NOT escape other markdown (since it's for inside a code block)
        self.assertEqual(sanitize_for_codeblock("**bold**"), "**bold**")

if __name__ == '__main__':
    unittest.main()
