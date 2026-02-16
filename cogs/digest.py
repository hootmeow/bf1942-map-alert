import discord
from discord.ext import commands, tasks
from discord.commands import Option
import logging
import datetime
import pytz
from core.database import Database
from utils.dnd import is_in_dnd

logger = logging.getLogger("bf1942_bot")


class DigestCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_digest.start()

    def cog_unload(self):
        self.daily_digest.cancel()

    @property
    def db(self) -> Database:
        return self.bot.db

    @commands.slash_command(name="digest_subscribe", description="Get a daily summary of BF1942 activity.")
    async def digest_subscribe(
        self,
        ctx: discord.ApplicationContext,
        channel: Option(discord.TextChannel, "Optional: channel for digest (DMs if empty)", required=False, default=None)
    ):
        channel_id = channel.id if channel else None

        if channel:
            perms = channel.permissions_for(ctx.guild.me)
            if not perms.send_messages or not perms.embed_links:
                await ctx.respond(
                    f"I don't have permission to send messages in {channel.mention}.",
                    ephemeral=True
                )
                return

        try:
            await self.db.upsert_digest_subscription(ctx.author.id, ctx.guild.id, channel_id)
            destination = f"channel **{channel.name}**" if channel else "your **DMs**"
            await ctx.respond(
                f"You are now subscribed to the **daily digest**.\n"
                f"It will be sent to {destination} around midnight UTC.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in /digest_subscribe: {e}")
            await ctx.respond("Something went wrong.", ephemeral=True)

    @commands.slash_command(name="digest_unsubscribe", description="Stop receiving daily digests.")
    async def digest_unsubscribe(self, ctx: discord.ApplicationContext):
        try:
            count = await self.db.delete_digest_subscription(ctx.author.id)
            if count > 0:
                await ctx.respond("Unsubscribed from the daily digest.", ephemeral=True)
            else:
                await ctx.respond("You weren't subscribed to the daily digest.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /digest_unsubscribe: {e}")
            await ctx.respond("Something went wrong.", ephemeral=True)

    @tasks.loop(minutes=5)
    async def daily_digest(self):
        if not self.bot.db.pool:
            return

        now_utc = datetime.datetime.now(pytz.utc)

        # Only fire near midnight UTC (between 00:00 and 00:04)
        if now_utc.hour != 0 or now_utc.minute >= 5:
            return

        try:
            # Double-fire guard
            today_key = now_utc.strftime("%Y-%m-%d")
            last_digest_date = await self.db.get_bot_state("last_digest_date")
            if last_digest_date == today_key:
                return

            subs = await self.db.get_all_digest_subscriptions()
            if not subs:
                await self.db.set_bot_state("last_digest_date", today_key)
                return

            # Gather stats
            digest_stats = await self.db.get_digest_stats()
            active_servers = await self.db.get_most_active_servers_24h()
            top_players = await self.db.get_top_players_24h()

            embed = discord.Embed(
                title="BF1942 Daily Digest",
                description=f"Activity summary for the last 24 hours.",
                color=discord.Color.dark_blue()
            )

            rounds_24h = digest_stats['rounds_24h'] if digest_stats else 0
            players_24h = digest_stats['unique_players_24h'] if digest_stats else 0
            embed.add_field(name="Rounds Played", value=str(rounds_24h), inline=True)
            embed.add_field(name="Unique Players", value=str(players_24h), inline=True)

            if active_servers:
                srv_lines = [f"**{s['server_name']}** — {s['round_count']} rounds" for s in active_servers]
                embed.add_field(name="Most Active Servers", value="\n".join(srv_lines), inline=False)

            if top_players:
                player_lines = [
                    f"**{p['player_name']}** — {p['total_score']:,} pts ({p['total_kills']:,} kills)"
                    for p in top_players
                ]
                embed.add_field(name="Top Players", value="\n".join(player_lines), inline=False)

            embed.set_footer(text=f"Digest for {today_key}")

            clean_content = f"BF1942 Daily Digest — {rounds_24h} rounds, {players_24h} players"

            for sub in subs:
                if is_in_dnd(sub, now_utc):
                    continue

                channel_id = sub.get("channel_id")
                user_id = sub["user_id"]

                if channel_id:
                    try:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            perms = channel.permissions_for(channel.guild.me)
                            if perms.send_messages and perms.embed_links:
                                await channel.send(content=clean_content, embed=embed)
                    except Exception as e:
                        logger.error(f"Error sending digest to channel {channel_id}: {e}")
                else:
                    try:
                        user = await self.bot.fetch_user(user_id)
                        await user.send(content=clean_content, embed=embed)
                    except discord.Forbidden:
                        logger.warning(f"Cannot DM user {user_id}")
                    except Exception as e:
                        logger.error(f"Error sending digest DM: {e}")

            await self.db.set_bot_state("last_digest_date", today_key)
            logger.info(f"Daily digest sent to {len(subs)} subscribers.")

        except Exception as e:
            logger.error(f"Error in daily digest task: {e}")

    @daily_digest.before_loop
    async def before_daily_digest(self):
        await self.bot.wait_until_ready()


def setup(bot):
    bot.add_cog(DigestCommands(bot))
