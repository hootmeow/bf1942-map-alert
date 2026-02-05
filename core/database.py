import asyncpg
import logging
from typing import List, Optional, Dict, Any, Union

logger = logging.getLogger("bf1942_bot")

class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Creates the database connection pool."""
        try:
            self.pool = await asyncpg.create_pool(self.dsn)
            logger.info("Database connection pool created.")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise e

    async def close(self):
        """Closes the database connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed.")

    async def execute(self, query: str, *args) -> str:
        """Executes a query and returns the status string."""
        if not self.pool:
            raise RuntimeError("Database not connected")
        return await self.pool.execute(query, *args)

    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """Fetches multiple rows."""
        if not self.pool:
            raise RuntimeError("Database not connected")
        return await self.pool.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetches a single row."""
        if not self.pool:
            raise RuntimeError("Database not connected")
        return await self.pool.fetchrow(query, *args)

    def _sanitize_like(self, query: str) -> str:
        """Escapes SQL LIKE wildcards and the escape character itself."""
        return query.replace('!', '!!').replace('%', '!%').replace('_', '!_')

    # --- Autocomplete Queries ---

    async def get_server_suggestions(self, query: str) -> List[str]:
        sql = """
        SELECT s.current_server_name
        FROM servers s
        WHERE s.current_server_name ILIKE $1 ESCAPE '!'
          AND s.current_state IN ('ACTIVE', 'EMPTY')
        ORDER BY s.current_player_count DESC
        LIMIT 25;
        """
        rows = await self.fetch(sql, f"{self._sanitize_like(query)}%")
        return [row['current_server_name'] for row in rows]

    async def get_map_suggestions(self, query: str) -> List[str]:
        sql = "SELECT DISTINCT map_name FROM rounds WHERE map_name ILIKE $1 ESCAPE '!' LIMIT 25"
        rows = await self.fetch(sql, f"{self._sanitize_like(query)}%")
        return [row['map_name'] for row in rows]

    async def get_gametype_suggestions(self, query: str) -> List[str]:
        sql = """
        SELECT DISTINCT current_gametype AS name
        FROM servers
        WHERE current_state <> 'OFFLINE' AND current_gametype IS NOT NULL AND current_gametype ILIKE $1 ESCAPE '!'
        ORDER BY name
        LIMIT 25;
        """
        rows = await self.fetch(sql, f"{self._sanitize_like(query)}%")
        return [row['name'] for row in rows if row['name']]

    # --- Server Info Queries ---

    async def get_all_active_servers(self, limit: int = 25) -> List[asyncpg.Record]:
        sql = """
        SELECT current_server_name, current_map, current_player_count, current_max_players
        FROM servers
        WHERE current_state IN ('ACTIVE', 'EMPTY')
        ORDER BY current_player_count DESC
        LIMIT $1;
        """
        return await self.fetch(sql, limit)

    async def get_servers_by_map(self, map_name: str) -> List[asyncpg.Record]:
        sql = """
        SELECT current_server_name, current_player_count, current_max_players
        FROM servers
        WHERE current_state IN ('ACTIVE', 'EMPTY') AND current_map ILIKE $1 ESCAPE '!'
        ORDER BY current_player_count DESC;
        """
        return await self.fetch(sql, self._sanitize_like(map_name))

    async def get_servers_by_gametype(self, gametype: str) -> List[asyncpg.Record]:
        sql = """
        SELECT current_server_name, current_map, current_player_count, current_max_players
        FROM servers
        WHERE current_state IN ('ACTIVE', 'EMPTY') AND current_gametype ILIKE $1 ESCAPE '!'
        ORDER BY current_player_count DESC
        LIMIT 25;
        """
        return await self.fetch(sql, self._sanitize_like(gametype))

    async def get_seed_servers(self) -> List[asyncpg.Record]:
        sql = """
        SELECT current_server_name, current_map, current_player_count, current_max_players
        FROM servers
        WHERE current_state = 'ACTIVE' AND current_player_count > 0 AND current_player_count < 6
        ORDER BY current_player_count ASC
        LIMIT 25;
        """
        return await self.fetch(sql)

    async def get_server_details(self, server_name: str) -> Optional[asyncpg.Record]:
        sql = """
        SELECT
            s.ip, s.port, s.current_server_name, s.current_map, s.current_player_count, s.current_max_players,
            s.current_gametype, s.current_game_port,
            lss.round_time_remain, lss.tickets1, lss.tickets2, lss.unpure_mods
        FROM servers s
        LEFT JOIN live_server_snapshot lss ON s.ip = lss.server_ip AND s.port = lss.server_port
        WHERE s.current_server_name = $1 AND s.current_state IN ('ACTIVE', 'EMPTY');
        """
        return await self.fetchrow(sql, server_name)

    async def get_server_players(self, ip: str, port: int) -> List[asyncpg.Record]:
        sql = """
        SELECT player_name, score, kills, deaths, ping, team
        FROM live_player_snapshot
        WHERE server_ip = $1 AND server_port = $2;
        """
        return await self.fetch(sql, ip, port)

    async def find_player(self, player_name: str) -> Optional[asyncpg.Record]:
        sql = """
        SELECT s.current_server_name, lps.score, lps.kills, lps.deaths
        FROM live_player_snapshot lps
        JOIN servers s ON lps.server_ip = s.ip AND lps.server_port = s.port
        WHERE lps.player_name = $1 AND s.current_state = 'ACTIVE';
        """
        # Note: Added fetchrow since the original code expects one result or handles it as such (though fetch would return list)
        # Original code used fetchrow.
        return await self.fetchrow(sql, player_name)

    # --- Subscription Queries ---

    async def upsert_subscription(self, user_id: int, server: str, map_name: str, players_over: int, guild_id: int, channel_id: Optional[int]):
        sql = """
        INSERT INTO subscriptions (user_id, server_name, map_name, players_over, guild_id, channel_id, is_paused)
        VALUES ($1, $2, $3, $4, $5, $6, false)
        ON CONFLICT (user_id, server_name, map_name)
        DO UPDATE SET
            players_over = EXCLUDED.players_over,
            guild_id = EXCLUDED.guild_id,
            channel_id = EXCLUDED.channel_id,
            is_paused = false;
        """
        await self.execute(sql, user_id, server, map_name, players_over, guild_id, channel_id)

    async def get_user_subscriptions(self, user_id: int) -> List[asyncpg.Record]:
        sql = "SELECT server_name, map_name, players_over, channel_id, is_paused FROM subscriptions WHERE user_id = $1"
        return await self.fetch(sql, user_id)

    async def delete_all_subscriptions(self, user_id: int) -> int:
        sql = "DELETE FROM subscriptions WHERE user_id = $1"
        status = await self.execute(sql, user_id)
        return int(status.split(' ')[1])

    async def set_subscription_paused(self, user_id: int, is_paused: bool) -> int:
        sql = "UPDATE subscriptions SET is_paused = $1 WHERE user_id = $2"
        status = await self.execute(sql, is_paused, user_id)
        return int(status.split(' ')[1])

    # --- DND Queries ---

    async def upsert_dnd_rule(self, user_id: int, start_hour: int, end_hour: int, weekdays: List[int], timezone: str):
        sql = """
        INSERT INTO user_dnd_rules (user_id, start_hour_utc, end_hour_utc, weekdays_utc, timezone)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id) DO UPDATE SET
            start_hour_utc = EXCLUDED.start_hour_utc,
            end_hour_utc = EXCLUDED.end_hour_utc,
            weekdays_utc = EXCLUDED.weekdays_utc,
            timezone = EXCLUDED.timezone;
        """
        await self.execute(sql, user_id, start_hour, end_hour, weekdays, timezone)

    async def get_dnd_rule(self, user_id: int) -> Optional[asyncpg.Record]:
        sql = "SELECT * FROM user_dnd_rules WHERE user_id = $1"
        return await self.fetchrow(sql, user_id)

    async def delete_dnd_rule(self, user_id: int) -> int:
        sql = "DELETE FROM user_dnd_rules WHERE user_id = $1"
        status = await self.execute(sql, user_id)
        return int(status.split(' ')[1])

    # --- Stats Queries ---

    async def get_top_map_subs(self, limit: int = 10, exclude_map: str = "*all*") -> List[asyncpg.Record]:
        sql = """
        SELECT map_name, COUNT(*) as count
        FROM subscriptions
        WHERE map_name <> $1
        GROUP BY map_name
        ORDER BY count DESC
        LIMIT $2;
        """
        return await self.fetch(sql, exclude_map, limit)

    async def get_top_server_subs(self, limit: int = 10) -> List[asyncpg.Record]:
        sql = """
        SELECT server_name, COUNT(*) as count
        FROM subscriptions
        GROUP BY server_name
        ORDER BY count DESC
        LIMIT $1;
        """
        return await self.fetch(sql, limit)

    # --- Background Task Queries ---
    
    # get_all_active_servers is used here too

    async def get_matching_subscriptions(self, server_name: str, map_name: str, server_sub_map_name: str) -> List[asyncpg.Record]:
        sql = """
        SELECT 
            s.user_id, s.players_over, s.channel_id, s.map_name, s.guild_id,
            dnd.start_hour_utc, dnd.end_hour_utc, dnd.weekdays_utc
        FROM subscriptions s
        LEFT JOIN user_dnd_rules dnd ON s.user_id = dnd.user_id
        WHERE 
            s.server_name = $1
            AND s.is_paused = false
            AND (s.map_name = $2 OR s.map_name = $3);
        """
        return await self.fetch(sql, server_name, map_name, server_sub_map_name)

    # --- Watchlist Queries ---

    async def add_watchlist(self, user_id: int, player_name: str):
        """Adds a player to the user's watchlist."""
        # Using a new table 'player_watchlist'
        # We need to ensure this table exists. 
        # For this exercise, I will assume we can create it or it exists.
        # IF IT DOES NOT EXIST, THIS WILL FAIL. 
        # Ideally, we should have a schema migration. 
        # I will create a method to init the table just in case.
        sql = """
        INSERT INTO player_watchlist (user_id, player_name)
        VALUES ($1, $2)
        ON CONFLICT (user_id, player_name) DO NOTHING;
        """
        await self.execute(sql, user_id, player_name)

    async def remove_watchlist(self, user_id: int, player_name: str) -> int:
        sql = "DELETE FROM player_watchlist WHERE user_id = $1 AND player_name = $2"
        status = await self.execute(sql, user_id, player_name)
        return int(status.split(' ')[1])

    async def get_user_watchlist(self, user_id: int) -> List[asyncpg.Record]:
        sql = "SELECT player_name FROM player_watchlist WHERE user_id = $1"
        return await self.fetch(sql, user_id)

    async def get_watchlist_subscribers(self, player_names: List[str]) -> List[asyncpg.Record]:
        """Finds users watching any of the given players."""
        sql = """
        SELECT 
            w.user_id, w.player_name,
            dnd.start_hour_utc, dnd.end_hour_utc, dnd.weekdays_utc
        FROM player_watchlist w
        LEFT JOIN user_dnd_rules dnd ON w.user_id = dnd.user_id
        WHERE w.player_name = ANY($1::text[]);
        """
        return await self.fetch(sql, player_names)
    
    async def get_all_online_players(self) -> List[asyncpg.Record]:
        """Fetches every player currently online across all active servers."""
        sql = """
        SELECT lps.player_name, s.current_server_name
        FROM live_player_snapshot lps
        JOIN servers s ON lps.server_ip = s.ip AND lps.server_port = s.port
        WHERE s.current_state = 'ACTIVE';
        """
        return await self.fetch(sql)
    
    async def init_watchlist_table(self):
        """Creates the watchlist table if it doesn't exist."""
        sql = """
        CREATE TABLE IF NOT EXISTS player_watchlist (
            user_id BIGINT,
            player_name TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            PRIMARY KEY (user_id, player_name)
        );
        """
        await self.execute(sql)


