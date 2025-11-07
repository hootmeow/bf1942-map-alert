import discord
from discord.ext import commands, tasks
from discord.commands import Option
import asyncpg  # --- REFACTORED ---
import os
from dotenv import load_dotenv
import re
import asyncio

# --- CONFIGURATION ---
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
# --- REFACTORED ---
# Set this in your .env file
# e.g. POSTGRES_DSN=postgres://bf1942_db_user:PASSWORD@your_host:5432/bf1942_data
POSTGRES_DSN = os.getenv("POSTGRES_DSN")

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.presences = True
intents.members = True
bot = commands.Bot(intents=intents)
bot.db_pool = None  # --- REFACTORED --- Will hold the connection pool

# This dictionary will hold the last known map for each server to detect changes.
last_known_maps = {}

# --- AUTOCOMPLETE FUNCTIONS ---
# --- REFACTORED ---
async def search_servers(ctx: discord.AutocompleteContext):
    """Provides server name suggestions for autocomplete."""
    if not bot.db_pool:
        return []
    
    query = "SELECT server_name FROM live_server_snapshot WHERE server_name ILIKE $1 AND status = 'online' ORDER BY player_count DESC LIMIT 25"
    try:
        rows = await bot.db_pool.fetch(query, f"{ctx.value}%")
        return [row['server_name'] for row in rows]
    except Exception as e:
        print(f"Error in search_servers: {e}")
        return []

# --- REFACTORED ---
async def search_maps(ctx: discord.AutocompleteContext):
    """Provides map name suggestions using the rounds table."""
    if not bot.db_pool:
        return []
    
    # We query the 'rounds' table for a distinct list of map names
    query = "SELECT DISTINCT map_name FROM rounds WHERE map_name ILIKE $1 LIMIT 25"
    try:
        rows = await bot.db_pool.fetch(query, f"{ctx.value}%")
        return [row['map_name'] for row in rows]
    except Exception as e:
        print(f"Error in search_maps: {e}")
        return []

# --- DISCORD COMMANDS ---
@bot.slash_command(name="subscribe", description="Get a DM when a map starts on a server.")
async def subscribe(
    ctx: discord.ApplicationContext,
    server: Option(str, "Start typing the server name", autocomplete=search_servers),
    map_name: Option(str, "Start typing the map name", autocomplete=search_maps),
    players_over: Option(int, "Optional: Only alert if player count is over this number", required=False, default=0)
):
    # --- REFACTORED ---
    # Use SQL INSERT... ON CONFLICT for an "upsert"
    query = """
    INSERT INTO subscriptions (user_id, server_name, map_name, players_over, guild_id)
    VALUES ($1, $2, $3, $4, $5)
    ON CONFLICT (user_id, server_name, map_name)
    DO UPDATE SET
        players_over = EXCLUDED.players_over,
        guild_id = EXCLUDED.guild_id;
    """
    try:
        await bot.db_pool.execute(
            query,
            ctx.author.id,
            server,
            map_name.lower(),
            players_over,
            ctx.guild.id
        )
        await ctx.respond(f"✅ You are now subscribed to **{map_name}** on **{server}**.", ephemeral=True)
    except Exception as e:
        print(f"Error in /subscribe: {e}")
        await ctx.respond("Something went wrong, I couldn't save your subscription.", ephemeral=True)


@bot.slash_command(name="list", description="See all of your current map alerts.")
async def list_subscriptions(ctx: discord.ApplicationContext):
    # --- REFACTORED ---
    query = "SELECT server_name, map_name, players_over FROM subscriptions WHERE user_id = $1"
    try:
        user_subs = await bot.db_pool.fetch(query, ctx.author.id)
        if not user_subs:
            await ctx.respond("You have no active subscriptions.", ephemeral=True)
            return

        embed = discord.Embed(title="Your Map Alert Subscriptions", color=discord.Color.blue())
        description = ""
        for sub in user_subs:
            player_condition = f" (Players > {sub['players_over']})" if sub.get('players_over', 0) > 0 else ""
            description += f"**{sub['server_name']}** -> **{sub['map_name']}**{player_condition}\n"
        embed.description = description
        await ctx.respond(embed=embed, ephemeral=True)
    except Exception as e:
        print(f"Error in /list: {e}")
        await ctx.respond("Something went wrong, I couldn't fetch your subscriptions.", ephemeral=True)


@bot.slash_command(name="unsubscribe", description="Removes all of your active map alerts.")
async def unsubscribe(ctx: discord.ApplicationContext):
    # --- REFACTORED ---
    try:
        status = await bot.db_pool.execute("DELETE FROM subscriptions WHERE user_id = $1", ctx.author.id)
        # asyncpg returns a string like 'DELETE 5'
        deleted_count = int(status.split(' ')[1])
        await ctx.respond(f"🗑️ All {deleted_count} of your subscriptions have been removed.", ephemeral=True)
    except Exception as e:
        print(f"Error in /unsubscribe: {e}")
        await ctx.respond("Something went wrong, I couldn't remove your subscriptions.", ephemeral=True)


@bot.slash_command(name="servers", description="See a live list of active BF1942 servers.")
async def servers(ctx: discord.ApplicationContext):
    await ctx.defer(ephemeral=True)
    # --- REFACTORED ---
    query = """
    SELECT server_name, map_name, player_count, max_players
    FROM live_server_snapshot
    WHERE status = 'online'
    ORDER BY player_count DESC
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
            players = f"{server['player_count']}/{server['max_players']}"
            embed.add_field(
                name=f"**{server['server_name']}**",
                value=f"🗺️ Map: **{server['map_name']}** | 👥 Players: **{players}**",
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
    # --- REFACTORED ---
    query = """
    SELECT server_name, player_count, max_players
    FROM live_server_snapshot
    WHERE status = 'online' AND map_name ILIKE $1
    ORDER BY player_count DESC;
    """
    try:
        server_list = await bot.db_pool.fetch(query, map_name)
        if not server_list:
            await ctx.followup.send(f"Sorry, no servers are currently playing **{map_name}**.")
            return

        embed = discord.Embed(title=f"Servers Playing: {map_name}", color=discord.Color.orange())
        description = ""
        for server in server_list:
            players = f"{server['player_count']}/{server['max_players']}"
            description += f"**{server['server_name']}** ({players} players)\n"
        embed.description = description
        await ctx.followup.send(embed=embed)
    except Exception as e:
        print(f"Error in /playing: {e}")
        await ctx.followup.send("Something went wrong, I couldn't find servers for that map.", ephemeral=True)


@bot.slash_command(name="serverinfo", description="Get detailed live info for a specific server.")
async def serverinfo(
    ctx: discord.ApplicationContext,
    server_name: Option(str, "Start typing the server name", autocomplete=search_servers)
):
    await ctx.defer(ephemeral=True)

    # --- REFACTORED ---
    # We join live_server_snapshot with servers to get the game port
    server_query = """
    SELECT
        lss.server_ip, lss.server_port, lss.server_name, lss.map_name, lss.player_count, lss.max_players,
        lss.gametype, lss.round_time_remain, lss.tickets1, lss.tickets2, lss.unpure_mods,
        s.current_game_port
    FROM live_server_snapshot lss
    LEFT JOIN servers s ON lss.server_ip = s.ip AND lss.server_port = s.port
    WHERE lss.server_name = $1 AND lss.status = 'online';
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
        hostname = server['server_name']
        map_name = server['map_name'] or 'N/A'
        num_players = server['player_count']
        max_players = server['max_players']
        # Use unpure_mods if available, fallback to gametype
        game_mod = server['unpure_mods'] or server['gametype'] or 'N/A'
        gametype = server['gametype'] or 'N/A'
        
        ip_address = str(server['server_ip'])
        game_port = server['current_game_port'] or 'N/A'
        full_address = f"{ip_address}:{game_port}"

        time_remain_sec = int(server['round_time_remain'] or 0)
        minutes, seconds = divmod(time_remain_sec, 60)
        time_remaining_formatted = f"{minutes}:{seconds:02d}"

        # --- Player Fetching ---
        all_players = await bot.db_pool.fetch(player_query, server['server_ip'], server['server_port'])
        
        # --- Player Sorting (in Python, as we need to split teams) ---
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


@bot.slash_command(name="find", description="Find which server a specific player is on.")
async def find(
    ctx: discord.ApplicationContext,
    player_name: Option(str, "Enter the full, case-sensitive player name")
):
    await ctx.defer(ephemeral=True)
    
    # --- REFACTORED ---
    # This is now a single, efficient query instead of a massive loop
    query = """
    SELECT lss.server_name, lps.score, lps.kills, lps.deaths
    FROM live_player_snapshot lps
    JOIN live_server_snapshot lss ON lps.server_ip = lss.server_ip AND lps.server_port = lss.server_port
    WHERE lps.player_name = $1 AND lss.status = 'online';
    """

    try:
        found_player = await bot.db_pool.fetchrow(query, player_name)
    
        if found_player:
            embed = discord.Embed(
                title=f"🕵️ Player Found: {player_name}",
                color=discord.Color.blue()
            )
            embed.add_field(name="Server", value=found_player['server_name'], inline=False)
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

    # --- REFACTORED ---
    query = """
    SELECT server_name, map_name, player_count, max_players
    FROM live_server_snapshot
    WHERE status = 'online' AND player_count > 0 AND player_count < 6
    ORDER BY player_count ASC
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
            players = f"{server['player_count']}/{server['max_players']}"
            map_name = server['map_name']
            embed.add_field(
                name=f"**{server['server_name']}**",
                value=f"🗺️ Map: **{map_name}** | 👥 Players: **{players}**",
                inline=False
            )
        await ctx.followup.send(embed=embed)
    except Exception as e:
        print(f"Error in /seed: {e}")
        await ctx.followup.send("Something went wrong, I couldn't find servers to seed.", ephemeral=True)


# --- BACKGROUND TASK FOR ALERTS ---
@tasks.loop(seconds=45)
async def check_map_changes():
    global last_known_maps
    if not bot.db_pool:
        print("Database pool not ready, skipping map check.")
        return

    try:
        # --- REFACTORED ---
        query = """
        SELECT server_name, map_name, player_count, max_players
        FROM live_server_snapshot
        WHERE status = 'online';
        """
        online_servers_rows = await bot.db_pool.fetch(query)
        online_servers = {s['server_name']: s for s in online_servers_rows}

        if not last_known_maps:
            for server_name, server_data in online_servers.items():
                last_known_maps[server_name] = server_data['map_name']
            print("Initial map state has been populated.")
            return

        for server_name, server_data in online_servers.items():
            current_map = server_data['map_name']
            last_map = last_known_maps.get(server_name)

            if current_map and last_map != current_map:
                print(f"MAP CHANGE DETECTED on {server_name}: {last_map} -> {current_map}")
                
                # --- REFACTORED ---
                subscription_query = """
                SELECT user_id, players_over
                FROM subscriptions
                WHERE server_name = $1 AND map_name = $2;
                """
                subs_to_alert = await bot.db_pool.fetch(
                    subscription_query,
                    server_name,
                    current_map.lower()
                )
                
                player_count = server_data['player_count']
                
                for sub in subs_to_alert:
                    if player_count > sub.get("players_over", 0):
                        try:
                            user = await bot.fetch_user(sub["user_id"])
                            embed = discord.Embed(
                                title="📢 BF1942 Map Alert!",
                                description=f"The map **{current_map}** has just started on **{server_name}**!",
                                color=discord.Color.gold()
                            )
                            embed.add_field(name="Players", value=f"{player_count}/{server_data['max_players']}")
                            await user.send(embed=embed)
                        except discord.Forbidden:
                            print(f"Could not send DM to user {sub['user_id']}. They may have DMs disabled.")
                        except Exception as e:
                            print(f"An error occurred sending a DM: {e}")

        # Update last_known_maps state
        for server_name, server_data in online_servers.items():
            last_known_maps[server_name] = server_data['map_name']
            
    except Exception as e:
        print(f"Error in background task: {e}")


# --- BOT EVENTS ---
@bot.event
async def on_ready():
    # --- REFACTORED ---
    # Create the database connection pool
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

# --- REFACTORED ---
# Gracefully close the database pool on bot shutdown
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