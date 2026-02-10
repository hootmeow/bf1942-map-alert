import unittest
from utils.validation import sanitize_text, sanitize_for_codeblock
import discord

class TestMentionSecurity(unittest.TestCase):
    def test_sanitize_text_markdown(self):
        # Test basic markdown escaping
        self.assertEqual(sanitize_text("normal"), "normal")
        self.assertEqual(sanitize_text("**bold**"), r"\*\*bold\*\*")
        self.assertEqual(sanitize_text("__under__"), r"\_\_under\_\_")
        self.assertEqual(sanitize_text("`code`"), r"\`code\`")

    def test_sanitize_text_mentions(self):
        # Test mention character escaping
        # discord.utils.escape_mentions adds a zero-width space ( \u200b ) after @ for everyone/here
        self.assertEqual(sanitize_text("@everyone"), "@\u200beveryone")
        self.assertEqual(sanitize_text("@here"), "@\u200bhere")

    def test_sanitize_text_none_and_empty(self):
        self.assertEqual(sanitize_text(None), "")
        self.assertEqual(sanitize_text(""), "")

    def test_sanitize_for_codeblock(self):
        # Test backtick escaping for codeblocks
        self.assertEqual(sanitize_for_codeblock("normal"), "normal")
        self.assertEqual(sanitize_for_codeblock("`code`"), "\u02cbcode\u02cb")
        self.assertEqual(sanitize_for_codeblock("```"), "\u02cb\u02cb\u02cb")
        self.assertEqual(sanitize_for_codeblock(None), "")

if __name__ == '__main__':
    unittest.main()
