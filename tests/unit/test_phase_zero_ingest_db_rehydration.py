"""Unit — _phase_zero_ingest must rehydrate from DB, not from disk cache.

SWI-B (2026-05-06): the v1 disk-cache path (``load_search_results``) returned
``{}`` on a fresh GH Actions runner because research/{date}/*.json files only
exist after a previous successful local commit. The new path always SELECTs
back from the DB after insert — every article carries its DB id.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_phase_zero_returns_db_rehydrated_articles(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    rehydrated = [
        {"id": "uuid-1", "url": "https://a", "title": "T1", "query_name": "rss-vn"},
        {"id": "uuid-2", "url": "https://b", "title": "T2", "query_name": "rss-vn"},
        {"id": "uuid-3", "url": "https://c", "title": "T3", "query_name": "rss-intl-bbc"},
    ]

    with (
        patch(
            "shared.neon.get_swing_watchlist",
            new=AsyncMock(return_value={"Tech": ["FPT"]}),
        ),
        patch(
            "shared.neon.get_portfolio_holdings",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "data.articles.articles_exist_in_db",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "shared.neon.load_articles_for_scan_date",
            new=AsyncMock(return_value=rehydrated),
        ),
    ):
        from news_pipeline_v2 import _phase_zero_ingest

        articles = await _phase_zero_ingest(date(2026, 5, 6))

    assert articles == rehydrated
    assert all(article["id"] for article in articles), "every article must carry DB id"


@pytest.mark.asyncio
async def test_phase_zero_does_not_depend_on_disk_files(tmp_path, monkeypatch):
    """No disk read happens — load_search_results was deleted with v1 orchestrator."""
    monkeypatch.chdir(tmp_path)

    with (
        patch(
            "shared.neon.get_swing_watchlist",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "shared.neon.get_portfolio_holdings",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "data.articles.articles_exist_in_db",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "shared.neon.load_articles_for_scan_date",
            new=AsyncMock(return_value=[{"id": "u", "url": "x", "query_name": "rss-vn"}]),
        ),
    ):
        from news_pipeline_v2 import _phase_zero_ingest

        # Should not raise even though no research/{date}/*.json files exist.
        articles = await _phase_zero_ingest(date(2026, 5, 6))

    assert len(articles) == 1
