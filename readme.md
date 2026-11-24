# BF1942 Map Alert Bot

## Overview

A high-performance, asynchronous Discord bot built with `py-cord` and `asyncpg`. It connects to the [captheflag.com](https://captheflag.com) statistics database (PostgreSQL) and optionally ClickHouse to provide real-time server information, player tracking, leaderboards, player profiles, round result notifications, and map change alerts.

The bot uses a modular architecture with **Cogs**, a dedicated database abstraction layer, and automatic startup migrations.

## Core Features

*   **🏆 Leaderboards:** Top players ranked by V5 score, filterable by time period and server.
*   **📋 Player Profiles:** Lifetime stats, K/D, win rate, top maps, top servers, recent rounds, and personal bests.
*   **🕵️ Player Watchlist:** Get a DM when your friends (or rivals) join a server, with map/players/gametype details.
*   **📡 Live Server Browser:** Browse all active servers with pagination.
*   **🔔 Map Alerts:** Subscribe to be notified when a specific map comes up, enriched with the previous round's result.
*   **🔔 Round Result Notifications:** Get notified when a round ends on a server with map, winner, duration, and per-team scoreboards.
*   **🔌 Server Up/Down Alerts:** Get notified when a server comes online or goes offline (confirmed over two checks, so a single missed query doesn't page you).
*   **📰 Daily Digest:** Automated daily summary of rounds played, active players, top servers, and top players.
*   **📈 Server Trends:** Top players, popular maps, population trends, and peak hours per server.
*   **📊 Global Stats:** Total rounds, unique players, currently active players, and popular maps.
*   **📊 Dynamic Status:** The bot's status updates every minute with real-time server and player counts.
*   **📜 Detailed Scoreboards:** Live scoreboards with ticket counts and copy-paste friendly IP addresses.
*   **🕒 Do Not Disturb:** Set quiet hours in your own timezone where the bot will hold back notifications.

## Architecture

```mermaid
graph TD
    Bot[bot.py] -->|Loads| Cogs
    Bot -->|Connects| DB[core/database.py]
    Bot -->|Error alerts| Health[utils/health.py]

    subgraph Cogs ["Command Modules"]
        Servers[cogs/servers.py]
        Subs[cogs/subscriptions.py]
        Stats[cogs/stats.py]
        General[cogs/general.py]
        Watch[cogs/watchlist.py]
        Leaderboard[cogs/leaderboard.py]
        Profile[cogs/profile.py]
        Digest[cogs/digest.py]
    end

    subgraph Utils ["Shared Utilities"]
        Alerts[utils/alerts.py]
        Autocomplete[utils/autocomplete.py]
        DND[utils/dnd.py]
        Health
        Pagination[utils/pagination.py]
    end

    Cogs -->|Uses| DB
    Cogs -->|Uses| Autocomplete
    Subs -->|Sends via| Alerts
    Watch -->|Sends via| Alerts
    Digest -->|Sends via| Alerts
    Subs -->|Uses| DND
    Watch -->|Uses| DND

    DB --> PostgreSQL[(PostgreSQL)]
    DB -.->|Optional| ClickHouse[(ClickHouse)]
```

*   **`bot.py`**: Entry point. Connects the database, runs migrations, connects ClickHouse and loads the blocklist *before* logging in to Discord, so background tasks always start with a working database. Loads extensions and syncs slash commands.
*   **`core/database.py`**: Centralized SQL query manager with Postgres and ClickHouse support. Caches the map list (10 min) and whole-history aggregates for `/stats` and `/leaderboard` (5 min).
*   **`core/logger.py`**: Console + rotating file logging (`bot.log` in the project root, 5 × 5 MB).
*   **`utils/alerts.py`**: Shared alert sender for channels and DMs. Respects the blocklist, pauses DMs for 24h to users who have them closed, and removes subscriptions for channels that stay unreachable.
*   **`utils/autocomplete.py`**: Shared server / map / gametype / player autocomplete callbacks.
*   **`utils/dnd.py`**: Do Not Disturb check, evaluated in the user's timezone.
*   **`utils/health.py`**: Error webhook alerts to a Discord channel.
*   **`utils/pagination.py`**: Paginated embed views.
*   **`cogs/`**:
    *   `servers.py`: Browsing, server info, pagination, server trends.
    *   `subscriptions.py`: Map alerts, round result notifications, server up/down alerts, DND settings.
    *   `watchlist.py`: Player tracking with enriched alerts, squad view.
    *   `stats.py`: Global statistics, player search.
    *   `leaderboard.py`: V5 score leaderboards.
    *   `profile.py`: Player profile lookup.
    *   `digest.py`: Daily activity digest.
    *   `general.py`: Dynamic status presence.

The bot only requests the `guilds` gateway intent. Slash commands arrive as interactions, and alerts only need the guild/channel cache, so no privileged intents are required.

## Requirements

*   Python 3.12 (production runs 3.12.3)
*   PostgreSQL Database (with the BF1942 stats engine schema)
*   **Optional:** ClickHouse (for playtime estimates, population trends, peak hours)
*   **Libraries** (pinned in `requirements.txt`):
    *   `py-cord` 2.7.2
    *   `python-dotenv` 1.2.2
    *   `asyncpg` 0.31.0
    *   `pytz` 2026.1.post1
    *   `clickhouse-connect` 0.15.1
    *   `aiohttp` 3.13.5

## Setup

1.  **Install Dependencies**:
    ```bash
    python3 -m venv venv
    venv/bin/pip install -r requirements.txt
    ```

2.  **Environment Variables**:
    Create a `.env` file (see `.env.example`):
    ```env
    DISCORD_TOKEN=your_bot_token
    POSTGRES_DSN=postgres://user:pass@host:port/db_name

    # Optional
    CLICKHOUSE_HOST=
    CLICKHOUSE_PORT=8123
    CLICKHOUSE_DB=default
    CLICKHOUSE_USER=default
    CLICKHOUSE_PASSWORD=

    DISCORD_WEBHOOK_URL=
    BLOCKED_USERS=
    BLOCKED_GUILDS=
    ```

3.  **Run**:
    ```bash
    venv/bin/python bot.py
    ```
    All bot-owned tables, columns and indexes are created automatically on startup via `run_migrations()`. If the database can't be reached at startup the bot exits with a non-zero status, so a process manager can retry it.

## Deployment

In production the bot runs as the `bf1942-map-bot` systemd service (`User=bf1942`, `WorkingDirectory=/opt/bf1942-map-bot`, `Restart=on-failure`) from a git checkout of `main`. To deploy:

```bash
sudo -u bf1942 git -C /opt/bf1942-map-bot pull --ff-only
sudo -u bf1942 /opt/bf1942-map-bot/venv/bin/pip install -r /opt/bf1942-map-bot/requirements.txt
sudo systemctl restart bf1942-map-bot
sudo journalctl -u bf1942-map-bot -f    # wait for "Slash commands synced."
```

## Command Reference

### 🏆 Leaderboards & Profiles
*   **/leaderboard `[period]` `[server]`**: Top 10 players by V5 score. Period: all-time, weekly, or monthly.
*   **/profile `[player]`**: Lifetime stats, K/D ratio, win rate, top maps/servers, recent rounds, personal bests, and estimated playtime.

### 🕵️ Watchlist
*   **/watch `[player]`**: Receive a DM when this player joins any server (includes map, players, gametype). Names are exact and case-sensitive; alerts for the same player are limited to one per 15 minutes.
*   **/unwatch `[player]`**: Stop tracking a player.
*   **/watchlist**: See who you are currently tracking.
*   **/squad**: See which players on your watchlist are currently online, grouped by server.

### 🖥️ Servers
*   **/servers**: Browse a live list of all active servers (supports pagination).
*   **/serverinfo `[server]`**: View a detailed scoreboard, map info, and get a copy-pasteable IP address.
*   **/playing `[map]`**: Find servers playing a specific map.
*   **/findgametype `[gametype]`**: Find servers running a specific gametype.
*   **/seed**: Find servers with low player counts that need help starting.
*   **/trends `[server]`**: Top players, popular maps (24h), population trends, and peak hours.

### 🔔 Alerts & Subscriptions
*   **/subscribe `[server]` `[map]`**: Alert for a specific map on a server.
*   **/subscribe_server `[server]`**: Alert for *any* map change on a server.
*   **/subscribe_rounds `[server]`**: Get notified when a round ends (map, winner, duration, per-team scoreboards). Only rounds that end after you subscribe are sent.
*   **/unsubscribe_rounds `[server]`**: Stop round result notifications.
*   **/subscribe_updown `[server]`**: Get an alert when a server goes online or offline.
*   **/unsubscribe_updown `[server]`**: Stop online/offline alerts for a server.
*   **/list**: View your active map subscriptions.
*   **/unsubscribe**: Remove all map subscriptions.
*   **/pause_alerts**: Temporarily pause/unpause all map alerts.
*   **/dnd set `[start_hour]` `[end_hour]` `[days]` `[timezone]`**: Configure your Do Not Disturb hours in your own timezone (handles daylight saving). Overnight windows (e.g. 22–06) belong to the day they start on. Setting the same start and end hour blocks the whole day.
*   **/dnd view**: View your current DND schedule.
*   **/dnd clear**: Remove your DND schedule.

Alerts can be posted to a channel (the bot needs **Send Messages** and **Embed Links** there) or sent by DM. If a channel is deleted or the bot is removed from the server, subscriptions for that channel are removed once it has been unreachable for at least 6 hours.

### 📰 Daily Digest
*   **/digest_subscribe `[channel]`**: Receive a daily summary shortly after midnight UTC (sent once a day, not affected by DND).
*   **/digest_unsubscribe**: Stop receiving digests.

### 📈 Stats
*   **/stats**: Global stats — total rounds, unique players, currently active, popular maps (7 days).
*   **/find `[player]`**: See which server a player is on right now.
*   **/alert_stats**: View the most popular subscribed maps/servers.

## Database Tables

The bot automatically creates and manages these tables on startup:

| Table | Purpose |
|-------|---------|
| `subscriptions` | Map change alert subscriptions |
| `user_dnd_rules` | Do Not Disturb schedules (local hours/days + timezone; legacy UTC columns kept) |
| `player_watchlist` | Player tracking watchlist |
| `round_result_subscriptions` | Round end notification subscriptions (with `created_at`) |
| `server_updown_subscriptions` | Server online/offline alert subscriptions |
| `digest_subscriptions` | Daily digest subscriptions |
| `bot_state` | Persistent bot state: last known maps and server states (time-stamped, ignored on startup if older than 10 minutes), announced round ids, last digest date |
| `bot_blocklist` | Blocked users and guilds |

The bot reads from but does not write to the stats engine tables (`servers`, `rounds`, `round_player_stats`, `players`, `live_server_snapshot`, `live_player_snapshot`).
