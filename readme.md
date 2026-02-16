# BF1942 Map Alert Bot

## Overview

A high-performance, asynchronous Discord bot built with `py-cord` and `asyncpg`. It connects to the bf1942.online statistics database (PostgreSQL) and optionally ClickHouse to provide real-time server information, player tracking, leaderboards, player profiles, round result notifications, and map change alerts.

The bot uses a modular architecture with **Cogs**, a dedicated database abstraction layer, and automatic startup migrations.

## Core Features

*   **🏆 Leaderboards:** Top players ranked by V5 score, filterable by time period and server.
*   **📋 Player Profiles:** Lifetime stats, K/D, win rate, top maps, top servers, recent rounds, and personal bests.
*   **🕵️ Player Watchlist:** Get a DM when your friends (or rivals) join a server, with map/players/gametype details.
*   **📡 Live Server Browser:** Browse all active servers with pagination.
*   **🔔 Map Alerts:** Subscribe to be notified when a specific map comes up, now enriched with previous round results.
*   **🔔 Round Result Notifications:** Get notified when a round ends on a server with map, winner, duration, and top 3 players.
*   **📰 Daily Digest:** Automated daily summary of rounds played, active players, top servers, and top players.
*   **📈 Server Trends:** Top players, popular maps, population trends, and peak hours per server.
*   **📊 Global Stats:** Total rounds, unique players, currently active players, and popular maps.
*   **📊 Dynamic Status:** The bot's status updates every minute with real-time player counts.
*   **📜 Detailed Scoreboards:** Live scoreboards with ticket counts and copy-paste friendly IP addresses.
*   **🕒 Do Not Disturb:** Set quiet hours where the bot will hold back notifications.

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
        DND[utils/dnd.py]
        Health
        Pagination[utils/pagination.py]
    end

    Cogs -->|Uses| DB
    Subs -->|Uses| DND
    Watch -->|Uses| DND
    Digest -->|Uses| DND

    DB --> PostgreSQL[(PostgreSQL)]
    DB -.->|Optional| ClickHouse[(ClickHouse)]
```

*   **`bot.py`**: Entry point. Loads extensions, runs migrations, loads blocklist, connects ClickHouse.
*   **`core/database.py`**: Centralized SQL query manager with Postgres and ClickHouse support.
*   **`utils/dnd.py`**: Shared Do Not Disturb check logic.
*   **`utils/health.py`**: Error webhook alerts to a Discord channel.
*   **`utils/pagination.py`**: Paginated embed views.
*   **`cogs/`**:
    *   `servers.py`: Browsing, server info, pagination, server trends.
    *   `subscriptions.py`: Map alerts, round result notifications, DND settings.
    *   `watchlist.py`: Player tracking with enriched alerts.
    *   `stats.py`: Global statistics, player search.
    *   `leaderboard.py`: V5 score leaderboards.
    *   `profile.py`: Player profile lookup.
    *   `digest.py`: Daily activity digest.
    *   `general.py`: Dynamic status presence.

## Requirements

*   Python 3.8+
*   PostgreSQL Database (with BF1942 stats schema)
*   **Optional:** ClickHouse (for playtime estimates, population trends, peak hours)
*   **Libraries**:
    *   `py-cord`
    *   `python-dotenv`
    *   `asyncpg`
    *   `pytz`
    *   `clickhouse-connect`
    *   `aiohttp`

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Environment Variables**:
    Create a `.env` file:
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
    python bot.py
    ```
    All bot-owned tables are created automatically on startup via `run_migrations()`.

## Command Reference

### 🏆 Leaderboards & Profiles
*   **/leaderboard `[period]` `[server]`**: Top 10 players by V5 score. Period: all-time, weekly, or monthly.
*   **/profile `[player]`**: Lifetime stats, K/D ratio, win rate, top maps/servers, recent rounds, personal bests, and estimated playtime.

### 🕵️ Watchlist
*   **/watch `[player]`**: Receive a DM when this player joins any server (includes map, players, gametype).
*   **/unwatch `[player]`**: Stop tracking a player.
*   **/watchlist**: See who you are currently tracking.

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
*   **/subscribe_rounds `[server]`**: Get notified when a round ends (map, winner, duration, top 3).
*   **/unsubscribe_rounds `[server]`**: Stop round result notifications.
*   **/list**: View your active subscriptions.
*   **/unsubscribe**: Remove all subscriptions.
*   **/pause_alerts**: Temporarily pause/unpause all alerts.
*   **/dnd set**: Configure your Do Not Disturb hours.
*   **/dnd view**: View your current DND schedule.
*   **/dnd clear**: Remove your DND schedule.

### 📰 Daily Digest
*   **/digest_subscribe `[channel]`**: Receive a daily summary at midnight UTC.
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
| `user_dnd_rules` | Do Not Disturb schedules |
| `player_watchlist` | Player tracking watchlist |
| `round_result_subscriptions` | Round end notification subscriptions |
| `digest_subscriptions` | Daily digest subscriptions |
| `bot_state` | Persistent bot state (map tracking, watermarks) |
| `bot_blocklist` | Blocked users and guilds |

The bot reads from but does not write to the stats engine tables (`servers`, `rounds`, `round_player_stats`, `players`, `live_server_snapshot`, `live_player_snapshot`).
