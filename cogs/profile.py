import discord
from discord.ext import commands
from discord.commands import Option
import logging
from core.database import Database

logger = logging.getLogger("bf1942_bot")

async def search_players(ctx: discord.AutocompleteContext):
    db: Database = ctx.bot.db
    return await db.get_player_suggestions(ctx.value)


class ProfileCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def db(self) -> Database:
        return self.bot.db

    @commands.slash_command(name="profile", description="View a player's lifetime stats and history.")
    async def profile(
        self,
        ctx: discord.ApplicationContext,
        player_name: Option(str, "Start typing a player name", autocomplete=search_players)
    ):
        await ctx.defer(ephemeral=False)
        try:
            stats = await self.db.get_player_lifetime_stats(player_name)
            if not stats:
                await ctx.followup.send(f"No data found for **{player_name}**.")
                return

            total_kills = stats['total_kills'] or 0
            total_deaths = stats['total_deaths'] or 0
            kdr = f"{total_kills / total_deaths:.2f}" if total_deaths > 0 else "N/A"
            rounds_played = stats['rounds_played'] or 0
            wins = stats['wins'] or 0
            win_rate = f"{wins / rounds_played * 100:.1f}%" if rounds_played > 0 else "N/A"

            embed = discord.Embed(
                title=f"Player Profile: {player_name}",
                color=discord.Color.blue()
            )

            embed.add_field(name="Total Score", value=f"{stats['total_score'] or 0:,}", inline=True)
            embed.add_field(name="K/D Ratio", value=f"{total_kills:,}/{total_deaths:,} ({kdr})", inline=True)
            embed.add_field(name="Rounds", value=f"{rounds_played:,}", inline=True)
            embed.add_field(name="Win Rate", value=f"{wins:,}W ({win_rate})", inline=True)

            # Estimated playtime from ClickHouse
            playtime_secs = self.db.get_player_playtime_seconds(player_name)
            if playtime_secs > 0:
                hours = playtime_secs // 3600
                embed.add_field(name="Est. Playtime", value=f"{hours:,}h", inline=True)

            # Personal bests
            bests = await self.db.get_player_personal_bests(player_name)
            if bests and bests['best_score']:
                embed.add_field(
                    name="Personal Bests",
                    value=f"Score: {bests['best_score']:,} | Kills: {bests['best_kills']:,}",
                    inline=False
                )

            # Top maps
            top_maps = await self.db.get_player_top_maps(player_name)
            if top_maps:
                map_lines = [f"{m['map_name']} ({m['play_count']} rounds)" for m in top_maps]
                embed.add_field(name="Top Maps", value="\n".join(map_lines), inline=True)

            # Top servers
            top_servers = await self.db.get_player_top_servers(player_name)
            if top_servers:
                srv_lines = [f"{s['server_name']} ({s['play_count']})" for s in top_servers]
                embed.add_field(name="Top Servers", value="\n".join(srv_lines), inline=True)

            # Recent rounds
            recent = await self.db.get_player_recent_rounds(player_name)
            if recent:
                recent_lines = []
                for r in recent:
                    date_str = r['started_at'].strftime("%m/%d") if r['started_at'] else "?"
                    recent_lines.append(
                        f"{date_str} — {r['map_name']} on {r['server_name']} "
                        f"({r['score']}pts, {r['kills']}K/{r['deaths']}D)"
                    )
                embed.add_field(name="Recent Rounds", value="\n".join(recent_lines), inline=False)

            await ctx.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in /profile: {e}")
            await ctx.followup.send("Something went wrong.", ephemeral=True)


def setup(bot):
    bot.add_cog(ProfileCommands(bot))
