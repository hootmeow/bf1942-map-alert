import unittest
from core.database import Database

class TestSQLSanitization(unittest.TestCase):
    def setUp(self):
        # We don't need a real DSN for these tests as we are testing a non-async method
        self.db = Database("postgres://user:pass@host/db")

    def test_sanitize_like(self):
        # Test basic characters
        self.assertEqual(self.db._sanitize_like("normal"), "normal")

        # Test wildcards
        self.assertEqual(self.db._sanitize_like("test%"), "test!%")
        self.assertEqual(self.db._sanitize_like("test_"), "test!_")

        # Test escape character
        self.assertEqual(self.db._sanitize_like("test!"), "test!!")

        # Test combination
        self.assertEqual(self.db._sanitize_like("!%_"), "!!!%!_")

        # Test empty string
        self.assertEqual(self.db._sanitize_like(""), "")

if __name__ == '__main__':
    unittest.main()
