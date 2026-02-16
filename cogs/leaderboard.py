import discord
from discord.ext import commands
from discord.commands import Option
import logging
from core.database import Database

logger = logging.getLogger("bf1942_bot")

async def search_servers(ctx: discord.AutocompleteContext):
    db: Database = ctx.bot.db
    return await db.get_server_suggestions(ctx.value)


class LeaderboardCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def db(self) -> Database:
        return self.bot.db

    @commands.slash_command(name="leaderboard", description="See the top players by V5 score.")
    async def leaderboard(
        self,
        ctx: discord.ApplicationContext,
        period: Option(str, "Time period", choices=["all-time", "weekly", "monthly"], default="all-time"),
        server: Option(str, "Filter by server (optional)", autocomplete=search_servers, required=False, default=None)
    ):
        await ctx.defer(ephemeral=False)
        try:
            rows = await self.db.get_leaderboard(period, server_name=server)
            if not rows:
                await ctx.followup.send("No leaderboard data found for that selection.")
                return

            title = f"Leaderboard — {period.replace('-', ' ').title()}"
            if server:
                title += f" — {server}"

            embed = discord.Embed(title=title, color=discord.Color.gold())

            lines = []
            for i, row in enumerate(rows, 1):
                kdr = f"{row['total_kills']}/{row['total_deaths']}"
                lines.append(
                    f"**{i}. {row['player_name']}** — "
                    f"V5: {row['v5_score']:,} | "
                    f"Score: {row['total_score']:,} | "
                    f"K/D: {kdr} | "
                    f"Rounds: {row['rounds_played']}"
                )

            embed.description = "\n".join(lines)
            embed.set_footer(text="V5 = (score*20) - (kills*10) + (rounds*100). Excludes coop.")
            await ctx.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in /leaderboard: {e}")
            await ctx.followup.send("Something went wrong.", ephemeral=True)


def setup(bot):
    bot.add_cog(LeaderboardCommands(bot))
