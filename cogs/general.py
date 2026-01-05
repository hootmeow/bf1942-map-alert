import discord
from discord.ext import commands, tasks
import logging
from core.database import Database

logger = logging.getLogger("bf1942_bot")

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_status.start()

    def cog_unload(self):
        self.update_status.cancel()

    @property
    def db(self) -> Database:
        return self.bot.db

    @tasks.loop(seconds=60)
    async def update_status(self):
        """Updates the bot's presence with live stats."""
        try:
            # We can use get_all_active_servers just to get the count
            # Or add a specific lightweight count query to DB
            servers = await self.db.get_all_active_servers(limit=500)
            server_count = len(servers)
            player_count = sum(s['current_player_count'] for s in servers)

            status_text = f"Watching {server_count} Servers | {player_count} Players"
            
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching, 
                    name=status_text
                )
            )
        except Exception as e:
            logger.error(f"Error updating status: {e}")

    @update_status.before_loop
    async def before_update_status(self):
        await self.bot.wait_until_ready()

def setup(bot):
    bot.add_cog(General(bot))
