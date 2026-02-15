import discord
from discord.ext import commands
from discord.commands import Option
import logging
from core.database import Database
from utils.validation import validate_input_length, ValidationError, sanitize_text

logger = logging.getLogger("bf1942_bot")

class StatCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def db(self) -> Database:
        return self.bot.db

    @commands.slash_command(name="alert_stats", description="See which maps and servers are most popular.")
    async def alert_stats(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=False)
        try:
            map_rows = await self.db.get_top_map_subs()
            server_rows = await self.db.get_top_server_subs()
            
            embed = discord.Embed(title="Bot Alert Statistics", color=discord.Color.dark_purple())
            
            map_desc = ""
            if not map_rows:
                map_desc = "No map subscriptions found."
            else:
                for i, row in enumerate(map_rows):
                    s_map = sanitize_text(row['map_name'])
                    map_desc += f"{i+1}. **{s_map}** ({row['count']} subs)\n"
            embed.add_field(name="Top 10 Subscribed Maps", value=map_desc, inline=False)
            
            server_desc = ""
            if not server_rows:
                server_desc = "No server subscriptions found."
            else:
                for i, row in enumerate(server_rows):
                    s_server = sanitize_text(row['server_name'])
                    server_desc += f"{i+1}. **{s_server}** ({row['count']} subs)\n"
            embed.add_field(name="Top 10 Subscribed Servers", value=server_desc, inline=False)
            
            await ctx.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in /alert_stats: {e}")
            await ctx.followup.send("Something went wrong, I couldn't fetch the stats.", ephemeral=True)

    @commands.slash_command(name="find", description="Find which server a specific player is on.")
    async def find(
        self,
        ctx: discord.ApplicationContext,
        player_name: Option(str, "Enter the full, case-sensitive player name")
    ):
        await ctx.defer(ephemeral=True)
        try:
            validate_input_length(player_name, 64, "Player Name")

            found_player = await self.db.find_player(player_name)
        
            if found_player:
                s_player = sanitize_text(player_name)
                s_server = sanitize_text(found_player['current_server_name'])
                embed = discord.Embed(
                    title=f"🕵️ Player Found: {s_player}",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Server", value=s_server, inline=False)
                embed.add_field(name="Score", value=str(found_player['score'] or 0), inline=True)
                embed.add_field(name="Kills", value=str(found_player['kills'] or 0), inline=True)
                embed.add_field(name="Deaths", value=str(found_player['deaths'] or 0), inline=True)
                await ctx.followup.send(embed=embed)
            else:
                await ctx.followup.send(f"Could not find a player named **{player_name}** on any active server.")
        except ValidationError as e:
            await ctx.followup.send(str(e), ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /find: {e}")
            await ctx.followup.send("Something went wrong, I couldn't perform the player search.", ephemeral=True)

def setup(bot):
    bot.add_cog(StatCommands(bot))
