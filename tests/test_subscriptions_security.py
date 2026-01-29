import unittest
from unittest.mock import AsyncMock, MagicMock
import discord
from cogs.subscriptions import SubscriptionCommands

class TestSubscriptionSecurity(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Common setup
        self.mock_bot = MagicMock()
        self.mock_bot.db = MagicMock()
        self.mock_bot.db.upsert_subscription = AsyncMock() # Must be awaitable
        self.mock_bot.wait_until_ready = AsyncMock()

        # Instantiate Cog
        self.cog = SubscriptionCommands(self.mock_bot)

    async def asyncTearDown(self):
        # Cancel the task loop to clean up
        self.cog.check_map_changes.cancel()

    async def test_subscribe_without_permissions(self):
        # Mock Context
        mock_ctx = MagicMock()
        mock_ctx.author = MagicMock()
        mock_ctx.guild = MagicMock()
        mock_ctx.respond = AsyncMock()

        # Mock Channel
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 12345
        mock_channel.mention = "#channel"

        # Mock Permissions
        bot_perms = MagicMock()
        bot_perms.send_messages = True
        bot_perms.embed_links = True

        user_perms = MagicMock()
        user_perms.manage_channels = False
        user_perms.administrator = False

        def permissions_for(member):
            if member == mock_ctx.guild.me:
                return bot_perms
            if member == mock_ctx.author:
                return user_perms
            return MagicMock()

        mock_channel.permissions_for.side_effect = permissions_for

        # Mock ctx.guild.me
        mock_ctx.guild.me = MagicMock()

        # Execute
        await self.cog.subscribe.callback(self.cog, mock_ctx, "MyServer", "Wake", 0, mock_channel)

        # Verification
        # Should NOT call DB because permission check fails
        self.mock_bot.db.upsert_subscription.assert_not_called()

        # Verify user was warned
        mock_ctx.respond.assert_called_with(
            f"❌ You need **Manage Channels** permission in {mock_channel.mention} to set up alerts there.",
            ephemeral=True
        )

    async def test_subscribe_server_without_permissions(self):
        mock_ctx = MagicMock()
        mock_ctx.author = MagicMock()
        mock_ctx.guild = MagicMock()
        mock_ctx.respond = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 12345
        mock_channel.mention = "#channel"

        bot_perms = MagicMock()
        bot_perms.send_messages = True
        bot_perms.embed_links = True

        user_perms = MagicMock()
        user_perms.manage_channels = False
        user_perms.administrator = False

        def permissions_for(member):
            if member == mock_ctx.guild.me:
                return bot_perms
            if member == mock_ctx.author:
                return user_perms
            return MagicMock()

        mock_channel.permissions_for.side_effect = permissions_for
        mock_ctx.guild.me = MagicMock()

        # Execute
        await self.cog.subscribe_server.callback(self.cog, mock_ctx, "MyServer", 0, mock_channel)

        # Verification
        self.mock_bot.db.upsert_subscription.assert_not_called()

        mock_ctx.respond.assert_called_with(
            f"❌ You need **Manage Channels** permission in {mock_channel.mention} to set up alerts there.",
            ephemeral=True
        )

if __name__ == '__main__':
    unittest.main()
