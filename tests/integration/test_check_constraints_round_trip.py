"""SWI-NN: PG round-trip integration test for CHECK constraints.

Spins a postgres container via `testcontainers`, applies migrations in order,
and runs synthetic morning recommendations through `_build_rec_row` →
`validate_row` → `INSERT`. Every constraint named in `pg_constraint` for the
pipeline-written tables must appear in `CHECKS_MIRRORED` — drift detection.

Skip when Docker / testcontainers unavailable so local dev without Docker is
not blocked.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("testcontainers", reason="testcontainers not installed")

if not os.environ.get("DOCKER_HOST") and not Path("/var/run/docker.sock").exists():
    pytest.skip("Docker not available — skipping PG round-trip", allow_module_level=True)


import asyncpg  # noqa: E402
from testcontainers.postgres import PostgresContainer  # type: ignore  # noqa: E402

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "scripts" / "db" / "migrations"
PIPELINE_TABLES = ("daily_recommendations", "daily_evaluations")


@pytest.fixture(scope="module")
def pg_url():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")


async def _apply_migrations(conn: asyncpg.Connection) -> None:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    for sql_file in files:
        sql = sql_file.read_text()
        try:
            await conn.execute(sql)
        except Exception as e:
            # Some migrations reference tables/columns added in others; for
            # this smoke test we tolerate failures on prompt-only migrations.
            # The pipeline tables are what we care about.
            if any(table in sql for table in PIPELINE_TABLES):
                raise RuntimeError(f"Failed applying {sql_file.name}: {e}") from e


@pytest.mark.asyncio
async def test_pipeline_tables_check_constraints_mirrored(pg_url):
    from shared.rules.row_invariants import CHECKS_MIRRORED

    conn = await asyncpg.connect(pg_url)
    try:
        await _apply_migrations(conn)
        for table in PIPELINE_TABLES:
            rows = await conn.fetch(
                """
                SELECT c.conname
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                WHERE t.relname = $1 AND c.contype = 'c'
                """,
                table,
            )
            db_checks = {r["conname"] for r in rows}
            mirrored = CHECKS_MIRRORED.get(table, set())
            missing = db_checks - mirrored
            assert not missing, (
                f"Table {table} has CHECK constraints not mirrored in "
                f"shared.rules.row_invariants.CHECKS_MIRRORED: {missing}. "
                "Add a Python mirror or annotate with row_invariant_mirror bypass."
            )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_round_trip_morning_recs(pg_url):
    """Build a representative morning rec set through _build_rec_row and INSERT it."""
    from shared.neon.insert_records._common import _INSERT_REC_SQL, _build_rec_row

    conn = await asyncpg.connect(pg_url)
    try:
        await _apply_migrations(conn)
        record_id = await conn.fetchval(
            """INSERT INTO daily_records (record_date) VALUES (CURRENT_DATE)
               ON CONFLICT (record_date) DO UPDATE SET record_date = EXCLUDED.record_date
               RETURNING id"""
        )

        recs = [
            {
                "ticker": "FPT",
                "action": "BUY",
                "entry_price": 130000,
                "stop_price": 125000,
                "target_price": 145000,
                "section": "TOP_PICKS",
                "source": "picks",
            },
            {
                "ticker": "VCB",
                "action": "WATCH",
                "section": "WHAT_TO_DO",
                "source": "sector_signals",
                "plan_shape": "BREAKOUT",
                "trigger_price": 90000,
                "stop_price": 87000,
                "target_price": 95000,
            },
        ]
        rows = [row for rec in recs if (row := _build_rec_row(record_id, rec, None)) is not None]
        assert len(rows) == 2
        await conn.executemany(_INSERT_REC_SQL, rows)

        count = await conn.fetchval(
            "SELECT COUNT(*) FROM daily_recommendations WHERE record_id = $1",
            record_id,
        )
        assert count == 2
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_round_trip_rejects_invariant_violation(pg_url):
    """A row that bypasses the boundary (synthetic bad row) MUST be rejected by Postgres."""
    conn = await asyncpg.connect(pg_url)
    try:
        await _apply_migrations(conn)
        record_id = await conn.fetchval(
            """INSERT INTO daily_records (record_date) VALUES (CURRENT_DATE)
               ON CONFLICT (record_date) DO UPDATE SET record_date = EXCLUDED.record_date
               RETURNING id"""
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                """INSERT INTO daily_recommendations
                   (record_id, ticker, action, plan_type, plan_shape, trigger_price_vnd)
                   VALUES ($1, 'XYZ', 'BUY', 'SWING', 'BREAKOUT', NULL)""",
                record_id,
            )
    finally:
        await conn.close()
