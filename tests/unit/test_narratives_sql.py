"""Unit regression — get_active_narratives must bind pipeline_version, not f-string it.

SWI-A (2026-05-06): the freshness_clause f-string concat
``"... > 0" f"AND pipeline_version='{V2}'"`` produced ``> 0AND ...`` and
Postgres rejected the whole query at parse time, silently killing news v2
for ~10 days. The instance fix binds pipeline_version as $N — this test
asserts the literal ``'v2'`` no longer appears in the rendered SQL and that
``pipeline_version = $N`` is present in both branches.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_no_inline_pipeline_version_literal_when_tickers_supplied():
    captured: dict[str, object] = {}

    async def fake_fetch_all(sql: str, *params: object) -> list[dict]:
        captured["sql"] = sql
        captured["params"] = params
        return []

    mock_db = AsyncMock()
    mock_db.fetch_all = fake_fetch_all

    with patch("shared.neon.narratives.get_db", new=AsyncMock(return_value=mock_db)):
        from shared.neon.narratives import get_active_narratives

        await get_active_narratives(["FPT"])

    rendered_sql = captured["sql"]
    assert isinstance(rendered_sql, str)
    assert "'v2'" not in rendered_sql, "pipeline_version must be bound as $N, not inlined"
    assert "pipeline_version = $2" in rendered_sql
    assert captured["params"] == (["FPT"], "v2")


@pytest.mark.asyncio
async def test_no_inline_pipeline_version_literal_when_tickers_absent():
    captured: dict[str, object] = {}

    async def fake_fetch_all(sql: str, *params: object) -> list[dict]:
        captured["sql"] = sql
        captured["params"] = params
        return []

    mock_db = AsyncMock()
    mock_db.fetch_all = fake_fetch_all

    with patch("shared.neon.narratives.get_db", new=AsyncMock(return_value=mock_db)):
        from shared.neon.narratives import get_active_narratives

        await get_active_narratives()

    rendered_sql = captured["sql"]
    assert isinstance(rendered_sql, str)
    assert "'v2'" not in rendered_sql
    assert "pipeline_version = $1" in rendered_sql
    assert captured["params"] == ("v2",)
