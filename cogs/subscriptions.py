import discord
from discord.ext import commands, tasks
from discord.commands import Option, SlashCommandGroup
import logging
import pytz
import datetime
import asyncio
from core.database import Database
from utils.dnd import is_in_dnd

logger = logging.getLogger("bf1942_bot")

SERVER_SUB_MAP_NAME = "*all*"

# Helper Constants for DND
DAY_MAP = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6
}
DAY_NAMES = [ "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun" ]

async def search_servers(ctx: discord.AutocompleteContext):
    db: Database = ctx.bot.db
    return await db.get_server_suggestions(ctx.value)

async def search_maps(ctx: discord.AutocompleteContext):
    db: Database = ctx.bot.db
    return await db.get_map_suggestions(ctx.value)

async def search_timezones(ctx: discord.AutocompleteContext):
    """Provides suggestions for timezones."""
    value = ctx.value.lower().replace(" ", "_")
    common_zones = [
        "UTC", "US/Eastern", "US/Central", "US/Mountain", "US/Pacific",
        "Europe/London", "Europe/Berlin", "Europe/Moscow",
        "Australia/Sydney"
    ]
    if len(value) < 2:
        return [tz for tz in common_zones if value in tz.lower()][:25]

    all_matches = [tz for tz in pytz.all_timezones if value in tz.lower()][:25]
    return all_matches

class SubscriptionCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_known_maps = {}
        self.check_map_changes.start()
        self.check_round_results.start()

    def cog_unload(self):
        self.check_map_changes.cancel()
        self.check_round_results.cancel()

    @property
    def db(self) -> Database:
        return self.bot.db

    dnd = SlashCommandGroup("dnd", "Manage your Do Not Disturb (DND) schedule.")

    @commands.slash_command(name="subscribe", description="Get an alert when a map starts on a server.")
    async def subscribe(
        self,
        ctx: discord.ApplicationContext,
        server: Option(str, "Start typing the server name", autocomplete=search_servers),
        map_name: Option(str, "Start typing the map name", autocomplete=search_maps),
        players_over: Option(int, "Optional: Only alert if player count is over this number", required=False, default=0),
        channel: Option(discord.TextChannel, "Optional: The channel to post the alert in (posts to DMs if empty)", required=False, default=None)
    ):
        channel_id = channel.id if channel else None

        if channel:
            perms = channel.permissions_for(ctx.guild.me)
            if not perms.send_messages or not perms.embed_links:
                await ctx.respond(
                    f"I don't have permission to **Send Messages** and **Embed Links** in {channel.mention}."
                    " Please update my permissions and try again.",
                    ephemeral=True
                )
                return

        try:
            await self.db.upsert_subscription(
                ctx.author.id, server, map_name.lower(), players_over, ctx.guild.id, channel_id
            )
            destination = f"channel **{channel.name}**" if channel else "your **DMs**"
            await ctx.respond(
                f"You are now subscribed to **{map_name}** on **{server}**.\n"
                f"Alerts will be sent to {destination}.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in /subscribe: {e}")
            await ctx.respond("Something went wrong, I couldn't save your subscription.", ephemeral=True)

    @commands.slash_command(name="subscribe_server", description="Get an alert for *every* map change on a server.")
    async def subscribe_server(
        self,
        ctx: discord.ApplicationContext,
        server: Option(str, "Start typing the server name", autocomplete=search_servers),
        players_over: Option(int, "Optional: Only alert if player count is over this number", required=False, default=0),
        channel: Option(discord.TextChannel, "Optional: The channel to post the alert in (posts to DMs if empty)", required=False, default=None)
    ):
        channel_id = channel.id if channel else None

        if channel:
            perms = channel.permissions_for(ctx.guild.me)
            if not perms.send_messages or not perms.embed_links:
                await ctx.respond(
                    f"I don't have permission to **Send Messages** and **Embed Links** in {channel.mention}.",
                    ephemeral=True
                )
                return

        try:
            await self.db.upsert_subscription(
                ctx.author.id, server, SERVER_SUB_MAP_NAME, players_over, ctx.guild.id, channel_id
            )
            destination = f"channel **{channel.name}**" if channel else "your **DMs**"
            await ctx.respond(
                f"You are now subscribed to **all map changes** on **{server}**.\n"
                f"Alerts will be sent to {destination}.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in /subscribe_server: {e}")
            await ctx.respond("Something went wrong, I couldn't save your subscription.", ephemeral=True)

    @commands.slash_command(name="subscribe_rounds", description="Get notified when a round ends on a server.")
    async def subscribe_rounds(
        self,
        ctx: discord.ApplicationContext,
        server: Option(str, "Start typing the server name", autocomplete=search_servers),
        channel: Option(discord.TextChannel, "Optional: The channel to post the alert in (posts to DMs if empty)", required=False, default=None)
    ):
        channel_id = channel.id if channel else None

        if channel:
            perms = channel.permissions_for(ctx.guild.me)
            if not perms.send_messages or not perms.embed_links:
                await ctx.respond(
                    f"I don't have permission to **Send Messages** and **Embed Links** in {channel.mention}.",
                    ephemeral=True
                )
                return

        try:
            await self.db.upsert_round_result_subscription(
                ctx.author.id, server, ctx.guild.id, channel_id
            )
            destination = f"channel **{channel.name}**" if channel else "your **DMs**"
            await ctx.respond(
                f"You are now subscribed to **round results** on **{server}**.\n"
                f"Alerts will be sent to {destination}.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in /subscribe_rounds: {e}")
            await ctx.respond("Something went wrong.", ephemeral=True)

    @commands.slash_command(name="unsubscribe_rounds", description="Stop round result notifications for a server.")
    async def unsubscribe_rounds(
        self,
        ctx: discord.ApplicationContext,
        server: Option(str, "Start typing the server name", autocomplete=search_servers)
    ):
        try:
            count = await self.db.delete_round_result_subscription(ctx.author.id, server)
            if count > 0:
                await ctx.respond(f"Unsubscribed from round results on **{server}**.", ephemeral=True)
            else:
                await ctx.respond(f"You weren't subscribed to round results on **{server}**.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /unsubscribe_rounds: {e}")
            await ctx.respond("Something went wrong.", ephemeral=True)

    @commands.slash_command(name="list", description="See all of your current map alerts.")
    async def list_subscriptions(self, ctx: discord.ApplicationContext):
        try:
            user_subs = await self.db.get_user_subscriptions(ctx.author.id)
            if not user_subs:
                await ctx.respond("You have no active subscriptions.", ephemeral=True)
                return

            embed = discord.Embed(title="Your Map Alert Subscriptions", color=discord.Color.blue())
            description = ""
            for sub in user_subs:
                player_condition = f" (Players > {sub['players_over']})" if sub.get('players_over', 0) > 0 else ""

                destination = "-> DMs"
                if sub['channel_id']:
                    channel = self.bot.get_channel(sub['channel_id'])
                    channel_name = f"#{channel.name}" if channel else f"Unknown Channel ({sub['channel_id']})"
                    destination = f"-> {channel_name}"

                map_name = sub['map_name']
                if map_name == SERVER_SUB_MAP_NAME:
                    map_display = "**Any Map**"
                else:
                    map_display = f"**{map_name}**"

                paused_status = " (PAUSED)" if sub['is_paused'] else ""

                description += f"**{sub['server_name']}** -> {map_display}{player_condition} {destination}{paused_status}\n"

            embed.description = description
            await ctx.respond(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /list: {e}")
            await ctx.respond("Something went wrong, I couldn't fetch your subscriptions.", ephemeral=True)

    @commands.slash_command(name="unsubscribe", description="Removes all of your active map alerts.")
    async def unsubscribe(self, ctx: discord.ApplicationContext):
        try:
            deleted_count = await self.db.delete_all_subscriptions(ctx.author.id)
            await ctx.respond(f"All {deleted_count} of your subscriptions have been removed.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /unsubscribe: {e}")
            await ctx.respond("Something went wrong, I couldn't remove your subscriptions.", ephemeral=True)

    @commands.slash_command(name="pause_alerts", description="Temporarily pause or unpause all of your map alerts.")
    async def pause_alerts(
        self,
        ctx: discord.ApplicationContext,
        status: Option(str, "Pause or unpause your alerts", choices=["pause", "unpause"])
    ):
        is_paused_bool = True if status == "pause" else False
        try:
            count = await self.db.set_subscription_paused(ctx.author.id, is_paused_bool)

            if count == 0:
                await ctx.respond("You have no subscriptions to update.", ephemeral=True)
                return

            action_text = "paused" if is_paused_bool else "unpaused"
            await ctx.respond(f"All {count} of your subscriptions have been **{action_text}**.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /pause_alerts: {e}")
            await ctx.respond("Something went wrong, I couldn't update your subscriptions.", ephemeral=True)

    # --- DND COMMANDS ---
    @dnd.command(name="set", description="Set a DND schedule to block alerts.")
    async def dnd_set(
        self,
        ctx: discord.ApplicationContext,
        start_hour: Option(int, "Start hour (0-23)", min_value=0, max_value=23),
        end_hour: Option(int, "End hour (0-23)", min_value=0, max_value=23),
        days: Option(str, "Days (e.g., 'weekdays', 'weekends', 'all', or 'mon,wed,fri')"),
        timezone: Option(str, "Your local timezone", autocomplete=search_timezones)
    ):
        await ctx.defer(ephemeral=True)

        # 1. Validate Timezone
        try:
            user_tz = pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            await ctx.followup.send(f"Unknown timezone: `{timezone}`. Please use the autocomplete to find a valid name.")
            return

        # 2. Parse Days
        days_lower = days.lower()
        day_list = []
        if days_lower == "all":
            day_list = [0, 1, 2, 3, 4, 5, 6]
        elif days_lower == "weekdays":
            day_list = [0, 1, 2, 3, 4]
        elif days_lower == "weekends":
            day_list = [5, 6]
        else:
            for day_str in days_lower.split(','):
                day_str = day_str.strip()
                if day_str in DAY_MAP:
                    day_list.append(DAY_MAP[day_str])
                else:
                    await ctx.followup.send(f"Invalid day: `{day_str}`.")
                    return

        if not day_list:
            await ctx.followup.send("You must provide at least one valid day.")
            return

        # 3. Convert times to UTC
        now_local = datetime.datetime.now(user_tz)
        start_local = now_local.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        end_local = now_local.replace(hour=end_hour, minute=0, second=0, microsecond=0)
        start_utc = start_local.astimezone(pytz.utc)
        end_utc = end_local.astimezone(pytz.utc)

        utc_days = set()
        for day_offset in range(8):
            test_date = start_local + datetime.timedelta(days=day_offset)
            if test_date.weekday() in day_list:
                utc_days.add(test_date.astimezone(pytz.utc).weekday())

        try:
            await self.db.upsert_dnd_rule(ctx.author.id, start_utc.hour, end_utc.hour, list(utc_days), timezone)
            day_names_str = ", ".join([DAY_NAMES[i] for i in day_list])
            await ctx.followup.send(f"DND schedule set!\n"
                                    f"Alerts blocked from **{start_hour:02d}:00** to **{end_hour:02d}:00** ({timezone})\n"
                                    f"On these days: **{day_names_str}**")
        except Exception as e:
            logger.error(f"Error in /dnd set: {e}")
            await ctx.followup.send("Something went wrong, I couldn't save your DND schedule.")

    @dnd.command(name="view", description="Show your current DND schedule.")
    async def dnd_view(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        try:
            rule = await self.db.get_dnd_rule(ctx.author.id)
            if not rule:
                await ctx.followup.send("You do not have a DND schedule set.")
                return

            user_tz = pytz.timezone(rule['timezone'])
            now_utc = datetime.datetime.now(pytz.utc)
            start_utc = now_utc.replace(hour=rule['start_hour_utc'], minute=0)
            end_utc = now_utc.replace(hour=rule['end_hour_utc'], minute=0)
            start_local = start_utc.astimezone(user_tz)
            end_local = end_utc.astimezone(user_tz)

            local_days = set()
            for i in range(7):
                if i in rule['weekdays_utc']:
                    local_days.add(DAY_NAMES[i])
            day_names_str = ", ".join(sorted(list(local_days), key=lambda d: DAY_NAMES.index(d)))

            await ctx.followup.send(f"**Your DND Schedule:**\n"
                                    f"Alerts blocked from **{start_local.hour:02d}:00** to **{end_local.hour:02d}:00** ({rule['timezone']})\n"
                                    f"Days (UTC relative): **{day_names_str}**")
        except Exception as e:
            logger.error(f"Error in /dnd view: {e}")
            await ctx.followup.send("Something went wrong.")

    @dnd.command(name="clear", description="Clear your DND schedule.")
    async def dnd_clear(self, ctx: discord.ApplicationContext):
        try:
            count = await self.db.delete_dnd_rule(ctx.author.id)
            if count == 0:
                await ctx.respond("You had no DND schedule to clear.", ephemeral=True)
            else:
                await ctx.respond("Your DND schedule has been cleared.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /dnd clear: {e}")
            await ctx.respond("Something went wrong.", ephemeral=True)

    # --- Shared alert sender ---
    async def _send_alert(self, embed, clean_content, channel_id, user_id):
        """Send an alert to a channel or DM."""
        if channel_id:
            try:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    perms = channel.permissions_for(channel.guild.me)
                    if perms.send_messages and perms.embed_links:
                        await channel.send(content=clean_content, embed=embed)
                    else:
                        logger.warning(f"Missing permissions for channel {channel_id}")
                else:
                    logger.warning(f"Could not find channel {channel_id}")
            except Exception as e:
                logger.error(f"Error sending channel alert: {e}")
        else:
            try:
                user = await self.bot.fetch_user(user_id)
                await user.send(content=clean_content, embed=embed)
            except discord.Forbidden:
                logger.warning(f"Cannot DM user {user_id}")
            except Exception as e:
                logger.error(f"Error sending DM alert: {e}")

    # --- BACKGROUND TASK: MAP CHANGES ---
    @tasks.loop(seconds=45)
    async def check_map_changes(self):
        if not self.bot.db.pool:
            return

        now_utc = datetime.datetime.now(pytz.utc)

        try:
            online_servers_rows = await self.db.get_all_active_servers(limit=500)
            online_servers = {s['current_server_name']: s for s in online_servers_rows}

            if not self.last_known_maps:
                for server_name, server_data in online_servers.items():
                    self.last_known_maps[server_name] = server_data['current_map']
                logger.info("Initial map state populated.")
                # Save to DB
                await self.db.set_bot_state("last_known_maps", self.last_known_maps)
                return

            for server_name, server_data in online_servers.items():
                current_map = server_data['current_map']
                last_map = self.last_known_maps.get(server_name)

                if current_map and last_map != current_map:
                    logger.info(f"MAP CHANGE DETECTED on {server_name}: {last_map} -> {current_map}")

                    subs_to_alert = await self.db.get_matching_subscriptions(
                        server_name, current_map.lower(), SERVER_SUB_MAP_NAME
                    )

                    player_count = server_data['current_player_count']

                    # Enriched alert: get previous round result
                    prev_round = await self.db.get_last_round_for_server(server_name)

                    for sub in subs_to_alert:
                        if player_count <= sub.get("players_over", 0):
                            continue

                        if is_in_dnd(sub, now_utc):
                            logger.info(f"Skipping alert for user {sub['user_id']} due to DND.")
                            continue

                        if sub['map_name'] == SERVER_SUB_MAP_NAME:
                            title = "BF1942 Server Alert!"
                            description = f"**{server_name}** has just changed maps to **{current_map}**!"
                            clean_content = f"{server_name} changed map to {current_map}"
                        else:
                            title = "BF1942 Map Alert!"
                            description = f"The map **{current_map}** has just started on **{server_name}**!"
                            clean_content = f"Map {current_map} started on {server_name}"

                        embed = discord.Embed(
                            title=title, description=description, color=discord.Color.gold()
                        )
                        embed.add_field(name="Players", value=f"{player_count}/{server_data['current_max_players']}")

                        # Enriched: previous round info
                        if prev_round:
                            winner = "Axis" if prev_round['winning_team'] == 1 else "Allies" if prev_round['winning_team'] == 2 else "Draw"
                            duration = prev_round['duration_seconds'] or 0
                            mins = duration // 60
                            embed.add_field(
                                name="Previous Round",
                                value=f"{prev_round['map_name']} — Winner: **{winner}** ({mins}m)",
                                inline=False
                            )

                        await self._send_alert(embed, clean_content, sub.get("channel_id"), sub["user_id"])

            # Update state
            for server_name, server_data in online_servers.items():
                self.last_known_maps[server_name] = server_data['current_map']

            # Persist to DB
            await self.db.set_bot_state("last_known_maps", self.last_known_maps)

        except Exception as e:
            logger.error(f"Error in background task: {e}")

    @check_map_changes.before_loop
    async def before_check_map_changes(self):
        await self.bot.wait_until_ready()
        # Load persisted state
        try:
            saved = await self.db.get_bot_state("last_known_maps")
            if saved and isinstance(saved, dict):
                self.last_known_maps = saved
                logger.info(f"Loaded last_known_maps from DB ({len(saved)} servers).")
        except Exception as e:
            logger.warning(f"Could not load last_known_maps: {e}")

    # --- BACKGROUND TASK: ROUND RESULTS ---
    @tasks.loop(seconds=60)
    async def check_round_results(self):
        if not self.bot.db.pool:
            return

        now_utc = datetime.datetime.now(pytz.utc)

        try:
            # Get watermark
            last_id = await self.db.get_bot_state("last_round_result_id")
            if last_id is None:
                last_id = await self.db.get_max_round_id()
                await self.db.set_bot_state("last_round_result_id", last_id)
                return

            new_rounds = await self.db.get_new_completed_rounds(last_id)
            if not new_rounds:
                return

            max_seen_id = last_id
            for rnd in new_rounds:
                round_id = rnd['id']
                if round_id > max_seen_id:
                    max_seen_id = round_id

                server_name = rnd['server_name']
                subs = await self.db.get_round_result_subscribers(server_name)
                if not subs:
                    continue

                # Build embed
                winner = "Axis" if rnd['winning_team'] == 1 else "Allies" if rnd['winning_team'] == 2 else "Draw"
                duration = rnd['duration_seconds'] or 0
                mins = duration // 60

                embed = discord.Embed(
                    title="Round Complete!",
                    description=f"**{server_name}**",
                    color=discord.Color.dark_gold()
                )
                embed.add_field(name="Map", value=rnd['map_name'], inline=True)
                embed.add_field(name="Winner", value=winner, inline=True)
                embed.add_field(name="Duration", value=f"{mins}m", inline=True)

                top_players = await self.db.get_round_top_players(round_id)
                if top_players:
                    top_lines = []
                    for i, p in enumerate(top_players, 1):
                        top_lines.append(f"{i}. **{p['player_name']}** — {p['score']} pts ({p['kills']}K/{p['deaths']}D)")
                    embed.add_field(name="Top Players", value="\n".join(top_lines), inline=False)

                clean_content = f"Round ended on {server_name}: {rnd['map_name']} — {winner}"

                for sub in subs:
                    if is_in_dnd(sub, now_utc):
                        continue
                    await self._send_alert(embed, clean_content, sub.get("channel_id"), sub["user_id"])

            await self.db.set_bot_state("last_round_result_id", max_seen_id)

        except Exception as e:
            logger.error(f"Error in round results task: {e}")

    @check_round_results.before_loop
    async def before_check_round_results(self):
        await self.bot.wait_until_ready()

def setup(bot):
    bot.add_cog(SubscriptionCommands(bot))
