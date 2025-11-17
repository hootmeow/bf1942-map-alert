# BF1942 Map Alert Bot

## Overview

This is a high-performance, asynchronous Discord bot built with `py-cord` and `asyncpg`. It connects directly to a live Battlefield 1942 statistics database (PostgreSQL) to provide real-time server information, player tracking, and map change alerts to a Discord community.

The bot is driven by slash commands and features a background task that periodically checks for map changes to send alerts.

## Core Features

* **Map Change Alerts:** Users can subscribe to alerts for a specific map on a server or all map changes on a server.
* **Flexible Alerts:** Alerts can be sent via DM or posted in a designated server channel.
* **Live Server Browser:** Users can browse all online servers, find servers by map or gametype, and find servers that need seeding.
* **Detailed Statistics:** Users can get a deep, live "scoreboard" view of any server, including player lists, scores, and ticket counts.
* **Player Finder:** Users can locate which server a specific player is currently on.
* **Subscription Management:** Users can list, pause, or remove their subscriptions.
* **Public Stats:** A command shows the community's most-subscribed maps and servers.

## Application Structure

The bot's logic is contained in a few key files:

* **`bot.py`**: Main application file. It contains all logic for:
    * Connecting to the PostgreSQL database (`asyncpg.create_pool`).
    * Connecting to Discord (`bot.run`).
    * Defining all slash commands (e.g., `@bot.slash_command`).
    * Defining autocomplete functions (`search_servers`, `search_maps`, etc.).
    * Running the background task (`@tasks.loop`) to check for map changes.

* **`.env`**: Stores configuration secrets (not included in the repository).
    * `DISCORD_TOKEN`: Bot token.
    * `POSTGRES_DSN`: PostgreSQL connection string (e.g., `postgres://user:pass@host:port/db`).

* **`requirements.txt`**: Lists required Python libraries.
    * `py-cord`
    * `python-dotenv`
    * `asyncpg`

## Database Interaction

The bot relies on read-access to the bf1942.online Battlefield 1942 statistics database and write-access to one table of its own. It will not work stand-alone.

## Command Reference

### Subscription Commands

* **`/subscribe`**
    * **Description:** Subscribes you to an alert for a *specific map* on a *specific server*.
    * **Options:** `server`, `map_name`, `players_over` (optional), `channel` (optional).

* **`/subscribe_server`**
    * **Description:** Subscribes you to *all map changes* on a specific server.
    * **Options:** `server`, `players_over` (optional), `channel` (optional).

* **`/list`**
    * **Description:** Shows all of your current subscriptions and their status (paused, channel, DM).

* **`/unsubscribe`**
    * **Description:** Deletes *all* of your active subscriptions.

* **`/pause_alerts`**
    * **Description:** Pauses or unpauses all alerts without deleting them.
    * **Options:** `status` (pause/unpause).

### Server Info Commands

* **`/servers`**
    * **Description:** Shows a live list of all online BF1942 servers, sorted by player count.

* **`/playing`**
    * **Description:** Finds all servers currently playing a specific map.
    * **Options:** `map_name` (autocomplete).

* **`/findgametype`**
    * **Description:** Finds all servers running a specific gametype (e.g., Conquest, CTF).
    * **Options:** `gametype` (autocomplete).

* **`/seed`**
    * **Description:** Finds servers with a low number of players (1–5) that need help starting.

### Player & Stats Commands

* **`/serverinfo`**
    * **Description:** Shows a detailed, live scoreboard for a single server, including teams, tickets, and player stats.
    * **Options:** `server_name` (autocomplete).

* **`/find`**
    * **Description:** Finds which server a specific player is currently on.
    * **Options:** `player_name`.

* **`/alert_stats`**
    * **Description:** Shows the Top 10 most-subscribed maps and servers across the community.
