import discord
from discord.ext import commands
import os
import sys
import traceback
from dotenv import load_dotenv
from core.database import Database
from core.logger import logger

# Load configuration
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
POSTGRES_DSN = os.getenv("POSTGRES_DSN")

if not DISCORD_TOKEN or not POSTGRES_DSN:
    logger.critical("Error: DISCORD_TOKEN or POSTGRES_DSN not found in environment variables.")

# Env-based blocklist seeds
ENV_BLOCKED_USERS = [
    int(x.strip()) for x in os.getenv("BLOCKED_USERS", "").split(",") if x.strip()
]
ENV_BLOCKED_GUILDS = [
    int(x.strip()) for x in os.getenv("BLOCKED_GUILDS", "").split(",") if x.strip()
]


class BF1942Bot(commands.Bot):
    def __init__(self):
        # Slash commands arrive as interactions and need no intents. Only the
        # guild/channel cache is used (channel lookups, permissions_for(guild.me)),
        # so skip members/presences/messages: they were unused, cost memory and
        # gateway traffic, and members/presences need verification at 100 guilds.
        intents = discord.Intents.none()
        intents.guilds = True

        super().__init__(
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
        )

        # Initialize Database
        self.db = Database(POSTGRES_DSN)

        # Blocklist — populated on_ready after DB connect
        self.blocked_user_ids: set = set()
        self.blocked_guild_ids: set = set()

        # Guards one-time startup work (on_ready re-fires on every reconnect)
        self._startup_done = False

        # Load Cogs
        self.load_extensions()

    def load_extensions(self):
        extensions = [
            "cogs.servers",
            "cogs.subscriptions",
            "cogs.stats",
            "cogs.general",
            "cogs.watchlist",
            "cogs.leaderboard",
            "cogs.profile",
            "cogs.digest",
        ]
        for ext in extensions:
            try:
                self.load_extension(ext)
                logger.info(f"Loaded extension: {ext}")
            except Exception as e:
                logger.error(f"Failed to load extension {ext}: {e}")

    async def start(self, token: str, *, reconnect: bool = True):
        """Connect the database before logging in.

        Background tasks start as soon as the gateway is ready, so the pool
        (and the state their before_loop hooks load) must exist by then.
        """
        await self.db.connect()

        try:
            await self.db.run_migrations()
        except Exception as e:
            logger.error(f"Migration error: {e}")

        # Connect ClickHouse (sync, no-op if not configured)
        self.db.connect_clickhouse()

        # Load blocklist from DB + env
        try:
            db_blocklist = await self.db.get_blocklist()
            self.blocked_user_ids = set(db_blocklist['users'] + ENV_BLOCKED_USERS)
            self.blocked_guild_ids = set(db_blocklist['guilds'] + ENV_BLOCKED_GUILDS)
            logger.info(f"Blocklist loaded: {len(self.blocked_user_ids)} users, {len(self.blocked_guild_ids)} guilds")
        except Exception as e:
            logger.error(f"Failed to load blocklist: {e}")
            self.blocked_user_ids = set(ENV_BLOCKED_USERS)
            self.blocked_guild_ids = set(ENV_BLOCKED_GUILDS)

        await super().start(token, reconnect=reconnect)

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")

        # on_ready fires again on every gateway reconnect — only sync
        # commands once per process.
        if self._startup_done:
            return
        self._startup_done = True

        await self.sync_commands()
        logger.info("Slash commands synced.")

    async def on_application_command_error(self, ctx, error):
        """Global error handler — logs and sends health webhook for genuine errors."""
        # Check failures (e.g. blocked users/guilds) already responded to the
        # user in the check itself — don't log or page ops for those.
        if isinstance(error, commands.CheckFailure):
            return

        logger.error(f"Command error in /{ctx.command}: {error}")

        # Best-effort: let the user know something broke (cogs handle their own
        # errors, so reaching here usually means an unexpected failure).
        try:
            if ctx.response.is_done():
                await ctx.followup.send("Something went wrong with that command.", ephemeral=True)
            else:
                await ctx.respond("Something went wrong with that command.", ephemeral=True)
        except Exception:
            pass

        try:
            from utils.health import send_health_alert
            tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            await send_health_alert(
                f"Command Error: /{ctx.command}",
                f"Guild: {ctx.guild}\nUser: {ctx.author}\n```\n{tb[:1500]}\n```"
            )
        except Exception:
            pass

    async def close(self):
        """Cleanup on bot shutdown."""
        logger.info("Bot is shutting down...")
        if self.db:
            await self.db.close()
        await super().close()


if __name__ == "__main__":
    try:
        if not DISCORD_TOKEN:
            raise ValueError("No token found")

        bot = BF1942Bot()

        # --- GLOBAL RESTRICTIONS (Users & Servers) ---
        @bot.check
        async def global_restrictions(ctx):
            if ctx.author.id in bot.blocked_user_ids:
                await ctx.respond("You are blocked from using this bot.", ephemeral=True)
                return False

            if ctx.guild and ctx.guild.id in bot.blocked_guild_ids:
                await ctx.respond("This server is blocked from using this bot.", ephemeral=True)
                return False

            return True
        # ---------------------------------------------

        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.critical(f"Failed to run bot: {e}")
        # Non-zero exit so systemd's Restart=on-failure retries (e.g. DB not up yet)
        sys.exit(1)
