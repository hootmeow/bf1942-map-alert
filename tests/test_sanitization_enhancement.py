import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import discord
from cogs.servers import ServerCommands
from utils.validation import sanitize_text, sanitize_for_codeblock

class TestSanitizationEnhancement(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.bot.wait_until_ready = AsyncMock()
        self.db = MagicMock()
        self.bot.db = self.db
        self.cog = ServerCommands(self.bot)

    async def test_playing_command_sanitization(self):
        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.defer = AsyncMock()
        ctx.followup.send = AsyncMock()
        ctx.bot = self.bot

        malicious_server_name = "@everyone **BOOM**"
        self.db.get_servers_by_map = AsyncMock(return_value=[
            {
                'current_server_name': malicious_server_name,
                'current_player_count': 10,
                'current_max_players': 64
            }
        ])

        await self.cog.playing.callback(self.cog, ctx, "wake_island")

        self.assertTrue(ctx.followup.send.called)
        args, kwargs = ctx.followup.send.call_args
        embed = kwargs.get('embed') or args[0]

        description = embed.description
        sanitized_name = sanitize_text(malicious_server_name)
        self.assertIn(sanitized_name, description)

    async def test_serverinfo_codeblock_sanitization(self):
        ctx = MagicMock(spec=discord.ApplicationContext)
        ctx.defer = AsyncMock()
        ctx.followup.send = AsyncMock()

        malicious_player_name = "Player ``` @everyone"
        self.db.get_server_details = AsyncMock(return_value={
            'current_server_name': 'Test Server',
            'current_map': 'Wake Island',
            'current_player_count': 1,
            'current_max_players': 64,
            'unpure_mods': None,
            'current_gametype': 'Conquest',
            'ip': '127.0.0.1',
            'port': 14567,
            'current_game_port': 14567,
            'round_time_remain': 1000,
            'tickets1': 100,
            'tickets2': 100
        })
        self.db.get_server_players = AsyncMock(return_value=[
            {
                'player_name': malicious_player_name,
                'score': 100,
                'kills': 10,
                'deaths': 5,
                'ping': 50,
                'team': 1
            }
        ])

        await self.cog.serverinfo.callback(self.cog, ctx, "Test Server")

        self.assertTrue(ctx.followup.send.called)
        args, kwargs = ctx.followup.send.call_args
        embed = kwargs.get('embed') or args[0]

        # Team 1 field is usually the second field (index 6 after Map, Players, Mod, Gametype, Time, Address)
        # Wait, let's just check the whole embed
        found = False
        for field in embed.fields:
            if "Axis (Team 1)" in field.name:
                self.assertIn("Player ''' @everyone", field.value)
                self.assertNotIn("```", field.value.strip("`"))
                found = True
        self.assertTrue(found)

    def test_sanitize_for_codeblock(self):
        self.assertEqual(sanitize_for_codeblock("normal"), "normal")
        self.assertEqual(sanitize_for_codeblock("```breakout"), "'''breakout")

if __name__ == '__main__':
    unittest.main()
