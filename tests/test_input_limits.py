import unittest
from unittest.mock import AsyncMock, MagicMock
from cogs.watchlist import Watchlist
from cogs.subscriptions import SubscriptionCommands
from cogs.stats import StatCommands
from utils.validation import ValidationError

class TestInputLimits(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot.db = MagicMock()
        # Mock methods to be awaitable
        self.mock_bot.db.init_watchlist_table = AsyncMock()
        self.mock_bot.db.add_watchlist = AsyncMock()
        self.mock_bot.db.upsert_subscription = AsyncMock()
        self.mock_bot.db.find_player = AsyncMock()
        self.mock_bot.wait_until_ready = AsyncMock()

    async def test_watch_limit(self):
        cog = Watchlist(self.mock_bot)
        # Stop the loop
        cog.check_watchlist.cancel()

        mock_ctx = MagicMock()
        mock_ctx.defer = AsyncMock()
        mock_ctx.followup.send = AsyncMock()
        mock_ctx.author.id = 123

        long_name = "a" * 65
        await cog.watch.callback(cog, mock_ctx, long_name)

        # Should call followup.send with error
        mock_ctx.followup.send.assert_called_once()
        args, _ = mock_ctx.followup.send.call_args
        self.assertIn("Player Name is too long", args[0])

        # Should NOT call DB
        self.mock_bot.db.add_watchlist.assert_not_called()

    async def test_subscribe_limit(self):
        cog = SubscriptionCommands(self.mock_bot)
        cog.check_map_changes.cancel()

        mock_ctx = MagicMock()
        mock_ctx.respond = AsyncMock() # subscribe uses respond not defer/followup usually?
        # Wait, the code uses ctx.respond for errors before DB call?
        # Let's check code.
        # Yes: await ctx.respond(str(e), ephemeral=True)

        mock_ctx.author.id = 123
        mock_ctx.guild.id = 456

        # Test Long Server Name
        long_server = "a" * 129
        await cog.subscribe.callback(cog, mock_ctx, long_server, "map", 0, None)

        mock_ctx.respond.assert_called()
        args, _ = mock_ctx.respond.call_args
        self.assertIn("Server Name is too long", args[0])
        self.mock_bot.db.upsert_subscription.assert_not_called()

    async def test_find_limit(self):
        cog = StatCommands(self.mock_bot)

        mock_ctx = MagicMock()
        mock_ctx.defer = AsyncMock()
        mock_ctx.followup.send = AsyncMock()

        long_name = "a" * 65
        await cog.find.callback(cog, mock_ctx, long_name)

        mock_ctx.followup.send.assert_called_once()
        args, _ = mock_ctx.followup.send.call_args
        self.assertIn("Player Name is too long", args[0])
        self.mock_bot.db.find_player.assert_not_called()

if __name__ == '__main__':
    unittest.main()
