import unittest
import discord
from unittest.mock import patch, AsyncMock, MagicMock
from bot import BF1942Bot

class TestMentionSecurity(unittest.IsolatedAsyncioTestCase):
    @patch('bot.os.getenv')
    @patch('bot.load_dotenv')
    async def test_bot_allowed_mentions(self, mock_load_dotenv, mock_getenv):
        # Mock environment variables to avoid real config loading
        def getenv_side_effect(key):
            if key == "DISCORD_TOKEN": return "fake-token"
            if key == "POSTGRES_DSN": return "postgres://user:pass@localhost/db"
            return None
        mock_getenv.side_effect = getenv_side_effect

        # We also want to prevent the bot from actually loading extensions or connecting to DB
        with patch.object(BF1942Bot, 'load_extensions', return_value=None):
            with patch('bot.Database') as mock_db_class:
                mock_db_instance = mock_db_class.return_value
                mock_db_instance.close = AsyncMock()

                bot = BF1942Bot()

                allowed_mentions = bot.allowed_mentions

                self.assertIsNotNone(allowed_mentions, "Bot should have allowed_mentions configured")
                self.assertFalse(allowed_mentions.everyone, "everyone mentions should be disabled")
                self.assertFalse(allowed_mentions.roles, "role mentions should be disabled")

                # Cleanup
                await bot.close()

if __name__ == '__main__':
    unittest.main()
