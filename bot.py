import discord
from discord.ext import commands, tasks
from discord.commands import Option
import pymongo
import os
from dotenv import load_dotenv
import re

# --- CONFIGURATION ---
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# --- DATABASE CONNECTION ---
mongo_client = pymongo.MongoClient(MONGO_URI)
# !!! IMPORTANT: Change "prod_stats" to your actual database name if different !!!
db = mongo_client["prod_stats"]
servers_collection = db["servers"]
maps_collection = db["unique_maps"]
subscriptions_collection = db["subscriptions"]

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.presences = True
intents.members = True
bot = commands.Bot(intents=intents)

# This dictionary will hold the last known map for each server to detect changes.
last_known_maps = {}

# --- AUTOCOMPLETE FUNCTIONS ---
async def search_servers(ctx: discord.AutocompleteContext):
    """Provides server name suggestions for autocomplete."""
    escaped_value = re.escape(ctx.value)
    query = {"info.hostname": {"$regex": escaped_value, "$options": "i"}}
    cursor = servers_collection.find(query).limit(25)
    return [server["info"]["hostname"] for server in cursor]

async def search_maps(ctx: discord.AutocompleteContext):
    """Provides map name suggestions using the efficient unique_maps collection."""
    query = {"_id": {"$regex": f"^{ctx.value}", "$options": "i"}}
    cursor = maps_collection.find(query).limit(25)
    return [map_doc["_id"] for map_doc in cursor]

# --- DISCORD COMMANDS ---
@bot.slash_command(name="subscribe", description="Get a DM when a map starts on a server.")
async def subscribe(
    ctx: discord.ApplicationContext,
    server: Option(str, "Start typing the server name", autocomplete=search_servers),
    map_name: Option(str, "Start typing the map name", autocomplete=search_maps),
    players_over: Option(int, "Optional: Only alert if player count is over this number", required=False, default=0)
):
    subscription = {
        "user_id": ctx.author.id,
        "server_name": server,
        "map_name": map_name.lower(),
        "players_over": players_over,
        "guild_id": ctx.guild.id
    }
    subscriptions_collection.update_one(
        {"user_id": ctx.author.id, "server_name": server, "map_name": map_name.lower()},
        {"$set": subscription},
        upsert=True
    )
    await ctx.respond(f"✅ You are now subscribed to **{map_name}** on **{server}**.", ephemeral=True)

@bot.slash_command(name="list", description="See all of your current map alerts.")
async def list_subscriptions(ctx: discord.ApplicationContext):
    user_subs = list(subscriptions_collection.find({"user_id": ctx.author.id}))
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

@bot.slash_command(name="unsubscribe", description="Removes all of your active map alerts.")
async def unsubscribe(ctx: discord.ApplicationContext):
    result = subscriptions_collection.delete_many({"user_id": ctx.author.id})
    await ctx.respond(f"🗑️ All {result.deleted_count} of your subscriptions have been removed.", ephemeral=True)

@bot.slash_command(name="servers", description="See a live list of active BF1942 servers.")
async def servers(ctx: discord.ApplicationContext):
    await ctx.defer(ephemeral=True)
    server_list = list(servers_collection.find({"status": "online"}).sort("info.num_players", -1))
    if not server_list:
        await ctx.followup.send("Could not find any online servers right now.")
        return

    embed = discord.Embed(
        title="Live BF1942 Servers",
        description=f"Showing {len(server_list)} online servers, sorted by player count.",
        color=discord.Color.green()
    )
    for server in server_list[:25]:
        server_info = server.get("info", {})
        players = f"{server_info.get('num_players', 0)}/{server_info.get('max_players', 0)}"
        map_name = server_info.get('mapname', 'Unknown')
        embed.add_field(
            name=f"**{server_info.get('hostname', 'Unknown Server')}**",
            value=f"🗺️ Map: **{map_name}** | 👥 Players: **{players}**",
            inline=False
        )
    await ctx.followup.send(embed=embed)

@bot.slash_command(name="playing", description="Find servers currently playing a specific map.")
async def playing(
    ctx: discord.ApplicationContext,
    map_name: Option(str, "Start typing the map name", autocomplete=search_maps)
):
    await ctx.defer(ephemeral=True)
    server_list = list(servers_collection.find({
        "status": "online",
        "info.mapname": {"$regex": f"^{map_name}", "$options": "i"}
    }).sort("info.num_players", -1))
    if not server_list:
        await ctx.followup.send(f"Sorry, no servers are currently playing **{map_name}**.")
        return

    embed = discord.Embed(title=f"Servers Playing: {map_name}", color=discord.Color.orange())
    description = ""
    for server in server_list:
        server_info = server.get("info", {})
        players = f"{server_info.get('num_players', 0)}/{server_info.get('max_players', 0)}"
        description += f"**{server_info.get('hostname', 'Unknown')}** ({players} players)\n"
    embed.description = description
    await ctx.followup.send(embed=embed)

@bot.slash_command(name="serverinfo", description="Get detailed live info for a specific server.")
async def serverinfo(
    ctx: discord.ApplicationContext,
    server_name: Option(str, "Start typing the server name", autocomplete=search_servers)
):
    await ctx.defer(ephemeral=True)

    server = servers_collection.find_one({"info.hostname": server_name})

    if not server:
        await ctx.followup.send("Could not find that server. It might be offline.")
        return

    # --- Data Extraction ---
    server_info = server.get("info", {})
    hostname = server_info.get('hostname', 'Unknown Server')
    map_name = server_info.get('mapname', 'N/A')
    num_players = server_info.get('num_players', 0)
    max_players = server_info.get('max_players', 0)
    game_mod = server_info.get('active_mods', server_info.get('gametype', 'N/A'))
    gametype = server_info.get('gametype', 'N/A')
    
    ip_address = server.get('ip', 'N/A')
    game_port = server_info.get('hostport', 'N/A')
    full_address = f"{ip_address}:{game_port}"

    time_remain_sec = int(server_info.get('roundtimeremain', 0))
    minutes, seconds = divmod(time_remain_sec, 60)
    time_remaining_formatted = f"{minutes}:{seconds:02d}"

    # --- Player Sorting ---
    all_players = server.get("players", [])
    team1_players = sorted([p for p in all_players if p.get("team") == 1], key=lambda x: x.get('score', 0), reverse=True)
    team2_players = sorted([p for p in all_players if p.get("team") == 2], key=lambda x: x.get('score', 0), reverse=True)

    # --- Embed Creation ---
    embed = discord.Embed(title=f"**{hostname}**", color=discord.Color.dark_gray())
    embed.add_field(name="🗺️ Map", value=f"`{map_name}`", inline=True)
    embed.add_field(name="👥 Players", value=f"`{num_players}/{max_players}`", inline=True)
    embed.add_field(name="🕹️ Mod", value=f"`{game_mod}`", inline=True)
    embed.add_field(name="🚩 Gametype", value=f"`{gametype}`", inline=True)
    embed.add_field(name="⌛ Time Remaining", value=f"`{time_remaining_formatted}`", inline=True)
    embed.add_field(name="🔌 Address", value=f"`{full_address}`", inline=True)

    # --- Team 1 (Axis) ---
    tickets1 = server_info.get('tickets1', 'N/A')
    team1_header = f"Axis (Team 1) - Tickets: {tickets1}"
    team1_body = "```\nScore  Kills  Deaths  Ping  Player\n-----  -----  ------  ----  --------------\n"
    if not team1_players:
        team1_body += "No players on this team."
    else:
        for p in team1_players[:10]:
            player_name = p.get('name', 'Unknown') or 'Unknown'
            team1_body += f"{p.get('score', 0):<7}{p.get('kills', 0):<7}{p.get('deaths', 0):<8}{p.get('ping', 0):<6}{player_name[:14]}\n"
    team1_body += "```"
    embed.add_field(name=team1_header, value=team1_body, inline=False)
    
    # --- Team 2 (Allies) ---
    tickets2 = server_info.get('tickets2', 'N/A')
    team2_header = f"Allies (Team 2) - Tickets: {tickets2}"
    team2_body = "```\nScore  Kills  Deaths  Ping  Player\n-----  -----  ------  ----  --------------\n"
    if not team2_players:
        team2_body += "No players on this team."
    else:
        for p in team2_players[:10]:
            player_name = p.get('name', 'Unknown') or 'Unknown'
            team2_body += f"{p.get('score', 0):<7}{p.get('kills', 0):<7}{p.get('deaths', 0):<8}{p.get('ping', 0):<6}{player_name[:14]}\n"
    team2_body += "```"
    embed.add_field(name=team2_header, value=team2_body, inline=False)

    await ctx.followup.send(embed=embed)

@bot.slash_command(name="find", description="Find which server a specific player is on.")
async def find(
    ctx: discord.ApplicationContext,
    player_name: Option(str, "Enter the full, case-sensitive player name")
):
    await ctx.defer(ephemeral=True)

    found_player = None
    server_of_player = None

    # Query all online servers
    online_servers = servers_collection.find({"status": "online"})

    for server in online_servers:
        for player in server.get("players", []):
            # Find an exact match for the player name
            if player.get("name") == player_name:
                found_player = player
                server_of_player = server.get("info", {})
                break
        if found_player:
            break
    
    if found_player and server_of_player:
        embed = discord.Embed(
            title=f"🕵️ Player Found: {found_player.get('name')}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Server", value=server_of_player.get('hostname', 'N/A'), inline=False)
        embed.add_field(name="Score", value=str(found_player.get('score', 0)), inline=True)
        embed.add_field(name="Kills", value=str(found_player.get('kills', 0)), inline=True)
        embed.add_field(name="Deaths", value=str(found_player.get('deaths', 0)), inline=True)
        await ctx.followup.send(embed=embed)
    else:
        await ctx.followup.send(f"Could not find a player named **{player_name}** on any active server.")

@bot.slash_command(name="seed", description="Find servers with a low player count to help get a game started.")
async def seed(ctx: discord.ApplicationContext):
    await ctx.defer(ephemeral=True)

    # Find servers with 1 to 5 players, sorted by the fewest players first
    server_list = list(servers_collection.find({
        "status": "online",
        "info.num_players": {"$gt": 0, "$lt": 6}
    }).sort("info.num_players", 1))

    if not server_list:
        await ctx.followup.send("No servers currently need seeding. Try the `/servers` command.")
        return

    embed = discord.Embed(
        title="🌱 Servers to Seed",
        description="These servers have a few players and are perfect to join and get a round started.",
        color=discord.Color.dark_green()
    )
    for server in server_list[:25]:
        server_info = server.get("info", {})
        players = f"{server_info.get('num_players', 0)}/{server_info.get('max_players', 0)}"
        map_name = server_info.get('mapname', 'Unknown')

        embed.add_field(
            name=f"**{server_info.get('hostname', 'Unknown Server')}**",
            # The join link has been removed from this line
            value=f"🗺️ Map: **{map_name}** | 👥 Players: **{players}**",
            inline=False
        )
    await ctx.followup.send(embed=embed)

# --- BACKGROUND TASK FOR ALERTS ---
# --- BACKGROUND TASK FOR ALERTS ---
@tasks.loop(seconds=45)
async def check_map_changes():
    global last_known_maps
    try:
        online_servers = {s["info"]["hostname"]: s for s in servers_collection.find({"status": "online"})}
        if not last_known_maps:
            for server_name, server_data in online_servers.items():
                last_known_maps[server_name] = server_data.get("info", {}).get("mapname")
            print("Initial map state has been populated.")
            return

        for server_name, server_data in online_servers.items():
            current_map = server_data.get("info", {}).get("mapname")
            last_map = last_known_maps.get(server_name)
            if current_map and last_map != current_map:
                print(f"MAP CHANGE DETECTED on {server_name}: {last_map} -> {current_map}")
                subs_to_alert = subscriptions_collection.find({
                    "server_name": server_name,
                    "map_name": current_map.lower()
                })
                
                # Get the info object from the correct variable
                server_info_data = server_data.get("info", {})
                player_count = server_info_data.get("num_players", 0)
                
                for sub in subs_to_alert:
                    if player_count > sub.get("players_over", 0):
                        try:
                            user = await bot.fetch_user(sub["user_id"])
                            embed = discord.Embed(
                                title="📢 BF1942 Map Alert!",
                                description=f"The map **{current_map}** has just started on **{server_name}**!",
                                color=discord.Color.gold()
                            )
                            # --- THIS LINE IS NOW FIXED ---
                            embed.add_field(name="Players", value=f"{player_count}/{server_info_data.get('max_players', 0)}")
                            await user.send(embed=embed)
                        except discord.Forbidden:
                            print(f"Could not send DM to user {sub['user_id']}. They may have DMs disabled.")
                        except Exception as e:
                            print(f"An error occurred sending a DM: {e}")

        for server_name, server_data in online_servers.items():
            last_known_maps[server_name] = server_data.get("info", {}).get("mapname")
            
    except Exception as e:
        print(f"Error in background task: {e}")


# --- BOT EVENTS ---
@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    await bot.sync_commands()
    print('Starting background task for map change alerts...')
    check_map_changes.start()

# --- RUN THE BOT ---
bot.run(DISCORD_TOKEN)
