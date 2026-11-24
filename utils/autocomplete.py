"""Shared slash-command autocomplete callbacks."""
import discord

from core.database import Database


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


async def search_players(ctx: discord.AutocompleteContext):
    """Provides player name suggestions."""
    db: Database = ctx.bot.db
    return await db.get_player_suggestions(ctx.value)
