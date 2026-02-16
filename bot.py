import discord
from discord.ext import commands
import os
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
        intents = discord.Intents.default()
        intents.presences = True
        intents.members = True
        intents.messages = True

        super().__init__(
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
        )

        # Initialize Database
        self.db = Database(POSTGRES_DSN)

        # Blocklist — populated on_ready after DB connect
        self.blocked_user_ids: set = set()
        self.blocked_guild_ids: set = set()

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

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")

        # Connect to Database if not already connected
        if not self.db.pool:
            try:
                await self.db.connect()
            except Exception as e:
                logger.critical(f"Failed to connect to database on startup: {e}")
                return

        # Run startup migrations
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

        await self.sync_commands()
        logger.info("Slash commands synced.")

    async def on_application_command_error(self, ctx, error):
        """Global error handler — logs and sends health webhook."""
        logger.error(f"Command error in /{ctx.command}: {error}")
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
