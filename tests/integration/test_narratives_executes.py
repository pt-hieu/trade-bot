"""Integration — get_active_narratives() must execute against a live Neon DB.

SWI-A class-level guard. The unit test (tests/unit/test_narratives_sql.py)
covers the single literal ``'v2'`` instance. This test executes the SQL so
any future regression of the same defect class — implicit string concat
producing a Postgres parse error — fails on a real connection rather than
silently in production.

Skipped unless DATABASE_URL is set (read-only Neon URL is sufficient since
this is SELECT-only).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — Neon read-only URL required for execution test",
)


@pytest.mark.asyncio
async def test_get_active_narratives_no_filter_executes():
    from shared.neon.narratives import get_active_narratives

    rows = await get_active_narratives()
    assert isinstance(rows, list)


@pytest.mark.asyncio
async def test_get_active_narratives_with_tickers_executes():
    from shared.neon.narratives import get_active_narratives

    rows = await get_active_narratives(["FPT"])
    assert isinstance(rows, list)
