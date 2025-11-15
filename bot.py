# main.py
import asyncio
from engine.scheduler import Scheduler
from engine.database import Database  # Import the Database class

async def main():
    """Main function to start the ingestion engine."""
    # Create the database manager instance here
    db_manager = Database()
    
    # "Inject" the instance into the scheduler when you create it
    scheduler = Scheduler(db_manager)
    
    try:
        await scheduler.run()
    except asyncio.CancelledError:
        print("Scheduler run cancelled.")
    finally:
        # Use the instance to disconnect
        await db_manager.disconnect()
        print("Application shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested by user.")
import discord
from discord.ext import commands, tasks
from discord.commands import Option, permissions
import asyncpg
import os
from dotenv import load_dotenv
import re
import asyncio

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


# --- DISCORD COMMANDS ---
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

# --- NEW COMMANDS ---

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


@bot.slash_command(name="alert_stats", description="See which maps and servers are most popular.")
# --- PERMISSION CHECK REMOVED ---
async def alert_stats(ctx: discord.ApplicationContext):
    """Shows statistics about bot subscriptions."""
    
    # --- NOW SETTING ephemeral=False ---
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
        # --- UPDATED ERROR MESSAGE ---
        await ctx.followup.send("Something went wrong, I couldn't fetch the stats.", ephemeral=True)

# --- ERROR HANDLER REMOVED ---      


# --- BACKGROUND TASK FOR ALERTS ---
@tasks.loop(seconds=45)
async def check_map_changes():
    global last_known_maps
    if not bot.db_pool:
        print("Database pool not ready, skipping map check.")
        return

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
                
                subscription_query = """
                SELECT user_id, players_over, channel_id, map_name
                FROM subscriptions
                WHERE 
                    server_name = $1
                    AND is_paused = false
                    AND (map_name = $2 OR map_name = $3);
                """
                subs_to_alert = await bot.db_pool.fetch(
                    subscription_query,
                    server_name,
                    current_map.lower(),
                    SERVER_SUB_MAP_NAME
                )
                
                player_count = server_data['current_player_count']
                
                for sub in subs_to_alert:
                    if player_count > sub.get("players_over", 0):
                        
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