import discord
from discord.ext import commands
from discord.commands import Option
import logging
from core.database import Database

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
                    map_desc += f"{i+1}. **{row['map_name']}** ({row['count']} subs)\n"
            embed.add_field(name="Top 10 Subscribed Maps", value=map_desc, inline=False)

            server_desc = ""
            if not server_rows:
                server_desc = "No server subscriptions found."
            else:
                for i, row in enumerate(server_rows):
                    server_desc += f"{i+1}. **{row['server_name']}** ({row['count']} subs)\n"
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
            found_player = await self.db.find_player(player_name)

            if found_player:
                embed = discord.Embed(
                    title=f"Player Found: {player_name}",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Server", value=found_player['current_server_name'], inline=False)
                embed.add_field(name="Score", value=str(found_player['score'] or 0), inline=True)
                embed.add_field(name="Kills", value=str(found_player['kills'] or 0), inline=True)
                embed.add_field(name="Deaths", value=str(found_player['deaths'] or 0), inline=True)
                await ctx.followup.send(embed=embed)
            else:
                await ctx.followup.send(f"Could not find a player named **{player_name}** on any active server.")
        except Exception as e:
            logger.error(f"Error in /find: {e}")
            await ctx.followup.send("Something went wrong, I couldn't perform the player search.", ephemeral=True)

    @commands.slash_command(name="stats", description="See global BF1942 statistics.")
    async def stats(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=False)
        try:
            global_stats = await self.db.get_global_stats()
            active_count = await self.db.get_active_player_count()
            popular_maps = await self.db.get_popular_maps_last_7_days()

            embed = discord.Embed(title="BF1942 Global Stats", color=discord.Color.dark_teal())

            total_rounds = global_stats['total_rounds'] if global_stats else 0
            unique_players = global_stats['unique_players'] if global_stats else 0
            embed.add_field(name="Total Rounds", value=f"{total_rounds:,}", inline=True)
            embed.add_field(name="Unique Players", value=f"{unique_players:,}", inline=True)
            embed.add_field(name="Currently Active", value=str(active_count), inline=True)

            if popular_maps:
                map_lines = [f"**{m['map_name']}** — {m['play_count']} rounds" for m in popular_maps]
                embed.add_field(name="Popular Maps (Last 7 Days)", value="\n".join(map_lines), inline=False)

            await ctx.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in /stats: {e}")
            await ctx.followup.send("Something went wrong.", ephemeral=True)

def setup(bot):
    bot.add_cog(StatCommands(bot))
