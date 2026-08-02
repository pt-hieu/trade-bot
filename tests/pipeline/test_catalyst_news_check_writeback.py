"""SWI-64: write-back must refresh last_updated for ALL checked catalysts.

Asserts the all-checked-keys UPDATE fires for the full inspected set,
not just the signal-producers, and that the idempotent guard
(``last_updated < signal_date``) still gates clock-skew rollback.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from pipeline.catalyst_news_check import save_catalyst_news_signals


class _DBStub:
    def __init__(self) -> None:
        self.execute = AsyncMock()
        self.execute_many = AsyncMock()


@pytest.fixture
def db_stub(monkeypatch) -> _DBStub:
    db = _DBStub()
    get_db_mock = AsyncMock(return_value=db)
    monkeypatch.setattr("pipeline.catalyst_news_check.get_db", get_db_mock)
    return db


@pytest.mark.asyncio
async def test_zero_hit_rows_still_refreshed(db_stub: _DBStub) -> None:
    scan_date = date(2026, 5, 1)
    checked = ["a", "b", "c"]
    saved = await save_catalyst_news_signals(
        signals=[], scan_date=scan_date, match_method="llm", checked_keys=checked
    )

    assert saved == 0
    db_stub.execute_many.assert_not_called()
    db_stub.execute.assert_awaited_once()
    update_args = db_stub.execute.await_args
    assert update_args.args[1] == scan_date
    assert update_args.args[2] == checked


@pytest.mark.asyncio
async def test_signal_producers_and_zero_hit_both_refreshed(db_stub: _DBStub) -> None:
    scan_date = date(2026, 5, 1)
    checked = ["sig1", "zero1", "zero2"]
    signals: list[dict] = [
        {
            "catalyst_key": "sig1",
            "catalyst_event": "evt",
            "article_count": 4,
            "unique_article_count": 2,
            "is_spike": True,
            "sample_titles": ["t"],
        }
    ]
    saved = await save_catalyst_news_signals(
        signals=signals, scan_date=scan_date, match_method="llm", checked_keys=checked
    )

    assert saved == 1
    db_stub.execute_many.assert_awaited_once()
    db_stub.execute.assert_awaited_once()
    refresh_args = db_stub.execute.await_args.args
    assert refresh_args[2] == checked


@pytest.mark.asyncio
async def test_legacy_callers_without_checked_keys_refresh_signal_producers(
    db_stub: _DBStub,
) -> None:
    scan_date = date(2026, 5, 1)
    signals = [
        {
            "catalyst_key": "only_one",
            "catalyst_event": "evt",
            "article_count": 1,
            "unique_article_count": 1,
            "is_spike": False,
            "sample_titles": [],
        }
    ]
    saved = await save_catalyst_news_signals(
        signals=signals, scan_date=scan_date, match_method="llm"
    )
    assert saved == 1
    refresh_args = db_stub.execute.await_args.args
    assert refresh_args[2] == ["only_one"]


@pytest.mark.asyncio
async def test_idempotent_guard_in_sql(db_stub: _DBStub) -> None:
    scan_date = date(2026, 5, 1)
    await save_catalyst_news_signals(
        signals=[], scan_date=scan_date, match_method="llm", checked_keys=["k"]
    )
    sql = db_stub.execute.await_args.args[0]
    assert "last_updated IS NULL OR last_updated < $1" in sql
