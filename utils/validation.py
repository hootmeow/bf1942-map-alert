import discord

class ValidationError(Exception):
    """Exception raised for validation errors."""
    pass

def validate_input_length(value: str, max_length: int, name: str):
    """
    Validates that the input string is within the specified length.

    Args:
        value (str): The input string to validate.
        max_length (int): The maximum allowed length.
        name (str): The name of the field (for error messages).

    Raises:
        ValidationError: If the value exceeds max_length.
    """
    if not value:
        return # Empty values might be handled elsewhere or are allowed

    if len(value) > max_length:
        raise ValidationError(f"❌ {name} is too long (max {max_length} characters).")

def sanitize_text(text: str) -> str:
    """
    Escapes Discord markdown and mentions to prevent formatting disruption.
    """
    if not text:
        return ""
    # We use escape_mentions to handle @everyone, @here, etc.
    text = discord.utils.escape_mentions(str(text))
    # Then escape_markdown for formatting characters
    return discord.utils.escape_markdown(text)
