import discord
from discord.ext import commands
from discord.commands import Option
import logging

# We will need to import the Database class for type hinting if we want, 
# but mostly we expect bot.db to be set.
from core.database import Database
from utils.validation import sanitize_text, sanitize_for_codeblock

logger = logging.getLogger("bf1942_bot")

async def search_servers(ctx: discord.AutocompleteContext):
    """Provides server name suggestions for autocomplete."""
    db: Database = ctx.bot.db
    return await db.get_server_suggestions(ctx.value)

async def search_maps(ctx: discord.AutocompleteContext):
    """Provides map name suggestions."""
    db: Database = ctx.bot.db
    return await db.get_map_suggestions(ctx.value)

async def search_gametypes(ctx: discord.AutocompleteContext):
    """Provides gametype suggestions."""
    db: Database = ctx.bot.db
    return await db.get_gametype_suggestions(ctx.value)


class ServerCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def db(self) -> Database:
        return self.bot.db

    @commands.slash_command(name="servers", description="See a live list of all active BF1942 servers.")
    async def servers(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        try:
            # Fetch ALL active servers (limit 100 or huge number)
            # Database method default was 25, we'll ask for more
            server_list = await self.db.get_all_active_servers(limit=500)
            
            if not server_list:
                await ctx.followup.send("Could not find any online servers right now.")
                return

            # Use our new Pagination View
            from utils.pagination import ServerPaginationView
            view = ServerPaginationView(server_list, per_page=10)
            await ctx.followup.send(embed=view.create_embed(), view=view)
            
        except Exception as e:
            logger.error(f"Error in /servers: {e}")
            await ctx.followup.send("Something went wrong, I couldn't fetch the server list.", ephemeral=True)

    @commands.slash_command(name="playing", description="Find servers currently playing a specific map.")
    async def playing(
        self,
        ctx: discord.ApplicationContext,
        map_name: Option(str, "Start typing the map name", autocomplete=search_maps)
    ):
        await ctx.defer(ephemeral=True)
        try:
            server_list = await self.db.get_servers_by_map(map_name)
            if not server_list:
                await ctx.followup.send(f"Sorry, no servers are currently playing **{map_name}**.")
                return

            s_map_name = sanitize_text(map_name)
            embed = discord.Embed(title=f"Servers Playing: {s_map_name}", color=discord.Color.orange())
            description = ""
            for server in server_list:
                players = f"{server['current_player_count']}/{server['current_max_players']}"
                s_server_name = sanitize_text(server['current_server_name'])
                description += f"**{s_server_name}** ({players} players)\n"
            embed.description = description
            await ctx.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in /playing: {e}")
            await ctx.followup.send("Something went wrong, I couldn't find servers for that map.", ephemeral=True)

    @commands.slash_command(name="findgametype", description="Find servers running a specific gametype.")
    async def findgametype(
        self,
        ctx: discord.ApplicationContext,
        gametype: Option(str, "Start typing the gametype name", autocomplete=search_gametypes)
    ):
        await ctx.defer(ephemeral=True)
        try:
            server_list = await self.db.get_servers_by_gametype(gametype)
            if not server_list:
                await ctx.followup.send(f"Sorry, no online servers were found running **{gametype}**.")
                return

            embed = discord.Embed(title=f"Servers Playing: {gametype}", color=discord.Color.orange())
            for server in server_list:
                players = f"{server['current_player_count']}/{server['current_max_players']}"
                s_server_name = sanitize_text(server['current_server_name'])
                s_map_name = sanitize_text(server['current_map'])
                embed.add_field(
                    name=f"**{s_server_name}**",
                    value=f"🗺️ Map: **{s_map_name}** | 👥 Players: **{players}**",
                    inline=False
                )
            await ctx.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in /findgametype: {e}")
            await ctx.followup.send("Something went wrong, I couldn't perform the search.", ephemeral=True)

    @commands.slash_command(name="seed", description="Find servers with a low player count to help get a game started.")
    async def seed(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        try:
            server_list = await self.db.get_seed_servers()
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
            logger.error(f"Error in /seed: {e}")
            await ctx.followup.send("Something went wrong, I couldn't find servers to seed.", ephemeral=True)

    @commands.slash_command(name="serverinfo", description="Get detailed live info for a specific server.")
    async def serverinfo(
        self,
        ctx: discord.ApplicationContext,
        server_name: Option(str, "Start typing the server name", autocomplete=search_servers)
    ):
        await ctx.defer(ephemeral=True)
        try:
            server = await self.db.get_server_details(server_name)
            if not server:
                await ctx.followup.send("Could not find that server. It might be offline.")
                return

            # Data Extraction
            hostname = sanitize_text(server['current_server_name'])
            map_name = sanitize_text(server['current_map']) or 'N/A'
            num_players = server['current_player_count']
            max_players = server['current_max_players']
            game_mod = sanitize_text(server['unpure_mods'] or server['current_gametype']) or 'N/A'
            gametype = sanitize_text(server['current_gametype']) or 'N/A'
            ip_address = str(server['ip'])
            game_port = server['current_game_port'] or 'N/A'
            full_address = f"{ip_address}:{game_port}"
            time_remain_sec = int(server['round_time_remain'] or 0)
            minutes, seconds = divmod(time_remain_sec, 60)
            time_remaining_formatted = f"{minutes}:{seconds:02d}"

            # Player Fetching
            all_players = await self.db.get_server_players(server['ip'], server['port'])
            
            team1_players = sorted([p for p in all_players if p['team'] == 1], key=lambda x: x.get('score', 0), reverse=True)
            team2_players = sorted([p for p in all_players if p['team'] == 2], key=lambda x: x.get('score', 0), reverse=True)

            # Embed Creation
            embed = discord.Embed(title=f"**{hostname}**", color=discord.Color.dark_gray())
            
            embed.add_field(name="🗺️ Map", value=f"`{map_name}`", inline=True)
            embed.add_field(name="👥 Players", value=f"`{num_players}/{max_players}`", inline=True)
            embed.add_field(name="🕹️ Mod", value=f"`{game_mod}`", inline=True)
            embed.add_field(name="🚩 Gametype", value=f"`{gametype}`", inline=True)
            embed.add_field(name="⌛ Time Remaining", value=f"`{time_remaining_formatted}`", inline=True)
            # Use inline code block for easy copy-paste without taking up space
            embed.add_field(name="🔌 Address", value=f"`{full_address}`", inline=True)

            # --- Formatting Helper ---
            def format_table(players):
                # Header: Score (7), Kills (7), Deaths (7), Ping (6), Name (Rest)
                # Max name length increased to 25 to prevent truncation
                lines = [f"{'Score':<7}{'Kills':<7}{'Deaths':<7}{'Ping':<6}Player"]
                lines.append("-" * 55) # Extended dash line
                for p in players[:15]: 
                    # Use specialized codeblock sanitization to prevent breakouts while maintaining visual quality
                    name = sanitize_for_codeblock(p['player_name'] or 'Unknown')
                    # Truncate slightly longer name if needed (now 25 chars)
                    lines.append(f"{p['score'] or 0:<7}{p['kills'] or 0:<7}{p['deaths'] or 0:<7}{p['ping'] or 0:<6}{name[:25]}")
                return "```\n" + "\n".join(lines) + "\n```"

            # Team 1
            tickets1 = server['tickets1'] or 'N/A'
            team1_header = f"Axis (Team 1) - Tickets: {tickets1}"
            team1_body = "No players on this team." if not team1_players else format_table(team1_players)
            embed.add_field(name=team1_header, value=team1_body, inline=False)
            
            # Team 2
            tickets2 = server['tickets2'] or 'N/A'
            team2_header = f"Allies (Team 2) - Tickets: {tickets2}"
            team2_body = "No players on this team." if not team2_players else format_table(team2_players)
            embed.add_field(name=team2_header, value=team2_body, inline=False)

            await ctx.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in /serverinfo: {e}")
            await ctx.followup.send("Something went wrong, I couldn't fetch that server's info.", ephemeral=True)

def setup(bot):
    bot.add_cog(ServerCommands(bot))
