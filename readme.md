# BF1942 Map Alert Bot

## Overview

This is a high-performance, asynchronous Discord bot built with `py-cord` and `asyncpg`. It connects directly to a live Battlefield 1942 statistics database (PostgreSQL) to provide real-time server information, player tracking, and map change alerts to a Discord community.

The bot uses a modern, modular architecture with **Cogs** and a dedicated database abstraction layer.

## Core Features

*   **🕵️ Player Watchlist:** Get a DM immediately when your friends (or rivals) join a server.
*   **📡 Live Server Browser:** Browse all active servers using pagination.
*   **🔔 Map Alerts:** Subscribe to be notified when a specific map comes up.
*   **📊 Dynamic Status:** The bot's status updates every minute with real-time player counts ("Watching X Players").
*   **📜 Detailed Scoreboards:** View live scoreboards with neat typography, ticket counts, and copy-paste friendly IP addresses.
*   **🕒 Do Not Disturb:** Set quiet hours where the bot will hold back notifications.

## Architecture

The bot has been refactored from a monolithic script into a modular design:

```mermaid
graph TD
    Bot[bot.py] -->|Loads| Cogs
    Bot -->|Connects| DB[core/database.py]
    
    subgraph Cogs ["Command Modules"]
        Servers[cogs/servers.py]
        Subs[cogs/subscriptions.py]
        Stats[cogs/stats.py]
        General[cogs/general.py]
        Watch[cogs/watchlist.py]
    end
    
    Servers -->|Uses| DB
    Subs -->|Uses| DB
    Stats -->|Uses| DB
    General -->|Uses| DB
    Watch -->|Uses| DB
    
    DB --> PostgreSQL[(PostgreSQL)]
```

*   **`bot.py`**: Entry point. Loads extensions and connects to DB.
*   **`core/database.py`**: Centralized SQL query manager.
*   **`cogs/`**:
    *   `servers.py`: Browsing, server info, pagination.
    *   `subscriptions.py`: Map alerts, DND settings.
    *   `watchlist.py`: Player tracking and anti-spam alerts.
    *   `stats.py`: Global statistics.
    *   `general.py`: Dynamic status presence.

## Requirements

*   Python 3.8+
*   PostgreSQL Database (with BF1942 stats schema)
*   **Libraries**:
    *   `py-cord`
    *   `python-dotenv`
    *   `asyncpg`
    *   `pytz`

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
    ```

3.  **Run**:
    ```bash
    python bot.py
    ```

## Command Reference

### 🕵️ Watchlist (New!)
*   **/watch `[player]`**: Receive a DM when this player joins any server. (Includes spam protection).
*   **/unwatch `[player]`**: Stop tracking a player.
*   **/watchlist**: See who you are currently tracking.

### 🖥️ Servers
*   **/servers**: Browse a live list of **all** active servers (supports pagination).
*   **/serverinfo `[server]`**: View a detailed scoreboard, map info, and get a copy-pasteable IP address.
*   **/playing `[map]`**: Find servers playing a specific map.
*   **/seed**: Find servers with low player counts that need help starting.

### 🔔 Alerts & Subscriptions
*   **/subscribe**: Alert for a specific map on a server.
*   **/subscribe_server**: Alert for *any* map change on a server.
*   **/list**: View your active subscriptions.
*   **/dnd set**: Configure your "Do Not Disturb" hours (UTC).

### 📈 Stats
*   **/find `[player]`**: See which server a player is on right now.
*   **/alert_stats**: View global stats on the most popular maps/servers.
