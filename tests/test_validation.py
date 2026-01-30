import unittest
from utils.validation import validate_input_length, ValidationError

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
