import discord
from discord.ext import commands, tasks
from discord.commands import Option, permissions
import asyncpg
import os
from dotenv import load_dotenv
import re
import asyncio
import datetime
import pytz # --- NEW IMPORT ---

# --- CONFIGURATION ---
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
POSTGRES_DSN = os.getenv("POSTGRES_DSN")

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.presences = True
intents.members = True
intents.messages = True 
bot = commands.Bot(intents=intents)
bot.db_pool = None
last_known_maps = {}

# --- SPECIAL VALUE FOR SERVER-WIDE SUBS ---
SERVER_SUB_MAP_NAME = "*all*" 

# --- AUTOCOMPLETE FUNCTIONS ---
async def search_servers(ctx: discord.AutocompleteContext):
    """Provides server name suggestions for autocomplete."""
    if not bot.db_pool:
        return []
    
    query = """
    SELECT s.current_server_name
    FROM servers s
    WHERE s.current_server_name ILIKE $1
      AND s.current_state IN ('ACTIVE', 'EMPTY')
    ORDER BY s.current_player_count DESC
    LIMIT 25;
    """
    try:
        rows = await bot.db_pool.fetch(query, f"{ctx.value}%")
        return [row['current_server_name'] for row in rows]
    except Exception as e:
        print(f"Error in search_servers: {e}")
        return []

async def search_maps(ctx: discord.AutocompleteContext):
    """Provides map name suggestions using the rounds table."""
    if not bot.db_pool:
        return []
    
    query = "SELECT DISTINCT map_name FROM rounds WHERE map_name ILIKE $1 LIMIT 25"
    try:
        rows = await bot.db_pool.fetch(query, f"{ctx.value}%")
        return [row['map_name'] for row in rows]
    except Exception as e:
        print(f"Error in search_maps: {e}")
        return []

async def search_gametypes(ctx: discord.AutocompleteContext):
    """Provides suggestions for gametypes."""
    if not bot.db_pool:
        return []
    
    query = """
    SELECT DISTINCT current_gametype AS name
    FROM servers
    WHERE current_state <> 'OFFLINE' AND current_gametype IS NOT NULL AND current_gametype ILIKE $1
    ORDER BY name
    LIMIT 25;
    """
    try:
        rows = await bot.db_pool.fetch(query, f"{ctx.value}%")
        return [row['name'] for row in rows if row['name']]
    except Exception as e:
        print(f"Error in search_gametypes: {e}")
        return []

# --- NEW TIMEZONE AUTOCOMPLETE ---
async def search_timezones(ctx: discord.AutocompleteContext):
    """Provides suggestions for timezones."""
    value = ctx.value.lower().replace(" ", "_")
    
    # Give some common, easy-to-type suggestions
    common_zones = [
        "UTC", "US/Eastern", "US/Central", "US/Mountain", "US/Pacific",
        "Europe/London", "Europe/Berlin", "Europe/Moscow",
        "Australia/Sydney"
    ]
    
    # Search all pytz timezones
    if len(value) < 2:
        return [tz for tz in common_zones if value in tz.lower()][:25]

    all_matches = [tz for tz in pytz.all_timezones if value in tz.lower()][:25]
    return all_matches


# --- DISCORD COMMANDS (RE-ORDERED) ---

# --- GROUP 1: SERVER & PLAYER INFO ---

@bot.slash_command(name="servers", description="See a live list of active BF1942 servers.")
async def servers(ctx: discord.ApplicationContext):
    await ctx.defer(ephemeral=True)
    query = """
    SELECT current_server_name, current_map, current_player_count, current_max_players
    FROM servers
    WHERE current_state IN ('ACTIVE', 'EMPTY')
    ORDER BY current_player_count DESC
    LIMIT 25;
    """
    try:
        server_list = await bot.db_pool.fetch(query)
        if not server_list:
            await ctx.followup.send("Could not find any online servers right now.")
            return

        embed = discord.Embed(
            title="Live BF1942 Servers",
            description=f"Showing {len(server_list)} online servers, sorted by player count.",
            color=discord.Color.green()
        )
        for server in server_list:
            players = f"{server['current_player_count']}/{server['current_max_players']}"
            embed.add_field(
                name=f"**{server['current_server_name']}**",
                value=f"🗺️ Map: **{server['current_map']}** | 👥 Players: **{players}**",
                inline=False
            )
        await ctx.followup.send(embed=embed)
    except Exception as e:
        print(f"Error in /servers: {e}")
        await ctx.followup.send("Something went wrong, I couldn't fetch the server list.", ephemeral=True)


@bot.slash_command(name="playing", description="Find servers currently playing a specific map.")
async def playing(
    ctx: discord.ApplicationContext,
    map_name: Option(str, "Start typing the map name", autocomplete=search_maps)
):
    await ctx.defer(ephemeral=True)
    query = """
    SELECT current_server_name, current_player_count, current_max_players
    FROM servers
    WHERE current_state IN ('ACTIVE', 'EMPTY') AND current_map ILIKE $1
    ORDER BY current_player_count DESC;
    """
    try:
        server_list = await bot.db_pool.fetch(query, map_name)
        if not server_list:
            await ctx.followup.send(f"Sorry, no servers are currently playing **{map_name}**.")
            return

        embed = discord.Embed(title=f"Servers Playing: {map_name}", color=discord.Color.orange())
        description = ""
        for server in server_list:
            players = f"{server['current_player_count']}/{server['current_max_players']}"
            description += f"**{server['current_server_name']}** ({players} players)\n"
        embed.description = description
        await ctx.followup.send(embed=embed)
    except Exception as e:
        print(f"Error in /playing: {e}")
        await ctx.followup.send("Something went wrong, I couldn't find servers for that map.", ephemeral=True)


@bot.slash_command(name="findgametype", description="Find servers running a specific gametype.")
async def findgametype(
    ctx: discord.ApplicationContext,
    gametype: Option(str, "Start typing the gametype name", autocomplete=search_gametypes)
):
    await ctx.defer(ephemeral=True)

    query = """
    SELECT
        current_server_name, current_map, current_player_count, current_max_players
    FROM servers
    WHERE
        current_state IN ('ACTIVE', 'EMPTY')
        AND current_gametype ILIKE $1
    ORDER BY
        current_player_count DESC
    LIMIT 25;
    """
    
    try:
        server_list = await bot.db_pool.fetch(query, gametype)

        if not server_list:
            await ctx.followup.send(f"Sorry, no online servers were found running **{gametype}**.")
            return

        embed = discord.Embed(title=f"Servers Playing: {gametype}", color=discord.Color.orange())
        
        for server in server_list:
            players = f"{server['current_player_count']}/{server['current_max_players']}"
            map_name = server['current_map']

            embed.add_field(
                name=f"**{server['current_server_name']}**",
                value=f"🗺️ Map: **{map_name}** | 👥 Players: **{players}**",
                inline=False
            )
        await ctx.followup.send(embed=embed)
        
    except Exception as e:
        print(f"Error in /findgametype: {e}")
        await ctx.followup.send("Something went wrong, I couldn't perform the search.", ephemeral=True)


@bot.slash_command(name="find", description="Find which server a specific player is on.")
async def find(
    ctx: discord.ApplicationContext,
    player_name: Option(str, "Enter the full, case-sensitive player name")
):
    await ctx.defer(ephemeral=True)
    
    query = """
    SELECT s.current_server_name, lps.score, lps.kills, lps.deaths
    FROM live_player_snapshot lps
    JOIN servers s ON lps.server_ip = s.ip AND lps.server_port = s.port
    WHERE lps.player_name = $1 AND s.current_state = 'ACTIVE';
    """
    try:
        found_player = await bot.db_pool.fetchrow(query, player_name)
    
        if found_player:
            embed = discord.Embed(
                title=f"🕵️ Player Found: {player_name}",
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
        print(f"Error in /find: {e}")
        await ctx.followup.send("Something went wrong, I couldn't perform the player search.", ephemeral=True)


@bot.slash_command(name="seed", description="Find servers with a low player count to help get a game started.")
async def seed(ctx: discord.ApplicationContext):
    await ctx.defer(ephemeral=True)

    query = """
    SELECT current_server_name, current_map, current_player_count, current_max_players
    FROM servers
    WHERE current_state = 'ACTIVE' AND current_player_count > 0 AND current_player_count < 6
    ORDER BY current_player_count ASC
    LIMIT 25;
    """
    try:
        server_list = await bot.db_pool.fetch(query)

        if not server_list:
            await ctx.followup.send("No servers currently need seeding. Try the `/servers` command.")
            return

        embed = discord.Embed(
            title="🌱 Servers to Seed",
            description="These servers have a few players and are perfect to join and get a round started.",
            color=discord.Color.dark_green()
        )
        for server in server_list:
            players = f"{server['current_player_count']}/{server['current_max_players']}"
            map_name = server['current_map']
            embed.add_field(
                name=f"**{server['current_server_name']}**",
                value=f"🗺️ Map: **{map_name}** | 👥 Players: **{players}**",
                inline=False
            )
        await ctx.followup.send(embed=embed)
    except Exception as e:
        print(f"Error in /seed: {e}")
        await ctx.followup.send("Something went wrong, I couldn't find servers to seed.", ephemeral=True)


@bot.slash_command(name="serverinfo", description="Get detailed live info for a specific server.")
async def serverinfo(
    ctx: discord.ApplicationContext,
    server_name: Option(str, "Start typing the server name", autocomplete=search_servers)
):
    await ctx.defer(ephemeral=True)

    server_query = """
    SELECT
        s.ip, s.port, s.current_server_name, s.current_map, s.current_player_count, s.current_max_players,
        s.current_gametype, s.current_game_port,
        lss.round_time_remain, lss.tickets1, lss.tickets2, lss.unpure_mods
    FROM servers s
    LEFT JOIN live_server_snapshot lss ON s.ip = lss.server_ip AND s.port = lss.server_port
    WHERE s.current_server_name = $1 AND s.current_state IN ('ACTIVE', 'EMPTY');
    """
    
    player_query = """
    SELECT player_name, score, kills, deaths, ping, team
    FROM live_player_snapshot
    WHERE server_ip = $1 AND server_port = $2;
    """

    try:
        server = await bot.db_pool.fetchrow(server_query, server_name)
        if not server:
            await ctx.followup.send("Could not find that server. It might be offline.")
            return

        # --- Data Extraction ---
        hostname = server['current_server_name']
        map_name = server['current_map'] or 'N/A'
        num_players = server['current_player_count']
        max_players = server['current_max_players']
        game_mod = server['unpure_mods'] or server['current_gametype'] or 'N/A'
        gametype = server['current_gametype'] or 'N/A'
        ip_address = str(server['ip'])
        game_port = server['current_game_port'] or 'N/A'
        full_address = f"{ip_address}:{game_port}"
        time_remain_sec = int(server['round_time_remain'] or 0)
        minutes, seconds = divmod(time_remain_sec, 60)
        time_remaining_formatted = f"{minutes}:{seconds:02d}"

        # --- Player Fetching ---
        all_players = await bot.db_pool.fetch(player_query, server['ip'], server['port'])
        
        team1_players = sorted([p for p in all_players if p['team'] == 1], key=lambda x: x.get('score', 0), reverse=True)
        team2_players = sorted([p for p in all_players if p['team'] == 2], key=lambda x: x.get('score', 0), reverse=True)

        # --- Embed Creation ---
        embed = discord.Embed(title=f"**{hostname}**", color=discord.Color.dark_gray())
        embed.add_field(name="🗺️ Map", value=f"`{map_name}`", inline=True)
        embed.add_field(name="👥 Players", value=f"`{num_players}/{max_players}`", inline=True)
        embed.add_field(name="🕹️ Mod", value=f"`{game_mod}`", inline=True)
        embed.add_field(name="🚩 Gametype", value=f"`{gametype}`", inline=True)
        embed.add_field(name="⌛ Time Remaining", value=f"`{time_remaining_formatted}`", inline=True)
        embed.add_field(name="🔌 Address", value=f"`{full_address}`", inline=True)

        # --- Team 1 (Axis) ---
        tickets1 = server['tickets1'] or 'N/A'
        team1_header = f"Axis (Team 1) - Tickets: {tickets1}"
        team1_body = "```\nScore  Kills  Deaths  Ping  Player\n-----  -----  ------  ----  --------------\n"
        if not team1_players:
            team1_body += "No players on this team."
        else:
            for p in team1_players[:10]:
                player_name = p['player_name'] or 'Unknown'
                team1_body += f"{p['score'] or 0:<7}{p['kills'] or 0:<7}{p['deaths'] or 0:<8}{p['ping'] or 0:<6}{player_name[:14]}\n"
        team1_body += "```"
        embed.add_field(name=team1_header, value=team1_body, inline=False)
        
        # --- Team 2 (Allies) ---
        tickets2 = server['tickets2'] or 'N/A'
        team2_header = f"Allies (Team 2) - Tickets: {tickets2}"
        team2_body = "```\nScore  Kills  Deaths  Ping  Player\n-----  -----  ------  ----  --------------\n"
        if not team2_players:
            team2_body += "No players on this team."
        else:
            for p in team2_players[:10]:
                player_name = p['player_name'] or 'Unknown'
                team2_body += f"{p['score'] or 0:<7}{p['kills'] or 0:<7}{p['deaths'] or 0:<8}{p['ping'] or 0:<6}{player_name[:14]}\n"
        team2_body += "```"
        embed.add_field(name=team2_header, value=team2_body, inline=False)

        await ctx.followup.send(embed=embed)
    except Exception as e:
        print(f"Error in /serverinfo: {e}")
        await ctx.followup.send("Something went wrong, I couldn't fetch that server's info.", ephemeral=True)

# --- GROUP 2: SUBSCRIPTION MANAGEMENT ---

@bot.slash_command(name="subscribe", description="Get an alert when a map starts on a server.")
async def subscribe(
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
                f"❌ I don't have permission to **Send Messages** and **Embed Links** in {channel.mention}."
                " Please update my permissions and try again.",
                ephemeral=True
            )
            return

    query = """
    INSERT INTO subscriptions (user_id, server_name, map_name, players_over, guild_id, channel_id, is_paused)
    VALUES ($1, $2, $3, $4, $5, $6, false)
    ON CONFLICT (user_id, server_name, map_name)
    DO UPDATE SET
        players_over = EXCLUDED.players_over,
        guild_id = EXCLUDED.guild_id,
        channel_id = EXCLUDED.channel_id,
        is_paused = false;
    """
    try:
        await bot.db_pool.execute(
            query,
            ctx.author.id,
            server,
            map_name.lower(),
            players_over,
            ctx.guild.id,
            channel_id
        )
        
        destination = f"channel **{channel.name}**" if channel else "your **DMs**"
        await ctx.respond(
            f"✅ You are now subscribed to **{map_name}** on **{server}**.\n"
            f"Alerts will be sent to {destination}.", 
            ephemeral=True
        )
    except Exception as e:
        print(f"Error in /subscribe: {e}")
        await ctx.respond("Something went wrong, I couldn't save your subscription.", ephemeral=True)


@bot.slash_command(name="subscribe_server", description="Get an alert for *every* map change on a server.")
async def subscribe_server(
    ctx: discord.ApplicationContext,
    server: Option(str, "Start typing the server name", autocomplete=search_servers),
    players_over: Option(int, "Optional: Only alert if player count is over this number", required=False, default=0),
    channel: Option(discord.TextChannel, "Optional: The channel to post the alert in (posts to DMs if empty)", required=False, default=None)
):
    """Subscribes a user to all map changes on a specific server."""
    
    channel_id = channel.id if channel else None
    
    if channel:
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.send_messages or not perms.embed_links:
            await ctx.respond(
                f"❌ I don't have permission to **Send Messages** and **Embed Links** in {channel.mention}.",
                ephemeral=True
            )
            return

    query = """
    INSERT INTO subscriptions (user_id, server_name, map_name, players_over, guild_id, channel_id, is_paused)
    VALUES ($1, $2, $3, $4, $5, $6, false)
    ON CONFLICT (user_id, server_name, map_name)
    DO UPDATE SET
        players_over = EXCLUDED.players_over,
        guild_id = EXCLUDED.guild_id,
        channel_id = EXCLUDED.channel_id,
        is_paused = false;
    """
    try:
        await bot.db_pool.execute(
            query,
            ctx.author.id,
            server,
            SERVER_SUB_MAP_NAME,
            players_over,
            ctx.guild.id,
            channel_id
        )
        
        destination = f"channel **{channel.name}**" if channel else "your **DMs**"
        await ctx.respond(
            f"✅ You are now subscribed to **all map changes** on **{server}**.\n"
            f"Alerts will be sent to {destination}.", 
            ephemeral=True
        )
    except Exception as e:
        print(f"Error in /subscribe_server: {e}")
        await ctx.respond("Something went wrong, I couldn't save your subscription.", ephemeral=True)


@bot.slash_command(name="list", description="See all of your current map alerts.")
async def list_subscriptions(ctx: discord.ApplicationContext):
    
    query = "SELECT server_name, map_name, players_over, channel_id, is_paused FROM subscriptions WHERE user_id = $1"
    try:
        user_subs = await bot.db_pool.fetch(query, ctx.author.id)
        if not user_subs:
            await ctx.respond("You have no active subscriptions.", ephemeral=True)
            return

        embed = discord.Embed(title="Your Map Alert Subscriptions", color=discord.Color.blue())
        description = ""
        for sub in user_subs:
            player_condition = f" (Players > {sub['players_over']})" if sub.get('players_over', 0) > 0 else ""
            
            destination = "-> DMs"
            if sub['channel_id']:
                channel = bot.get_channel(sub['channel_id'])
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
        print(f"Error in /list: {e}")
        await ctx.respond("Something went wrong, I couldn't fetch your subscriptions.", ephemeral=True)


@bot.slash_command(name="unsubscribe", description="Removes all of your active map alerts.")
async def unsubscribe(ctx: discord.ApplicationContext):
    try:
        status = await bot.db_pool.execute("DELETE FROM subscriptions WHERE user_id = $1", ctx.author.id)
        deleted_count = int(status.split(' ')[1])
        await ctx.respond(f"🗑️ All {deleted_count} of your subscriptions have been removed.", ephemeral=True)
    except Exception as e:
        print(f"Error in /unsubscribe: {e}")
        await ctx.respond("Something went wrong, I couldn't remove your subscriptions.", ephemeral=True)


@bot.slash_command(name="pause_alerts", description="Temporarily pause or unpause all of your map alerts.")
async def pause_alerts(
    ctx: discord.ApplicationContext,
    status: Option(str, "Pause or unpause your alerts", choices=["pause", "unpause"])
):
    """Pauses or unpauses all alerts for a user."""
    
    is_paused_bool = True if status == "pause" else False
    
    query = "UPDATE subscriptions SET is_paused = $1 WHERE user_id = $2"
    
    try:
        update_status = await bot.db_pool.execute(query, is_paused_bool, ctx.author.id)
        count = int(update_status.split(' ')[1])
        
        if count == 0:
            await ctx.respond("You have no subscriptions to update.", ephemeral=True)
            return
            
        action_text = "paused" if is_paused_bool else "unpaused"
        await ctx.respond(f"✅ All {count} of your subscriptions have been **{action_text}**.", ephemeral=True)
        
    except Exception as e:
        print(f"Error in /pause_alerts: {e}")
        await ctx.respond("Something went wrong, I couldn't update your subscriptions.", ephemeral=True)

# --- GROUP 3: DND MANAGEMENT (NEW) ---

# Helper dicts for DND
DAY_MAP = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6
}
DAY_NAMES = [ "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun" ]

# Create a DND command group
dnd = bot.create_group("dnd", "Manage your Do Not Disturb (DND) schedule.")

@dnd.command(name="set", description="Set a DND schedule to block alerts.")
async def dnd_set(
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
        await ctx.followup.send(f"❌ Unknown timezone: `{timezone}`. Please use the autocomplete to find a valid name (e.g., `US/Eastern`).")
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
                await ctx.followup.send(f"❌ Invalid day: `{day_str}`. Must be `all`, `weekdays`, `weekends`, or a list like `mon,tue,sun`.")
                return
    
    if not day_list:
        await ctx.followup.send("❌ You must provide at least one valid day.")
        return
    
    # 3. Convert times to UTC
    # Create a "dummy" date in the user's timezone to do the conversion
    now_local = datetime.datetime.now(user_tz)
    
    start_local = now_local.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end_local = now_local.replace(hour=end_hour, minute=0, second=0, microsecond=0)

    start_utc = start_local.astimezone(pytz.utc)
    end_utc = end_local.astimezone(pytz.utc)

    # Get the UTC day list (0-6, Mon-Sun)
    # This handles the case where "Monday 22:00" for the user is already "Tuesday 02:00" in UTC
    utc_days = set()
    for day_offset in range(8): # Check a full week + 1 day
        test_date = start_local + datetime.timedelta(days=day_offset)
        if test_date.weekday() in day_list:
            utc_days.add(test_date.astimezone(pytz.utc).weekday())

    # 4. Save to DB
    query = """
    INSERT INTO user_dnd_rules (user_id, start_hour_utc, end_hour_utc, weekdays_utc, timezone)
    VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT (user_id) DO UPDATE SET
        start_hour_utc = EXCLUDED.start_hour_utc,
        end_hour_utc = EXCLUDED.end_hour_utc,
        weekdays_utc = EXCLUDED.weekdays_utc,
        timezone = EXCLUDED.timezone;
    """
    try:
        await bot.db_pool.execute(query, ctx.author.id, start_utc.hour, end_utc.hour, list(utc_days), timezone)
        
        day_names_str = ", ".join([DAY_NAMES[i] for i in day_list])
        await ctx.followup.send(f"✅ DND schedule set!\n"
                                f"Alerts will be **blocked** from **{start_hour:02d}:00** to **{end_hour:02d}:00** ({timezone})\n"
                                f"On these days: **{day_names_str}**")
    except Exception as e:
        print(f"Error in /dnd set: {e}")
        await ctx.followup.send("Something went wrong, I couldn't save your DND schedule.")


@dnd.command(name="view", description="Show your current DND schedule.")
async def dnd_view(ctx: discord.ApplicationContext):
    await ctx.defer(ephemeral=True)
    
    query = "SELECT * FROM user_dnd_rules WHERE user_id = $1"
    rule = await bot.db_pool.fetchrow(query, ctx.author.id)
    
    if not rule:
        await ctx.followup.send("You do not have a DND schedule set. Use `/dnd set` to create one.")
        return
        
    # Convert UTC hours back to user's local timezone for display
    try:
        user_tz = pytz.timezone(rule['timezone'])
        now_utc = datetime.datetime.now(pytz.utc)
        
        start_utc = now_utc.replace(hour=rule['start_hour_utc'], minute=0)
        end_utc = now_utc.replace(hour=rule['end_hour_utc'], minute=0)
        
        start_local = start_utc.astimezone(user_tz)
        end_local = end_utc.astimezone(user_tz)
        
        # Reconstruct the day list
        # This is a bit complex, but we check which *local* days are affected by the UTC rules
        local_days = set()
        for i in range(7): # Check all 7 days
            if i in rule['weekdays_utc']:
                local_days.add(DAY_NAMES[i])
        
        day_names_str = ", ".join(sorted(list(local_days), key=lambda d: DAY_NAMES.index(d)))

        await ctx.followup.send(f"**Your DND Schedule:**\n"
                                f"Alerts are **blocked** from **{start_local.hour:02d}:00** to **{end_local.hour:02d}:00** ({rule['timezone']})\n"
                                f"On these days (in UTC): **{day_names_str}**\n"
                                f"*(Note: Day conversion is complex. Set your rule again if this looks wrong.)*")
    except Exception as e:
        print(f"Error in /dnd view: {e}")
        await ctx.followup.send("Something went wrong, I couldn't display your schedule.")


@dnd.command(name="clear", description="Clear your DND schedule.")
async def dnd_clear(ctx: discord.ApplicationContext):
    query = "DELETE FROM user_dnd_rules WHERE user_id = $1"
    status = await bot.db_pool.execute(query, ctx.author.id)
    
    if status == "DELETE 0":
        await ctx.respond("You had no DND schedule to clear.", ephemeral=True)
    else:
        await ctx.respond("✅ Your DND schedule has been cleared. You will now receive all alerts.", ephemeral=True)

# --- GROUP 4: BOT STATISTICS ---

@bot.slash_command(name="alert_stats", description="See which maps and servers are most popular.")
async def alert_stats(ctx: discord.ApplicationContext):
    """Shows statistics about bot subscriptions."""
    
    await ctx.defer(ephemeral=False) 

    map_query = """
    SELECT map_name, COUNT(*) as count
    FROM subscriptions
    WHERE map_name <> $1
    GROUP BY map_name
    ORDER BY count DESC
    LIMIT 10;
    """
    
    server_query = """
    SELECT server_name, COUNT(*) as count
    FROM subscriptions
    GROUP BY server_name
    ORDER BY count DESC
    LIMIT 10;
    """

    try:
        map_rows = await bot.db_pool.fetch(map_query, SERVER_SUB_MAP_NAME)
        server_rows = await bot.db_pool.fetch(server_query)
        
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
        print(f"Error in /alert_stats: {e}")
        await ctx.followup.send("Something went wrong, I couldn't fetch the stats.", ephemeral=True)


# --- BACKGROUND TASK FOR ALERTS (UPDATED) ---
@tasks.loop(seconds=45)
async def check_map_changes():
    global last_known_maps
    if not bot.db_pool:
        print("Database pool not ready, skipping map check.")
        return
        
    # Get current UTC time, hour, and weekday
    now_utc = datetime.datetime.now(pytz.utc)
    current_utc_hour = now_utc.hour
    current_utc_weekday = now_utc.weekday() # 0 = Mon, 6 = Sun

    try:
        query = """
        SELECT current_server_name, current_map, current_player_count, current_max_players
        FROM servers
        WHERE current_state IN ('ACTIVE', 'EMPTY');
        """
        online_servers_rows = await bot.db_pool.fetch(query)
        online_servers = {s['current_server_name']: s for s in online_servers_rows}

        if not last_known_maps:
            for server_name, server_data in online_servers.items():
                last_known_maps[server_name] = server_data['current_map']
            print("Initial map state has been populated.")
            return

        for server_name, server_data in online_servers.items():
            current_map = server_data['current_map']
            last_map = last_known_maps.get(server_name)

            if current_map and last_map != current_map:
                print(f"MAP CHANGE DETECTED on {server_name}: {last_map} -> {current_map}")
                
                # --- QUERY UPDATED TO JOIN DND RULES ---
                subscription_query = """
                SELECT 
                    s.user_id, s.players_over, s.channel_id, s.map_name,
                    dnd.start_hour_utc, dnd.end_hour_utc, dnd.weekdays_utc
                FROM subscriptions s
                LEFT JOIN user_dnd_rules dnd ON s.user_id = dnd.user_id
                WHERE 
                    s.server_name = $1
                    AND s.is_paused = false
                    AND (s.map_name = $2 OR s.map_name = $3);
                """
                subs_to_alert = await bot.db_pool.fetch(
                    subscription_query,
                    server_name,
                    current_map.lower(),
                    SERVER_SUB_MAP_NAME
                )
                
                player_count = server_data['current_player_count']
                
                for sub in subs_to_alert:
                    if player_count <= sub.get("players_over", 0):
                        continue # Skip for player count
                    
                    # --- NEW DND CHECK ---
                    if sub['start_hour_utc'] is not None:
                        is_dnd_day = current_utc_weekday in sub['weekdays_utc']
                        
                        # Check if current hour is in the DND range
                        # This logic handles "overnight" ranges (e.g., 22:00 to 06:00)
                        start_h = sub['start_hour_utc']
                        end_h = sub['end_hour_utc']
                        is_dnd_hour = False
                        
                        if start_h <= end_h:
                            # Simple range (e.g., 09:00 to 17:00)
                            is_dnd_hour = start_h <= current_utc_hour < end_h
                        else:
                            # Overnight range (e.g., 22:00 to 06:00)
                            is_dnd_hour = current_utc_hour >= start_h or current_utc_hour < end_h
                        
                        if is_dnd_day and is_dnd_hour:
                            print(f"Skipping alert for user {sub['user_id']} due to DND.")
                            continue # Skip alert, user is in DND
                    
                    # --- End DND Check ---

                    if sub['map_name'] == SERVER_SUB_MAP_NAME:
                        title = "📢 BF1942 Server Alert!"
                        description = f"**{server_name}** has just changed maps to **{current_map}**!"
                    else:
                        title = "📢 BF1942 Map Alert!"
                        description = f"The map **{current_map}** has just started on **{server_name}**!"
                    
                    embed = discord.Embed(
                        title=title,
                        description=description,
                        color=discord.Color.gold()
                    )
                    embed.add_field(name="Players", value=f"{player_count}/{server_data['current_max_players']}")
                    
                    channel_id = sub.get("channel_id")
                    
                    if channel_id:
                        try:
                            channel = bot.get_channel(channel_id)
                            if channel:
                                perms = channel.permissions_for(channel.guild.me)
                                if perms.send_messages and perms.embed_links:
                                    await channel.send(embed=embed)
                                else:
                                    print(f"PERMISSION ERROR: Bot lacks 'Send Messages' or 'Embed Links' for channel {channel_id}.")
                            else:
                                print(f"ERROR: Could not find channel with ID {channel_id}. Maybe it was deleted?")
                        except Exception as e:
                            print(f"An error occurred sending a channel alert: {e}")
                    
                    else:
                        try:
                            user = await bot.fetch_user(sub["user_id"])
                            await user.send(embed=embed)
                        except discord.Forbidden:
                            print(f"Could not send DM to user {sub['user_id']}. They may have DMs disabled.")
                        except Exception as e:
                            print(f"An error occurred sending a DM: {e}")

        # Update last_known_maps state
        for server_name, server_data in online_servers.items():
            last_known_maps[server_name] = server_data['current_map']
            
    except Exception as e:
        print(f"Error in background task: {e}")


# --- BOT EVENTS ---
@bot.event
async def on_ready():
    try:
        bot.db_pool = await asyncpg.create_pool(POSTGRES_DSN)
        print("✅ Database connection pool created.")
    except Exception as e:
        print(f"!!!!!!!!!!\nCould not connect to database: {e}\n!!!!!!!!!!")
        return
    
    print(f'✅ Logged in as {bot.user}')
    await bot.sync_commands()
    print('Starting background task for map change alerts...')
    check_map_changes.start()

@bot.event
async def on_close():
    if bot.db_pool:
        print("Closing database connection pool...")
        await bot.db_pool.close()
    await bot.close()

# --- RUN THE BOT ---
try:
    bot.run(DISCORD_TOKEN)
except Exception as e:
    print(f"Error running bot: {e}")