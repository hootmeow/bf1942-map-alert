import unittest
from utils.validation import validate_input_length, ValidationError, sanitize_for_codeblock

class TestValidation(unittest.TestCase):
    def test_valid_input(self):
        """Should not raise error for valid input."""
        validate_input_length("test", 10, "Input")

    def test_exact_limit(self):
        """Should not raise error for input with exact max length."""
        validate_input_length("12345", 5, "Input")

    def test_too_long(self):
        """Should raise ValidationError for input longer than max length."""
        with self.assertRaises(ValidationError) as cm:
            validate_input_length("123456", 5, "MyField")
        self.assertIn("MyField is too long", str(cm.exception))

    def test_empty(self):
        """Should not raise error for empty input (handled as valid length)."""
        validate_input_length("", 5, "Input")

    def test_sanitize_for_codeblock(self):
        """Should replace backticks with a safe character."""
        # Test basic replacement
        self.assertEqual(sanitize_for_codeblock("test`name"), "testˋname")
        # Test multiple backticks
        self.assertEqual(sanitize_for_codeblock("``breakout``"), "ˋˋbreakoutˋˋ")
        # Test empty input
        self.assertEqual(sanitize_for_codeblock(""), "")
        self.assertEqual(sanitize_for_codeblock(None), "")
        # Test normal name
        self.assertEqual(sanitize_for_codeblock("NormalPlayer"), "NormalPlayer")
