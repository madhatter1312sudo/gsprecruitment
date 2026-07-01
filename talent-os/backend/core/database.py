"""
Talent OS — Async Database Engine with asyncpg connection pooling.
Replaces the old sync `engine.connect()` that blocked the event loop.
"""
import asyncpg
from typing import Optional
from core.config import settings

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Lazily initialise and return the global connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=settings.postgres_host,
            port=settings.postgres_port,
            database=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
            min_size=2,
            max_size=10,
            command_timeout=30,
            # Always use SSL when connecting
            # ssl="require",  # uncomment once TLS cert is configured
        )
    return _pool


async def close_pool() -> None:
    """Gracefully close the pool on shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def fetch_one(sql: str, *args) -> Optional[dict]:
    """Fetch a single row as a dict."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, *args)
        return dict(row) if row else None


async def fetch_all(sql: str, *args) -> list[dict]:
    """Fetch all matching rows as dicts."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
        return [dict(r) for r in rows]


async def execute(sql: str, *args) -> str:
    """Execute a write statement and return status."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(sql, *args)
        return result


async def fetch_val(sql: str, *args):
    """Fetch a single scalar value."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(sql, *args)