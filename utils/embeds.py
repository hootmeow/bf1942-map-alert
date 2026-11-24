"""Shared pieces for alert embeds: captheflag.com links, server/round details."""
import datetime
import os
from urllib.parse import quote

# `or` so an empty SITE_URL= line in .env still falls back to the default
SITE_URL = (os.getenv("SITE_URL") or "https://captheflag.com").rstrip("/")
GAME_URL = f"{SITE_URL}/bf1942"
FOOTER_TEXT = "captheflag.com"


def server_url(server_id) -> str:
    return f"{GAME_URL}/servers/{server_id}"


def player_url(player_name: str) -> str:
    return f"{GAME_URL}/player/{quote(player_name, safe='')}"


def round_url(round_id) -> str:
    return f"{GAME_URL}/stats/rounds/{round_id}"


def link(text, url) -> str:
    """Markdown link; brackets in the text (clan tags) are escaped so they can't break out."""
    safe = str(text).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
    return f"[{safe}]({url})"


def winner_name(team) -> str:
    return "Axis" if team == 1 else "Allies" if team == 2 else "Draw"


def address(ip, game_port):
    """Copy-pasteable ip:port, or None when either part is unknown."""
    if not ip or not game_port:
        return None
    return f"{ip}:{game_port}"


def discord_time(dt: datetime.datetime, style: str = "t") -> str:
    """Discord timestamp markup; renders in each reader's own timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return f"<t:{int(dt.timestamp())}:{style}>"


def format_clock(seconds) -> str:
    minutes, secs = divmod(int(seconds or 0), 60)
    return f"{minutes}:{secs:02d}"


def add_server_fields(embed, detail, include_players: bool = True):
    """Address, players, gametype/mod, time left and tickets from get_server_details()."""
    if not detail:
        return
    addr = address(detail['ip'], detail['current_game_port'])
    if addr:
        embed.add_field(name="Address", value=f"`{addr}`", inline=True)
    if include_players:
        embed.add_field(name="Players",
                        value=f"{detail['current_player_count']}/{detail['current_max_players']}", inline=True)
    gametype = detail['current_gametype'] or 'N/A'
    mod = detail['unpure_mods']
    embed.add_field(name="Gametype", value=f"{gametype} ({mod})" if mod else gametype, inline=True)
    if detail['round_time_remain']:
        embed.add_field(name="Time Left", value=format_clock(detail['round_time_remain']), inline=True)
    if detail['tickets1'] is not None or detail['tickets2'] is not None:
        t1 = detail['tickets1'] if detail['tickets1'] is not None else '?'
        t2 = detail['tickets2'] if detail['tickets2'] is not None else '?'
        embed.add_field(name="Tickets", value=f"Axis {t1} · Allies {t2}", inline=True)
