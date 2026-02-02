import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from core.database import Database
from core.logger import logger

# Load configuration
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
POSTGRES_DSN = os.getenv("POSTGRES_DSN")

if not DISCORD_TOKEN or not POSTGRES_DSN:
    logger.critical("Error: DISCORD_TOKEN or POSTGRES_DSN not found in environment variables.")
    # We don't exit here to allow for testing imports, but run will fail.

class BF1942Bot(commands.Bot):
    def __init__(self):
        # Initialize intents
        intents = discord.Intents.default()
        intents.presences = True
        intents.members = True
        intents.messages = True 
        
        super().__init__(
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none()
        )
        
        # Initialize Database
        self.db = Database(POSTGRES_DSN)

        # Blacklist (Centralized for checks in cogs and background tasks)
        self.blocked_user_ids = [
            123456789012345678,  # User 1
        ]
        self.blocked_guild_ids = [
            999888777666555444, # Bad Server 1
            555555555555555555  # Bad Server 2
        ]
        
        # Load Cogs
        self.load_extensions()

    def load_extensions(self):
        extensions = [
            "cogs.servers",
            "cogs.subscriptions",
            "cogs.stats",
            "cogs.general",
            "cogs.watchlist"
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

        await self.sync_commands()
        logger.info("Slash commands synced.")

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
            # 1. Block Specific Users
            if ctx.author.id in ctx.bot.blocked_user_ids:
                await ctx.respond("⛔ You are blocked from using this bot.", ephemeral=True)
                return False

            # 2. Block Specific Servers (Guilds)
            # We must check 'ctx.guild' first because it is None in DMs
            if ctx.guild and ctx.guild.id in ctx.bot.blocked_guild_ids:
                await ctx.respond("⛔ This server is blocked from using this bot.", ephemeral=True)
                return False
            
            return True
        # ---------------------------------------------

        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.critical(f"Failed to run bot: {e}")
