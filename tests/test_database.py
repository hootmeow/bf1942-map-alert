import unittest
from core.database import Database

class TestDatabaseSanitization(unittest.TestCase):
    def setUp(self):
        # We don't need a real DSN for testing the sanitization helper
        self.db = Database("postgres://user:pass@host:5432/db")

    def test_sanitize_like_percent(self):
        input_str = "100% pure"
        expected = "100\\% pure"
        self.assertEqual(self.db._sanitize_like(input_str), expected)

    def test_sanitize_like_underscore(self):
        input_str = "player_name"
        expected = "player\\_name"
        self.assertEqual(self.db._sanitize_like(input_str), expected)

    def test_sanitize_like_backslash(self):
        input_str = "path\\to"
        expected = "path\\\\to"
        self.assertEqual(self.db._sanitize_like(input_str), expected)

    def test_sanitize_like_mixed(self):
        input_str = "50%_discount\\"
        expected = "50\\%\\_discount\\\\"
        self.assertEqual(self.db._sanitize_like(input_str), expected)

    def test_sanitize_like_no_wildcards(self):
        input_str = "normal string"
        expected = "normal string"
        self.assertEqual(self.db._sanitize_like(input_str), expected)

if __name__ == '__main__':
    unittest.main()
