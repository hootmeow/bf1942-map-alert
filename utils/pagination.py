import discord
from discord.ext import commands

class SimplePaginationView(discord.ui.View):
    def __init__(self, items, per_page=10, title="List", timeout=180):
        super().__init__(timeout=timeout)
        self.items = items
        self.per_page = per_page
        self.title = title
        self.current_page = 0
        self.max_pages = (len(items) - 1) // per_page

        # Disable buttons if single page
        if self.max_pages == 0:
            self.children[0].disabled = True # Prev
            self.children[1].disabled = True # Next

        self.update_buttons()

    def create_embed(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        current_items = self.items[start:end]

        embed = discord.Embed(
            title=f"{self.title} (Page {self.current_page + 1}/{self.max_pages + 1})",
            color=discord.Color.blue()
        )
        
        description = ""
        for item in current_items:
            description += str(item) + "\n"
        
        embed.description = description
        return embed

    def update_buttons(self):
        self.children[0].disabled = (self.current_page == 0)
        self.children[1].disabled = (self.current_page == self.max_pages)

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.primary)
    async def previous_callback(self, button, interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.primary)
    async def next_callback(self, button, interaction):
        if self.current_page < self.max_pages:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

class ServerPaginationView(discord.ui.View):
    """
    Specialized view to handle Server objects (dictionaries) specifically 
    because we want fancy fielding, not just a list of strings in description.
    """
    def __init__(self, servers, per_page=10, timeout=180):
        super().__init__(timeout=timeout)
        self.servers = servers
        self.per_page = per_page
        self.current_page = 0
        self.max_pages = (len(servers) - 1) // per_page
        
        if self.max_pages == 0:
            self.children[0].disabled = True
            self.children[1].disabled = True

    def create_embed(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        current_servers = self.servers[start:end]

        embed = discord.Embed(
            title="Live BF1942 Servers",
            description=f"Showing {len(self.servers)} online servers. (Page {self.current_page + 1}/{self.max_pages + 1})",
            color=discord.Color.green()
        )
        
        for server in current_servers:
            players = f"{server['current_player_count']}/{server['current_max_players']}"
            embed.add_field(
                name=f"**{server['current_server_name']}**",
                value=f"🗺️ Map: **{server['current_map']}** | 👥 Players: **{players}**",
                inline=False
            )
        return embed

    def update_buttons(self):
        self.children[0].disabled = (self.current_page == 0)
        self.children[1].disabled = (self.current_page == self.max_pages)

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.primary)
    async def previous_callback(self, button, interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.primary)
    async def next_callback(self, button, interaction):
        if self.current_page < self.max_pages:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
