import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import datetime
import pytz
from cogs.watchlist import Watchlist
from cogs.subscriptions import SubscriptionCommands

class TestBlacklistEnforcement(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.db = MagicMock()
        self.bot.db.pool = True
        self.bot.wait_until_ready = AsyncMock()

        # Initialize blacklists
        self.bot.blocked_user_ids = [111, 222]
        self.bot.blocked_guild_ids = [999]

    async def test_watchlist_blacklist(self):
        # Setup Watchlist Cog
        cog = Watchlist(self.bot)

        # Mock DB response
        # Two users watching the same player: one blocked, one not.
        cog.db.get_all_online_players = AsyncMock(return_value=[
            {'player_name': 'TargetPlayer', 'current_server_name': 'SomeServer'}
        ])
        cog.db.get_watchlist_subscribers = AsyncMock(return_value=[
            {'user_id': 111, 'player_name': 'TargetPlayer', 'start_hour_utc': None}, # Blocked
            {'user_id': 333, 'player_name': 'TargetPlayer', 'start_hour_utc': None}  # Not Blocked
        ])

        cog.previously_online = set() # Force "just joined"
        cog.previously_online = {'OldPlayer'} # Now TargetPlayer will be seen as just joined

        mock_user_111 = MagicMock()
        mock_user_111.send = AsyncMock()
        mock_user_333 = MagicMock()
        mock_user_333.send = AsyncMock()

        async def fetch_user(uid):
            if uid == 111: return mock_user_111
            if uid == 333: return mock_user_333
            return None

        self.bot.fetch_user = AsyncMock(side_effect=fetch_user)

        # Run the loop iteration once
        await cog.check_watchlist()

        # Verify
        mock_user_111.send.assert_not_called()
        mock_user_333.send.assert_called_once()

        cog.check_watchlist.cancel()

    async def test_subscription_blacklist(self):
        # Setup Subscription Cog
        cog = SubscriptionCommands(self.bot)

        # Mock DB response
        cog.db.get_all_active_servers = AsyncMock(return_value=[
            {'current_server_name': 'Server1', 'current_map': 'MapA', 'current_player_count': 10, 'current_max_players': 32}
        ])

        # Setup last known maps to trigger change
        cog.last_known_maps = {'Server1': 'OldMap'}

        # Matching subs:
        # 1. Blocked User (DM)
        # 2. Blocked Guild (Channel)
        # 3. Normal User (DM)
        # 4. Normal Guild (Channel)
        cog.db.get_matching_subscriptions = AsyncMock(return_value=[
            {'user_id': 111, 'players_over': 0, 'channel_id': None, 'map_name': 'MapA', 'guild_id': 100, 'start_hour_utc': None}, # User Blocked
            {'user_id': 444, 'players_over': 0, 'channel_id': 555, 'map_name': 'MapA', 'guild_id': 999, 'start_hour_utc': None},  # Guild Blocked
            {'user_id': 333, 'players_over': 0, 'channel_id': None, 'map_name': 'MapA', 'guild_id': 100, 'start_hour_utc': None}, # OK DM
            {'user_id': 444, 'players_over': 0, 'channel_id': 666, 'map_name': 'MapA', 'guild_id': 888, 'start_hour_utc': None}   # OK Channel
        ])

        mock_user_111 = MagicMock()
        mock_user_111.send = AsyncMock()
        mock_user_333 = MagicMock()
        mock_user_333.send = AsyncMock()

        async def fetch_user(uid):
            if uid == 111: return mock_user_111
            if uid == 333: return mock_user_333
            return MagicMock()

        self.bot.fetch_user = AsyncMock(side_effect=fetch_user)

        mock_channel_555 = MagicMock()
        mock_channel_555.send = AsyncMock()
        mock_channel_666 = MagicMock()
        mock_channel_666.send = AsyncMock()
        mock_channel_666.guild.me = MagicMock()

        # Mock permissions for channel 666
        perms = MagicMock()
        perms.send_messages = True
        perms.embed_links = True
        mock_channel_666.permissions_for.return_value = perms

        def get_channel(cid):
            if cid == 555: return mock_channel_555
            if cid == 666: return mock_channel_666
            return None

        self.bot.get_channel = MagicMock(side_effect=get_channel)

        # Run
        await cog.check_map_changes()

        # Verify
        mock_user_111.send.assert_not_called()
        mock_channel_555.send.assert_not_called()
        mock_user_333.send.assert_called_once()
        mock_channel_666.send.assert_called_once()

        cog.check_map_changes.cancel()

if __name__ == '__main__':
    unittest.main()
