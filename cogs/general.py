import discord
from discord.ext import commands, tasks
import logging
from core.database import Database
from core.version import GIT_COMMIT, __version__
from utils import embeds

logger = logging.getLogger("bf1942_bot")


class AboutLinks(discord.ui.View):
    """Link buttons only: Discord opens them directly, so no callbacks or timeout."""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="captheflag.com", url=embeds.SITE_URL, emoji="🌐"))
        self.add_item(discord.ui.Button(label="BF1942 Servers", url=f"{embeds.GAME_URL}/servers", emoji="🖥️"))
        self.add_item(discord.ui.Button(label="Round Stats", url=f"{embeds.GAME_URL}/stats/rounds", emoji="📊"))

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_status_text = None
        self.update_status.start()

    def cog_unload(self):
        self.update_status.cancel()

    @property
    def db(self) -> Database:
        return self.bot.db

    @commands.slash_command(name="about", description="About this bot: version, status and links to captheflag.com.")
    async def about(self, ctx: discord.ApplicationContext):
        version = f"v{__version__}" + (f" (`{GIT_COMMIT}`)" if GIT_COMMIT else "")
        embed = discord.Embed(
            title="BF1942 Map Alert Bot",
            url=embeds.SITE_URL,
            description=(
                "Live Battlefield 1942 server info, map & round alerts, player watchlists, "
                f"leaderboards and profiles, powered by {embeds.link('captheflag.com', embeds.SITE_URL)} stats."
            ),
            color=discord.Color.dark_green(),
        )
        embed.add_field(name="Version", value=version, inline=True)
        embed.add_field(name="Online Since", value=embeds.discord_time(self.bot.started_at, "R"), inline=True)
        embed.add_field(name="Latency", value=f"{self.bot.latency * 1000:.0f} ms", inline=True)
        embed.add_field(name="Discord Servers", value=f"{len(self.bot.guilds):,}", inline=True)
        if self.last_status_text:
            embed.add_field(name="Tracking", value=self.last_status_text, inline=True)
        embed.add_field(
            name="Getting Started",
            value=("`/servers` browse live servers · `/subscribe` map alerts · "
                   "`/subscribe_rounds` round results · `/watch` player alerts · `/profile` player stats"),
            inline=False,
        )
        if self.bot.user and self.bot.user.display_avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text=embeds.FOOTER_TEXT)
        await ctx.respond(embed=embed, view=AboutLinks(), ephemeral=True)

    @tasks.loop(seconds=60)
    async def update_status(self):
        """Updates the bot's presence with live stats."""
        try:
            # We can use get_all_active_servers just to get the count
            # Or add a specific lightweight count query to DB
            servers = await self.db.get_all_active_servers(limit=500)
            server_count = len(servers)
            player_count = sum(s['current_player_count'] for s in servers)

            # ActivityType.watching already renders as "Watching <name>"
            status_text = f"{server_count} Servers | {player_count} Players"
            if status_text == self.last_status_text:
                return
            self.last_status_text = status_text

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
