"""
Database connection module for Neon/PostgreSQL.

Provides async connection pooling and query helpers using asyncpg.
Supports both local Docker Postgres and Neon.tech serverless.

Environment Variables:
    DATABASE_URL: PostgreSQL connection string
        Local: postgresql://swingy:localdev@localhost:5432/swingy
        Neon:  postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/swingy

Usage:
    from shared.database import Database

    async with Database() as db:
        rows = await db.fetch_all("SELECT * FROM stocks")
        row = await db.fetch_one("SELECT * FROM stocks WHERE ticker = $1", "FPT")
        await db.execute("INSERT INTO stocks (ticker) VALUES ($1)", "VHM")
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from asyncpg import Pool, Record

logger = logging.getLogger(__name__)

# Default to local Docker Postgres
DEFAULT_DATABASE_URL = "postgresql://swingy:localdev@localhost:5432/swingy"


class Database:
    """Async database connection manager with connection pooling."""

    _pool: Pool | None = None
    _url: str | None = None
    _connect_lock: asyncio.Lock | None = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """Lazily create lock (safe under single event loop + GIL)."""
        if cls._connect_lock is None:
            cls._connect_lock = asyncio.Lock()
        return cls._connect_lock

    def __init__(self, url: str | None = None):
        """Initialize database with optional URL override."""
        self._url = url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

    async def connect(self) -> None:
        """Create connection pool if not already connected."""
        if Database._pool is not None:
            return
        async with self._get_lock():
            if Database._pool is not None:
                return  # Another coroutine created it while we waited
            # Safety banner: show which database we're targeting
            url = self._url or ""
            if "neon.tech" in url:
                logger.info("[DB] Connecting to: *** NEON PRODUCTION ***")
            elif "localhost" in url:
                logger.info("[DB] Connecting to: localhost (Docker)")
            else:
                logger.info("[DB] Connecting to: %s...", url[:40])

            async def _init_connection(connection):
                """Register JSONB codec so asyncpg decodes JSONB as Python objects."""
                await connection.set_type_codec(
                    "jsonb",
                    encoder=json.dumps,
                    decoder=json.loads,
                    schema="pg_catalog",
                )

            # SWI-261: pool size gated by env var. Default 10 (Neon Standard
            # tier). catalyst-check workflow sets SWINGY_PG_POOL_MAX=20 to
            # absorb nested gather fan-out on spike-disposition path. Other
            # pipelines retain the default to avoid Neon connection-limit alerts.
            max_size = int(os.environ.get("SWINGY_PG_POOL_MAX", "10"))
            Database._pool = await asyncpg.create_pool(
                self._url,
                min_size=0,
                max_size=max_size,
                command_timeout=60,
                init=_init_connection,
            )

    async def disconnect(self) -> None:
        """Close connection pool."""
        if Database._pool is not None:
            await Database._pool.close()
            Database._pool = None

    async def __aenter__(self) -> "Database":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit — intentionally a no-op.

        Pool is a class-level singleton shared across all Database() instances.
        Use `await close_db()` in a `finally:` block to close explicitly.
        """
        pass

    @property
    def pool(self) -> Pool:
        """Get the connection pool, raising if not connected."""
        if Database._pool is None:
            raise RuntimeError("Database not connected. Use 'async with Database():'")
        return Database._pool

    async def _with_retry(self, method: str, query: str, *args: Any) -> Any:
        """Execute a query with retry on stale Neon connections."""
        for attempt in range(2):
            try:
                async with self.pool.acquire() as conn:
                    return await getattr(conn, method)(query, *args)
            except asyncpg.ConnectionDoesNotExistError:
                if attempt == 0:
                    continue
                raise

    async def execute(self, query: str, *args: Any) -> str:
        """Execute a query and return status string.

        Pass parameters as positional args, NOT as a list:
            await db.execute("... $1", value)      # correct
            await db.execute("... $1", [value])     # WRONG — asyncpg error
        """
        return await self._with_retry("execute", query, *args)

    async def execute_many(self, query: str, args_list: list[tuple]) -> None:
        """Execute a query for multiple sets of arguments (with retry)."""
        if not args_list:
            return
        for attempt in range(2):
            try:
                async with self.pool.acquire() as conn:
                    await conn.executemany(query, args_list)
                return
            except asyncpg.ConnectionDoesNotExistError:
                if attempt == 0:
                    continue
                raise

    async def fetch_one(self, query: str, *args: Any) -> Record | None:
        """Fetch a single row.

        Pass parameters as positional args, NOT as a list.
        """
        return await self._with_retry("fetchrow", query, *args)

    async def fetch_all(self, query: str, *args: Any) -> list[Record]:
        """Fetch all rows.

        Pass parameters as positional args, NOT as a list:
            await db.fetch_all("... WHERE x = $1", value)      # correct
            await db.fetch_all("... WHERE x = $1", [value])     # WRONG
        """
        return await self._with_retry("fetch", query, *args)

    async def fetch_val(self, query: str, *args: Any) -> Any:
        """Fetch a single value from the first column of the first row.

        Pass parameters as positional args, NOT as a list.
        """
        return await self._with_retry("fetchval", query, *args)

    @asynccontextmanager
    async def transaction(self):
        """Context manager for transactions."""
        async with self.pool.acquire() as conn, conn.transaction():
            yield conn


# Singleton instance for module-level usage
_db: Database | None = None
_db_lock: asyncio.Lock | None = None


def _get_db_lock() -> asyncio.Lock:
    """Lazily create module-level lock (safe under single event loop + GIL)."""
    global _db_lock
    if _db_lock is None:
        _db_lock = asyncio.Lock()
    return _db_lock


async def get_db() -> Database:
    """Get or create the singleton database instance."""
    global _db
    if _db is not None:
        return _db
    async with _get_db_lock():
        if _db is not None:
            return _db  # Another coroutine created it while we waited
        _db = Database()
        await _db.connect()
    return _db


async def close_db() -> None:
    """Close the database connection pool."""
    global _db
    if _db is not None:
        await _db.disconnect()
        _db = None


# Convenience functions for direct usage
async def execute(query: str, *args: Any) -> str:
    """Execute a query. Pass params as positional args, not a list."""
    db = await get_db()
    return await db.execute(query, *args)


async def fetch_one(query: str, *args: Any) -> Record | None:
    """Fetch a single row. Pass params as positional args, not a list."""
    db = await get_db()
    return await db.fetch_one(query, *args)


async def fetch_all(query: str, *args: Any) -> list[Record]:
    """Fetch all rows. Pass params as positional args, not a list."""
    db = await get_db()
    return await db.fetch_all(query, *args)


async def fetch_val(query: str, *args: Any) -> Any:
    """Fetch a single value. Pass params as positional args, not a list."""
    db = await get_db()
    return await db.fetch_val(query, *args)


# Sync wrapper for scripts that aren't async
def run_sync(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


if __name__ == "__main__":
    # Test connection
    async def test():
        async with Database() as db:
            # Test basic query
            result = await db.fetch_val("SELECT 1")
            print(f"Connection test: {result}")

            # Test sectors table
            sectors = await db.fetch_all("SELECT * FROM sectors")
            print(f"Sectors: {len(sectors)} rows")
            for s in sectors:
                print(f"  - {s['name']}: {s['display_name']}")

            # Test function
            deployable = await db.fetch_val("SELECT get_deployable_cash()")
            print(f"Deployable cash: {deployable}")

    asyncio.run(test())
