import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import datetime
import pytz
from cogs.subscriptions import SubscriptionCommands
from cogs.watchlist import Watchlist

class TestBlacklistEnforcement(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot.db = MagicMock()
        self.mock_bot.db.pool = MagicMock()
        self.mock_bot.wait_until_ready = AsyncMock()

        # Setup blacklists
        self.mock_bot.blocked_user_ids = [123]
        self.mock_bot.blocked_guild_ids = [456]

    async def test_subscription_alerts_respect_blacklist(self):
        # Instantiate Cog
        cog = SubscriptionCommands(self.mock_bot)
        cog.last_known_maps = {"Server1": "OldMap"}

        # Mock database responses
        self.mock_bot.db.get_all_active_servers = AsyncMock(return_value=[
            {"current_server_name": "Server1", "current_map": "NewMap", "current_player_count": 10, "current_max_players": 64}
        ])

        # Two subscriptions: one blocked user, one blocked guild
        self.mock_bot.db.get_matching_subscriptions = AsyncMock(return_value=[
            {
                "user_id": 123, # Blocked user
                "guild_id": 789,
                "players_over": 0,
                "channel_id": None,
                "map_name": "newmap",
                "start_hour_utc": None,
                "end_hour_utc": None,
                "weekdays_utc": None
            },
            {
                "user_id": 999,
                "guild_id": 456, # Blocked guild
                "players_over": 0,
                "channel_id": 111,
                "map_name": "newmap",
                "start_hour_utc": None,
                "end_hour_utc": None,
                "weekdays_utc": None
            }
        ])

        # Mock fetch_user and get_channel
        self.mock_bot.fetch_user = AsyncMock()
        self.mock_bot.get_channel = MagicMock(return_value=None)

        # Run one iteration of the task
        await cog.check_map_changes()

        # Verification: fetch_user should NOT be called for blocked user 123
        self.mock_bot.fetch_user.assert_not_called()
        # Verification: get_channel should NOT be called for blocked guild 456
        self.mock_bot.get_channel.assert_not_called()

        cog.check_map_changes.cancel()

    async def test_watchlist_alerts_respect_blacklist(self):
        # Instantiate Cog
        cog = Watchlist(self.mock_bot)
        cog.previously_online = set()

        # Mock database responses
        self.mock_bot.db.get_all_online_players = AsyncMock(return_value=[
            {"player_name": "Player1", "current_server_name": "Server1"}
        ])

        # Seed previously online so it detects a "join"
        cog.previously_online = set()
        # To trigger just_joined, we need previously_online to be non-empty but NOT contain Player1
        cog.previously_online = {"OtherPlayer"}

        self.mock_bot.db.get_watchlist_subscribers = AsyncMock(return_value=[
            {
                "user_id": 123, # Blocked user
                "player_name": "Player1",
                "start_hour_utc": None,
                "end_hour_utc": None,
                "weekdays_utc": None
            }
        ])

        # Mock fetch_user
        self.mock_bot.fetch_user = AsyncMock()

        # Run one iteration of the task
        await cog.check_watchlist()

        # Verification: fetch_user should NOT be called for blocked user 123
        self.mock_bot.fetch_user.assert_not_called()

        cog.check_watchlist.cancel()

if __name__ == '__main__':
    unittest.main()
