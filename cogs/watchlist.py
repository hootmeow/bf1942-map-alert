import discord
from discord.ext import commands, tasks
from discord.commands import Option
import logging
import datetime
import pytz
from core.database import Database
from utils.validation import validate_input_length, ValidationError, sanitize_text

logger = logging.getLogger("bf1942_bot")

class Watchlist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Sets to track state
        self.previously_online = set() # {player_name, ...}
        self.cooldowns = {} # {(user_id, player_name): expiration_timestamp}
        self.check_watchlist.start()

    def cog_unload(self):
        self.check_watchlist.cancel()

    @property
    def db(self) -> Database:
        return self.bot.db

    @commands.slash_command(name="watch", description="Get a DM when a specific player joins a server.")
    async def watch(
        self,
        ctx: discord.ApplicationContext,
        player_name: Option(str, "The exact case-sensitive player name")
    ):
        await ctx.defer(ephemeral=True)
        try:
            validate_input_length(player_name, 64, "Player Name")

            # Ensure table exists (idempotent)
            await self.db.init_watchlist_table()
            
            await self.db.add_watchlist(ctx.author.id, player_name)
            await ctx.followup.send(f"✅ You are now watching **{player_name}**. I'll DM you when they join a server.")
        except ValidationError as e:
            await ctx.followup.send(str(e), ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /watch: {e}")
            await ctx.followup.send("Something went wrong.", ephemeral=True)

    @commands.slash_command(name="unwatch", description="Stop watching a player.")
    async def unwatch(
        self,
        ctx: discord.ApplicationContext,
        player_name: Option(str, " The player name to remove")
    ):
        await ctx.defer(ephemeral=True)
        try:
            validate_input_length(player_name, 64, "Player Name")

            count = await self.db.remove_watchlist(ctx.author.id, player_name)
            if count > 0:
                await ctx.followup.send(f"✅ Stopped watching **{player_name}**.")
            else:
                await ctx.followup.send(f"You weren't watching **{player_name}**.", ephemeral=True)
        except ValidationError as e:
            await ctx.followup.send(str(e), ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /unwatch: {e}")
            await ctx.followup.send("Something went wrong.", ephemeral=True)

    @commands.slash_command(name="watchlist", description="See who you are watching.")
    async def watchlist(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        try:
            rows = await self.db.get_user_watchlist(ctx.author.id)
            if not rows:
                await ctx.followup.send("You are not watching any players.")
                return
            
            names = [f"• {r['player_name']}" for r in rows]
            await ctx.followup.send(f"**Your Watchlist:**\n" + "\n".join(names))
        except Exception as e:
            logger.error(f"Error in /watchlist: {e}")
            await ctx.followup.send("Something went wrong.", ephemeral=True)

    @tasks.loop(seconds=45)
    async def check_watchlist(self):
        if not self.bot.db.pool:
            return

        try:
            # 1. Get all currently online players
            rows = await self.db.get_all_online_players()
            current_online = {r['player_name']: r['current_server_name'] for r in rows}
            current_online_names = set(current_online.keys())

            # 2. Identify Just Joined (Present now, but NOT in previous cycle)
            # If previous state is empty (bot restart), assume nobody just joined to avoid spam
            just_joined_names = []
            if self.previously_online:
                just_joined_names = [name for name in current_online_names if name not in self.previously_online]
            
            # Update state for next loop
            self.previously_online = current_online_names

            if not just_joined_names:
                return

            # 3. Find subscribers for these specific players
            subs = await self.db.get_watchlist_subscribers(just_joined_names)
            
            now_utc = datetime.datetime.now(pytz.utc)
            current_utc_hour = now_utc.hour
            current_utc_weekday = now_utc.weekday()
            
            for sub in subs:
                user_id = sub['user_id']

                # Security Check: Respect global user blacklist
                if user_id in self.bot.blocked_user_ids:
                    continue

                player_name = sub['player_name']
                server_name = current_online.get(player_name, "Unknown Server")

                # Sanitize for Discord output
                s_player_name = sanitize_text(player_name)
                s_server_name = sanitize_text(server_name)

                # --- Cooldown Check ---
                # Key: (User, Player)
                # If they are in cooldown, SKIP
                cooldown_key = (user_id, player_name)
                if cooldown_key in self.cooldowns:
                    if now_utc < self.cooldowns[cooldown_key]:
                        continue # Still cooling down
                
                # --- DND Check ---
                if sub['start_hour_utc'] is not None:
                    is_dnd_day = current_utc_weekday in sub['weekdays_utc']
                    start_h = sub['start_hour_utc']
                    end_h = sub['end_hour_utc']
                    is_dnd_hour = False
                    if start_h <= end_h:
                        is_dnd_hour = start_h <= current_utc_hour < end_h
                    else:
                        is_dnd_hour = current_utc_hour >= start_h or current_utc_hour < end_h
                    
                    if is_dnd_day and is_dnd_hour:
                        continue # Skip for DND

                # --- Send Alert ---
                try:
                    user = await self.bot.fetch_user(user_id)
                    embed = discord.Embed(
                        title="🕵️ Watchlist Alert",
                        description=f"**{s_player_name}** just joined **{s_server_name}**!",
                        color=discord.Color.magenta()
                    )
                    clean_content = f"Watchlist: {s_player_name} joined {s_server_name}"
                    await user.send(
                        content=clean_content,
                        embed=embed,
                        allowed_mentions=discord.AllowedMentions.none()
                    )
                    
                    # Set Cooldown (e.g., 15 minutes)
                    # We don't want to ping again if they rejoin within 15 mins
                    self.cooldowns[cooldown_key] = now_utc + datetime.timedelta(minutes=15)
                    
                except discord.Forbidden:
                    logger.warning(f"Cannot DM user {user_id}")
                except Exception as e:
                    logger.error(f"Error sending watchlist alert: {e}")

            # Cleanup expired cooldowns (optional, but good for memory)
            keys_to_delete = [k for k, v in self.cooldowns.items() if now_utc > v]
            for k in keys_to_delete:
                del self.cooldowns[k]

        except Exception as e:
            logger.error(f"Error in watchlist task: {e}")

    @check_watchlist.before_loop
    async def before_check_watchlist(self):
        await self.bot.wait_until_ready()

def setup(bot):
    bot.add_cog(Watchlist(bot))
