import asyncpg
import json
import logging
import os
from typing import List, Optional, Dict, Any, Union

logger = logging.getLogger("bf1942_bot")


class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: Optional[asyncpg.Pool] = None
        self.ch_client = None

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

    # --- Startup Migrations ---

    async def run_migrations(self):
        """Creates all bot-owned tables if they don't exist."""
        statements = [
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id BIGINT NOT NULL,
                server_name TEXT NOT NULL,
                map_name TEXT NOT NULL,
                players_over INT DEFAULT 0,
                guild_id BIGINT,
                channel_id BIGINT,
                is_paused BOOLEAN DEFAULT false,
                PRIMARY KEY (user_id, server_name, map_name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_dnd_rules (
                user_id BIGINT PRIMARY KEY,
                start_hour_utc INT NOT NULL,
                end_hour_utc INT NOT NULL,
                weekdays_utc INT[] NOT NULL,
                timezone TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS player_watchlist (
                user_id BIGINT,
                player_name TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                PRIMARY KEY (user_id, player_name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS round_result_subscriptions (
                user_id BIGINT NOT NULL,
                server_name TEXT NOT NULL,
                guild_id BIGINT,
                channel_id BIGINT,
                PRIMARY KEY (user_id, server_name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS digest_subscriptions (
                user_id BIGINT PRIMARY KEY,
                guild_id BIGINT,
                channel_id BIGINT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value JSONB NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS bot_blocklist (
                id SERIAL PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id BIGINT NOT NULL UNIQUE,
                reason TEXT
            )
            """,
        ]
        for sql in statements:
            await self.execute(sql)
        logger.info("Bot migrations complete.")

    # --- ClickHouse Integration ---

    def connect_clickhouse(self):
        """Connect to ClickHouse if configured. Graceful no-op otherwise."""
        ch_host = os.getenv("CLICKHOUSE_HOST")
        ch_port = os.getenv("CLICKHOUSE_PORT", "8123")
        ch_db = os.getenv("CLICKHOUSE_DB", "default")
        ch_user = os.getenv("CLICKHOUSE_USER", "default")
        ch_password = os.getenv("CLICKHOUSE_PASSWORD", "")
        if not ch_host:
            logger.info("ClickHouse not configured, skipping.")
            return
        try:
            import clickhouse_connect
            self.ch_client = clickhouse_connect.get_client(
                host=ch_host, port=int(ch_port), database=ch_db,
                username=ch_user, password=ch_password
            )
            logger.info("ClickHouse client connected.")
        except Exception as e:
            logger.warning(f"Failed to connect to ClickHouse: {e}")

    def ch_query(self, query: str, parameters=None) -> List[Dict[str, Any]]:
        """Run a ClickHouse query and return a list of dicts. Returns [] if not connected."""
        if not self.ch_client:
            return []
        result = self.ch_client.query(query, parameters=parameters)
        columns = result.column_names
        return [dict(zip(columns, row)) for row in result.result_rows]

    # --- Bot State ---

    async def get_bot_state(self, key: str) -> Any:
        row = await self.fetchrow("SELECT value FROM bot_state WHERE key = $1", key)
        if row:
            return json.loads(row['value'])
        return None

    async def set_bot_state(self, key: str, value: Any):
        val = json.dumps(value)
        await self.execute(
            """
            INSERT INTO bot_state (key, value) VALUES ($1, $2::jsonb)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            key, val
        )

    # --- Blocklist ---

    async def get_blocklist(self) -> Dict[str, List[int]]:
        """Returns {'users': [...], 'guilds': [...]} from bot_blocklist table."""
        rows = await self.fetch("SELECT entity_type, entity_id FROM bot_blocklist")
        result: Dict[str, List[int]] = {'users': [], 'guilds': []}
        for row in rows:
            if row['entity_type'] == 'user':
                result['users'].append(row['entity_id'])
            elif row['entity_type'] == 'guild':
                result['guilds'].append(row['entity_id'])
        return result

    # --- Autocomplete Queries ---

    async def get_server_suggestions(self, query: str) -> List[str]:
        sql = """
        SELECT s.current_server_name
        FROM servers s
        WHERE s.current_server_name ILIKE $1
          AND s.current_state IN ('ACTIVE', 'EMPTY')
        ORDER BY s.current_player_count DESC
        LIMIT 25;
        """
        rows = await self.fetch(sql, f"{query}%")
        return [row['current_server_name'] for row in rows]

    async def get_map_suggestions(self, query: str) -> List[str]:
        sql = "SELECT DISTINCT map_name FROM rounds WHERE map_name ILIKE $1 LIMIT 25"
        rows = await self.fetch(sql, f"{query}%")
        return [row['map_name'] for row in rows]

    async def get_gametype_suggestions(self, query: str) -> List[str]:
        sql = """
        SELECT DISTINCT current_gametype AS name
        FROM servers
        WHERE current_state <> 'OFFLINE' AND current_gametype IS NOT NULL AND current_gametype ILIKE $1
        ORDER BY name
        LIMIT 25;
        """
        rows = await self.fetch(sql, f"{query}%")
        return [row['name'] for row in rows if row['name']]

    async def get_player_suggestions(self, query: str) -> List[str]:
        sql = """
        SELECT DISTINCT p.canonical_name AS player_name
        FROM round_player_stats rps
        JOIN players p ON rps.player_id = p.player_id
        WHERE p.canonical_name ILIKE $1
        ORDER BY p.canonical_name
        LIMIT 25;
        """
        rows = await self.fetch(sql, f"{query}%")
        return [row['player_name'] for row in rows]

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
        WHERE current_state IN ('ACTIVE', 'EMPTY') AND current_map ILIKE $1
        ORDER BY current_player_count DESC;
        """
        return await self.fetch(sql, map_name)

    async def get_servers_by_gametype(self, gametype: str) -> List[asyncpg.Record]:
        sql = """
        SELECT current_server_name, current_map, current_player_count, current_max_players
        FROM servers
        WHERE current_state IN ('ACTIVE', 'EMPTY') AND current_gametype ILIKE $1
        ORDER BY current_player_count DESC
        LIMIT 25;
        """
        return await self.fetch(sql, gametype)

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

    # --- Global Stats Queries ---

    async def get_global_stats(self) -> Optional[asyncpg.Record]:
        sql = """
        SELECT
            (SELECT COUNT(*) FROM rounds) AS total_rounds,
            (SELECT COUNT(DISTINCT player_id) FROM round_player_stats) AS unique_players
        """
        return await self.fetchrow(sql)

    async def get_active_player_count(self) -> int:
        sql = """
        SELECT COUNT(DISTINCT lps.player_name)
        FROM live_player_snapshot lps
        JOIN servers s ON lps.server_ip = s.ip AND lps.server_port = s.port
        WHERE s.current_state = 'ACTIVE'
        """
        row = await self.fetchrow(sql)
        return row[0] if row else 0

    async def get_popular_maps_last_7_days(self, limit: int = 10) -> List[asyncpg.Record]:
        sql = """
        SELECT map_name, COUNT(*) AS play_count
        FROM rounds
        WHERE start_time >= NOW() - INTERVAL '7 days'
        GROUP BY map_name
        ORDER BY play_count DESC
        LIMIT $1
        """
        return await self.fetch(sql, limit)

    # --- Background Task Queries ---

    async def get_matching_subscriptions(self, server_name: str, map_name: str, server_sub_map_name: str) -> List[asyncpg.Record]:
        sql = """
        SELECT
            s.user_id, s.players_over, s.channel_id, s.map_name,
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
        sql = """
        SELECT lps.player_name, s.current_server_name
        FROM live_player_snapshot lps
        JOIN servers s ON lps.server_ip = s.ip AND lps.server_port = s.port
        WHERE s.current_state = 'ACTIVE';
        """
        return await self.fetch(sql)

    # --- Round Result Queries ---

    async def upsert_round_result_subscription(self, user_id: int, server_name: str, guild_id: int, channel_id: Optional[int]):
        sql = """
        INSERT INTO round_result_subscriptions (user_id, server_name, guild_id, channel_id)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, server_name)
        DO UPDATE SET guild_id = EXCLUDED.guild_id, channel_id = EXCLUDED.channel_id;
        """
        await self.execute(sql, user_id, server_name, guild_id, channel_id)

    async def delete_round_result_subscription(self, user_id: int, server_name: str) -> int:
        sql = "DELETE FROM round_result_subscriptions WHERE user_id = $1 AND server_name = $2"
        status = await self.execute(sql, user_id, server_name)
        return int(status.split(' ')[1])

    async def get_new_completed_rounds(self, last_round_id: int) -> List[asyncpg.Record]:
        sql = """
        SELECT r.round_id AS id, sv.current_server_name AS server_name,
               r.map_name, r.winner_team AS winning_team, r.duration_seconds,
               r.start_time, r.end_time
        FROM rounds r
        JOIN servers sv ON r.server_id = sv.server_id
        WHERE r.round_id > $1 AND r.end_time IS NOT NULL
        ORDER BY r.round_id ASC
        """
        return await self.fetch(sql, last_round_id)

    async def get_round_top_players(self, round_id: int, limit: int = 3) -> List[asyncpg.Record]:
        sql = """
        SELECT p.canonical_name AS player_name,
               rps.final_score AS score, rps.final_kills AS kills,
               rps.final_deaths AS deaths, rps.team
        FROM round_player_stats rps
        JOIN players p ON rps.player_id = p.player_id
        WHERE rps.round_id = $1
        ORDER BY rps.final_score DESC
        LIMIT $2
        """
        return await self.fetch(sql, round_id, limit)

    async def get_round_result_subscribers(self, server_name: str) -> List[asyncpg.Record]:
        sql = """
        SELECT rrs.user_id, rrs.channel_id,
               dnd.start_hour_utc, dnd.end_hour_utc, dnd.weekdays_utc
        FROM round_result_subscriptions rrs
        LEFT JOIN user_dnd_rules dnd ON rrs.user_id = dnd.user_id
        WHERE rrs.server_name = $1
        """
        return await self.fetch(sql, server_name)

    async def get_last_round_for_server(self, server_name: str) -> Optional[asyncpg.Record]:
        sql = """
        SELECT r.round_id AS id, r.map_name,
               r.winner_team AS winning_team, r.duration_seconds
        FROM rounds r
        JOIN servers sv ON r.server_id = sv.server_id
        WHERE sv.current_server_name = $1 AND r.end_time IS NOT NULL
        ORDER BY r.end_time DESC
        LIMIT 1
        """
        return await self.fetchrow(sql, server_name)

    # --- Leaderboard Queries ---

    async def get_leaderboard(self, period: str, server_name: Optional[str] = None, limit: int = 10) -> List[asyncpg.Record]:
        """Top players by V5 score: (score*20) - (kills*10) + (rounds*100). Excludes coop and flagged."""
        time_filter = ""
        if period == "weekly":
            time_filter = "AND r.start_time >= NOW() - INTERVAL '7 days'"
        elif period == "monthly":
            time_filter = "AND r.start_time >= NOW() - INTERVAL '30 days'"

        server_filter = ""
        params = []
        param_idx = 1
        if server_name:
            server_filter = f"AND sv.current_server_name = ${param_idx}"
            params.append(server_name)
            param_idx += 1

        sql = f"""
        SELECT
            p.canonical_name AS player_name,
            SUM(rps.final_score) * 20 - SUM(rps.final_kills) * 10 + COUNT(DISTINCT rps.round_id) * 100 AS v5_score,
            SUM(rps.final_score) AS total_score,
            SUM(rps.final_kills) AS total_kills,
            SUM(rps.final_deaths) AS total_deaths,
            COUNT(DISTINCT rps.round_id) AS rounds_played
        FROM round_player_stats rps
        JOIN rounds r ON rps.round_id = r.round_id
        JOIN players p ON rps.player_id = p.player_id
        JOIN servers sv ON r.server_id = sv.server_id
        WHERE r.gamemode NOT ILIKE '%coop%'
            AND p.is_flagged = false
            {time_filter}
            {server_filter}
        GROUP BY p.canonical_name
        ORDER BY v5_score DESC
        LIMIT ${param_idx}
        """
        params.append(limit)
        return await self.fetch(sql, *params)

    # --- Player Profile Queries ---

    async def get_player_lifetime_stats(self, player_name: str) -> Optional[asyncpg.Record]:
        sql = """
        SELECT
            p.canonical_name AS player_name,
            SUM(rps.final_score) AS total_score,
            SUM(rps.final_kills) AS total_kills,
            SUM(rps.final_deaths) AS total_deaths,
            COUNT(DISTINCT rps.round_id) AS rounds_played,
            SUM(CASE WHEN rps.team = r.winner_team THEN 1 ELSE 0 END) AS wins
        FROM round_player_stats rps
        JOIN rounds r ON rps.round_id = r.round_id
        JOIN players p ON rps.player_id = p.player_id
        WHERE p.canonical_name = $1
        GROUP BY p.canonical_name
        """
        return await self.fetchrow(sql, player_name)

    async def get_player_top_maps(self, player_name: str, limit: int = 5) -> List[asyncpg.Record]:
        sql = """
        SELECT r.map_name, COUNT(*) AS play_count, SUM(rps.final_score) AS total_score
        FROM round_player_stats rps
        JOIN rounds r ON rps.round_id = r.round_id
        JOIN players p ON rps.player_id = p.player_id
        WHERE p.canonical_name = $1
        GROUP BY r.map_name
        ORDER BY play_count DESC
        LIMIT $2
        """
        return await self.fetch(sql, player_name, limit)

    async def get_player_top_servers(self, player_name: str, limit: int = 5) -> List[asyncpg.Record]:
        sql = """
        SELECT sv.current_server_name AS server_name, COUNT(*) AS play_count
        FROM round_player_stats rps
        JOIN rounds r ON rps.round_id = r.round_id
        JOIN players p ON rps.player_id = p.player_id
        JOIN servers sv ON r.server_id = sv.server_id
        WHERE p.canonical_name = $1
        GROUP BY sv.current_server_name
        ORDER BY play_count DESC
        LIMIT $2
        """
        return await self.fetch(sql, player_name, limit)

    async def get_player_recent_rounds(self, player_name: str, limit: int = 5) -> List[asyncpg.Record]:
        sql = """
        SELECT r.map_name, sv.current_server_name AS server_name,
               rps.final_score AS score, rps.final_kills AS kills,
               rps.final_deaths AS deaths, r.start_time AS started_at
        FROM round_player_stats rps
        JOIN rounds r ON rps.round_id = r.round_id
        JOIN players p ON rps.player_id = p.player_id
        LEFT JOIN servers sv ON r.server_id = sv.server_id
        WHERE p.canonical_name = $1
        ORDER BY r.start_time DESC
        LIMIT $2
        """
        return await self.fetch(sql, player_name, limit)

    async def get_player_personal_bests(self, player_name: str) -> Optional[asyncpg.Record]:
        sql = """
        SELECT
            MAX(rps.final_score) AS best_score,
            MAX(rps.final_kills) AS best_kills
        FROM round_player_stats rps
        JOIN players p ON rps.player_id = p.player_id
        WHERE p.canonical_name = $1
        """
        return await self.fetchrow(sql, player_name)

    # --- ClickHouse convenience methods ---

    def get_player_playtime_seconds(self, player_name: str) -> int:
        """Estimated playtime from ClickHouse player_snapshots. Returns 0 if unavailable."""
        rows = self.ch_query(
            "SELECT count() * 30 AS playtime_seconds FROM player_snapshots WHERE player_name = {name:String}",
            parameters={"name": player_name}
        )
        return rows[0]['playtime_seconds'] if rows else 0

    def get_server_population_trend(self, server_name: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Hourly average population for a server over the last N hours."""
        return self.ch_query(
            """
            SELECT toStartOfHour(timestamp) AS hour, avg(player_count) AS avg_players
            FROM server_snapshots
            WHERE server_name = {name:String}
              AND timestamp >= now() - toIntervalHour({hours:Int32})
            GROUP BY hour
            ORDER BY hour
            """,
            parameters={"name": server_name, "hours": hours}
        )

    def get_server_peak_hours(self, server_name: str) -> List[Dict[str, Any]]:
        """Average population by hour-of-day for a server (last 30 days)."""
        return self.ch_query(
            """
            SELECT toHour(timestamp) AS hour_of_day, avg(player_count) AS avg_players
            FROM server_snapshots
            WHERE server_name = {name:String}
              AND timestamp >= now() - toIntervalDay(30)
            GROUP BY hour_of_day
            ORDER BY hour_of_day
            """,
            parameters={"name": server_name}
        )

    # --- Server Trends Queries (Postgres) ---

    async def get_server_top_players_24h(self, server_name: str, limit: int = 10) -> List[asyncpg.Record]:
        sql = """
        SELECT p.canonical_name AS player_name,
               SUM(rps.final_score) AS total_score, SUM(rps.final_kills) AS total_kills
        FROM round_player_stats rps
        JOIN rounds r ON rps.round_id = r.round_id
        JOIN players p ON rps.player_id = p.player_id
        JOIN servers sv ON r.server_id = sv.server_id
        WHERE sv.current_server_name = $1 AND r.start_time >= NOW() - INTERVAL '24 hours'
        GROUP BY p.canonical_name
        ORDER BY total_score DESC
        LIMIT $2
        """
        return await self.fetch(sql, server_name, limit)

    async def get_server_popular_maps_24h(self, server_name: str, limit: int = 10) -> List[asyncpg.Record]:
        sql = """
        SELECT r.map_name, COUNT(*) AS play_count
        FROM rounds r
        JOIN servers sv ON r.server_id = sv.server_id
        WHERE sv.current_server_name = $1 AND r.start_time >= NOW() - INTERVAL '24 hours'
        GROUP BY r.map_name
        ORDER BY play_count DESC
        LIMIT $2
        """
        return await self.fetch(sql, server_name, limit)

    # --- Digest Queries ---

    async def upsert_digest_subscription(self, user_id: int, guild_id: int, channel_id: Optional[int]):
        sql = """
        INSERT INTO digest_subscriptions (user_id, guild_id, channel_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id)
        DO UPDATE SET guild_id = EXCLUDED.guild_id, channel_id = EXCLUDED.channel_id;
        """
        await self.execute(sql, user_id, guild_id, channel_id)

    async def delete_digest_subscription(self, user_id: int) -> int:
        sql = "DELETE FROM digest_subscriptions WHERE user_id = $1"
        status = await self.execute(sql, user_id)
        return int(status.split(' ')[1])

    async def get_all_digest_subscriptions(self) -> List[asyncpg.Record]:
        sql = """
        SELECT ds.user_id, ds.channel_id,
               dnd.start_hour_utc, dnd.end_hour_utc, dnd.weekdays_utc
        FROM digest_subscriptions ds
        LEFT JOIN user_dnd_rules dnd ON ds.user_id = dnd.user_id
        """
        return await self.fetch(sql)

    async def get_digest_stats(self) -> Optional[asyncpg.Record]:
        sql = """
        SELECT
            (SELECT COUNT(*) FROM rounds WHERE start_time >= NOW() - INTERVAL '24 hours') AS rounds_24h,
            (SELECT COUNT(DISTINCT rps.player_id)
             FROM round_player_stats rps
             JOIN rounds r ON rps.round_id = r.round_id
             WHERE r.start_time >= NOW() - INTERVAL '24 hours') AS unique_players_24h
        """
        return await self.fetchrow(sql)

    async def get_most_active_servers_24h(self, limit: int = 5) -> List[asyncpg.Record]:
        sql = """
        SELECT sv.current_server_name AS server_name, COUNT(*) AS round_count
        FROM rounds r
        JOIN servers sv ON r.server_id = sv.server_id
        WHERE r.start_time >= NOW() - INTERVAL '24 hours'
        GROUP BY sv.current_server_name
        ORDER BY round_count DESC
        LIMIT $1
        """
        return await self.fetch(sql, limit)

    async def get_top_players_24h(self, limit: int = 5) -> List[asyncpg.Record]:
        sql = """
        SELECT p.canonical_name AS player_name,
               SUM(rps.final_score) AS total_score, SUM(rps.final_kills) AS total_kills
        FROM round_player_stats rps
        JOIN rounds r ON rps.round_id = r.round_id
        JOIN players p ON rps.player_id = p.player_id
        WHERE r.start_time >= NOW() - INTERVAL '24 hours'
        GROUP BY p.canonical_name
        ORDER BY total_score DESC
        LIMIT $1
        """
        return await self.fetch(sql, limit)

    async def get_max_round_id(self) -> int:
        row = await self.fetchrow("SELECT COALESCE(MAX(round_id), 0) AS max_id FROM rounds")
        return row['max_id']
