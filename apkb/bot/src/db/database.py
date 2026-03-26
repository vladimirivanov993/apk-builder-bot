import asyncpg
import logging
from typing import Optional

logger = logging.getLogger(__name__)
_pool = None

async def init_db(database_url: str):
    global _pool
    _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=10)
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS builds (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username TEXT,
                app_name TEXT NOT NULL,
                package TEXT NOT NULL,
                version TEXT NOT NULL,
                apk_filename TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                completed_at TIMESTAMP WITH TIME ZONE
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await conn.execute("""
            INSERT INTO settings (key, value)
            VALUES ('maintenance_mode', 'false')
            ON CONFLICT (key) DO NOTHING
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_builds_user_status ON builds(user_id, status)
        """)
    logger.info("Database initialized")

async def close_db():
    global _pool
    if _pool:
        await _pool.close()

async def record_build_start(user_id: int, username: Optional[str], app_name: str, package: str, version: str) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO builds (user_id, username, app_name, package, version, status)
            VALUES ($1, $2, $3, $4, $5, 'processing')
            RETURNING id
            """,
            user_id, username, app_name, package, version
        )
        return row['id']

async def record_build_complete(build_id: int, apk_filename: str):
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE builds
            SET status = 'completed', apk_filename = $2, completed_at = NOW()
            WHERE id = $1
            """,
            build_id, apk_filename
        )

async def record_build_failed(build_id: int, error_message: str):
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE builds
            SET status = 'failed', error_message = $2, completed_at = NOW()
            WHERE id = $1
            """,
            build_id, error_message
        )

async def get_user_active_build(user_id: int) -> Optional[int]:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM builds WHERE user_id = $1 AND status = 'processing'",
            user_id
        )
        return row['id'] if row else None

async def get_maintenance_mode() -> bool:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT value FROM settings WHERE key = 'maintenance_mode'"
        )
        return row['value'].lower() == 'true' if row else False

async def set_maintenance_mode(enabled: bool):
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE settings SET value = $1 WHERE key = 'maintenance_mode'",
            'true' if enabled else 'false'
        )
