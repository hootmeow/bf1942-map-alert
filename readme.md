\# BF1942 Map Alert Bot



\## Overview



This is a high-performance, asynchronous Discord bot built with `py-cord` and `asyncpg`. It connects directly to a live Battlefield 1942 statistics database (PostgreSQL) to provide real-time server information, player tracking, and map change alerts to a Discord community.



The bot is driven by slash commands and features a background task that periodically checks for map changes to send alerts.



\## Core Features



\* \*\*Map Change Alerts:\*\* Users can subscribe to alerts for a specific map on a server or all map changes on a server.

\* \*\*Flexible Alerts:\*\* Alerts can be sent via DM or posted in a designated server channel.

\* \*\*Live Server Browser:\*\* Users can browse all online servers, find servers by map or gametype, and find servers that need seeding.

\* \*\*Detailed Statistics:\*\* Users can get a deep, live "scoreboard" view of any server, including player lists, scores, and ticket counts.

\* \*\*Player Finder:\*\* Users can locate which server a specific player is currently on.

\* \*\*Subscription Management:\*\* Users can list, pause, or remove their subscriptions.

\* \*\*Public Stats:\*\* A command shows the community's most-subscribed maps and servers.



\## Application Structure



The bot's logic is contained in a few key files:



\* \*\*`bot.py`\*\*: This is the main application file. It contains all logic for:

&nbsp;   \* Connecting to the PostgreSQL database (`asyncpg.create\_pool`).

&nbsp;   \* Connecting to Discord (`bot.run`).

&nbsp;   \* Defining all slash commands (e.g., `@bot.slash\_command`).

&nbsp;   \* Defining all autocomplete functions (`search\_servers`, `search\_maps`, etc.).

&nbsp;   \* Running the background task (`@tasks.loop`) to check for map changes.

\* \*\*`.env`\*\*: This file (which is not in the repository) stores the configuration secrets.

&nbsp;   \* `DISCORD\_TOKEN`: The bot's Discord token.

&nbsp;   \* `POSTGRES\_DSN`: The full connection string for the PostgreSQL database (e.g., `postgres://user:pass@host:port/db`).

\* \*\*`requirements.txt`\*\*: Lists the required Python libraries.

&nbsp;   \* `py-cord`: The Discord API library.

&nbsp;   \* `python-dotenv`: For loading the `.env` file.

&nbsp;   \* `asyncpg`: The asynchronous PostgreSQL driver.



\## Database Interaction



The bot relies on read-access to a live game statistics database and write-access to one table of its own.



\### Bot-Owned Table



The bot's \*only\* write-access requirement is for the `subscriptions` table.



\* \*\*`subscriptions`\*\*:

&nbsp;   \* \*\*Purpose:\*\* Stores all user alerts.

&nbsp;   \* \*\*Key Columns:\*\*

&nbsp;       \* `user\_id` (BIGINT): The Discord ID of the user.

&nbsp;       \* `server\_name` (VARCHAR): The name of the server to watch.

&nbsp;       \* `map\_name` (VARCHAR): The name of the map to watch. A special value of `\*all\*` is used for `/subscribe\_server` alerts.

&nbsp;       \* `channel\_id` (BIGINT): If `NULL`, the alert is a DM. If it has an ID, the alert is posted to that channel.

&nbsp;       \* `is\_paused` (BOOLEAN): If `true`, the user will not receive alerts for this subscription.



\### External (Read-Only) Tables



The bot reads from the following tables to get its live game data:



\* \*\*`servers`\*\*: The main table for server status. Used to find servers that are `ACTIVE` or `EMPTY`. Provides `current\_server\_name`, `current\_map`, `current\_player\_count`, `current\_gametype`, etc.

\* \*\*`live\_server\_snapshot`\*\*: A detailed snapshot of live server data, including `tickets1`, `tickets2`, `unpure\_mods`, and `round\_time\_remain`.

\* \*\*`live\_player\_snapshot`\*\*: A detailed snapshot of all players currently online, including `player\_name`, `score`, `kills`, `deaths`, `ping`, and `team`.

\* \*\*`rounds`\*\*: A historical log of all completed rounds. Used by the `/search\_maps` autocomplete to get a list of all map names.



\## Command Reference



\### Subscription Commands



\* \*\*`/subscribe`\*\*

&nbsp;   \* \*\*Description:\*\* Subscribes you to an alert for a \*specific map\* on a \*specific server\*.

&nbsp;   \* \*\*Options:\*\* `server`, `map\_name`, `players\_over` (optional), `channel` (optional).

\* \*\*`/subscribe\_server`\*\*

&nbsp;   \* \*\*Description:\*\* Subscribes you to alerts for \*any map change\* on a \*specific server\*.

&nbsp;   \* \*\*Options:\*\* `server`, `players\_over` (optional), `channel` (optional).

\* \*\*`/list`\*\*

&nbsp;   \* \*\*Description:\*\* Shows all of your current map and server subscriptions and their status (paused, channel, DM).

\* \*\*`/unsubscribe`\*\*

&nbsp;   \* \*\*Description:\*\* Deletes \*all\* of your active subscriptions.

\* \*\*`/pause\_alerts`\*\*

&nbsp;   \* \*\*Description:\*\* Pauses or unpauses all of your alerts without deleting them.

&nbsp;   \* \*\*Options:\*\* `status` (pause/unpause).



\### Server Info Commands



\* \*\*`/servers`\*\*

&nbsp;   \* \*\*Description:\*\* Shows a live list of all online BF1942 servers, sorted by player count.

\* \*\*`/playing`\*\*

&nbsp;   \* \*\*Description:\*\* Finds all servers currently playing a specific map.

&nbsp;   \* \*\*Options:\*\* `map\_name` (with autocomplete).

\* \*\*`/findgametype`\*\*

&nbsp;   \* \*\*Description:\*\* Finds all servers currently running a specific gametype (e.g., Conquest, CTF).

&nbsp;   \* \*\*Options:\*\* `gametype` (with autocomplete).

\* \*\*`/seed`\*\*

&nbsp;   \* \*\*Description:\*\* Finds servers with a small number of players (1-5) that need help starting.



\### Player \& Stats Commands



\* \*\*`/serverinfo`\*\*

&nbsp;   \* \*\*Description:\*\* Shows a detailed, live scoreboard for a single server, including teams, tickets, and player stats.

&nbsp;   \* \*\*Options:\*\* `server\_name` (with autocomplete).

\* \*\*`/find`\*\*

&nbsp;   \* \*\*Description:\*\* Finds which server a specific player is currently on.

&nbsp;   \* \*\*Options:\*\* `player\_name`.

\* \*\*`/alert\_stats`\*\*

&nbsp;   \* \*\*Description:\*\* A public command to see the Top 10 most-subscribed-to maps and servers by the bot's users.

