"""Tests for insert_daily_record — atomic eval persistence + empty-payload guard."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest


def _make_db_mock(fetch_val_side_effect: list[object]) -> AsyncMock:
    db = AsyncMock()
    # db.fetch_val (outside txn) and conn.fetchval (inside txn) drain from
    # the same sequence — the transaction context yields the mock itself.
    values = iter(fetch_val_side_effect)

    async def _drain(*_args, **_kwargs):
        return next(values)

    db.fetch_val = AsyncMock(side_effect=_drain)
    db.fetchval = AsyncMock(side_effect=_drain)
    db.execute = AsyncMock()
    db.execute_many = AsyncMock()
    db.executemany = AsyncMock()

    @asynccontextmanager
    async def _txn():
        yield db

    db.transaction = _txn  # type: ignore[method-assign]
    return db


_REC = {
    "ticker": "FPT",
    "action": "HOLD",
    "section": "MY_HOLDINGS",
}
_EVAL = {
    "ticker": "FPT",
    "recommendation": "HOLD",
    "section": "MY_HOLDINGS",
    "entry_hit": False,
    "stop_hit": False,
    "target_hit": False,
    "eod_price": 76.0,
    "pnl_percent": -10.1,
    "status": "HOLD",
    "analysis": "Holding through earnings.",
    "won": False,
    "day_change": -0.5,
}


@pytest.mark.asyncio
async def test_persists_evals_when_recs_and_evals_match():
    """Happy path: 1 rec + 1 eval → both persisted."""
    # fetch values: id=1, existing_rec_count=0
    db = _make_db_mock(fetch_val_side_effect=[1, 0])
    scan = date(2026, 4, 19)
    data = {"recommendations": [_REC], "evaluations": [_EVAL]}

    with patch("shared.neon.insert_records.daily.get_db", return_value=db):
        from shared.neon.insert_records import insert_daily_record

        ok = await insert_daily_record(scan, data)
    assert ok is True
    # executemany called twice inside transaction — once for recs, once for evals
    assert db.executemany.call_count == 2


@pytest.mark.asyncio
async def test_raises_eval_persistence_gap_when_recs_exist_but_no_evals():
    """The 2026-04-19 retro bug — recs in DB, evals empty → must raise."""
    # fetch values: id=1, existing_rec_count=12 (morning had recs)
    db = _make_db_mock(fetch_val_side_effect=[1, 12])
    scan = date(2026, 4, 19)
    data = {"recommendations": [], "evaluations": []}

    with (
        patch("shared.neon.insert_records.daily.get_db", return_value=db),
        pytest.raises(RuntimeError, match="EVAL_PERSISTENCE_GAP"),
    ):
        from shared.neon.insert_records import insert_daily_record

        await insert_daily_record(scan, data)
    # DELETE must NOT have run — transaction rolled back before reaching it
    delete_calls = [c for c in db.execute.call_args_list if "DELETE" in str(c)]
    assert delete_calls == []


@pytest.mark.asyncio
async def test_raises_when_incoming_recs_present_but_evals_empty():
    """Recs being re-inserted but evals empty → must raise."""
    db = _make_db_mock(fetch_val_side_effect=[1, 0])
    scan = date(2026, 4, 19)
    data = {"recommendations": [_REC], "evaluations": []}

    with (
        patch("shared.neon.insert_records.daily.get_db", return_value=db),
        pytest.raises(RuntimeError, match="EVAL_PERSISTENCE_GAP"),
    ):
        from shared.neon.insert_records import insert_daily_record

        await insert_daily_record(scan, data)


@pytest.mark.asyncio
async def test_no_recs_no_evals_does_not_raise():
    """Genuinely empty day — no recs, no evals → no raise."""
    db = _make_db_mock(fetch_val_side_effect=[1, 0])
    scan = date(2026, 4, 19)
    data = {"recommendations": [], "evaluations": []}

    with patch("shared.neon.insert_records.daily.get_db", return_value=db):
        from shared.neon.insert_records import insert_daily_record

        ok = await insert_daily_record(scan, data)
    assert ok is True


@pytest.mark.asyncio
async def test_evaluate_action_does_not_trigger_false_gap():
    """EVALUATE action (added in dd1a3f5c) is a valid eval row, not a gap."""
    db = _make_db_mock(fetch_val_side_effect=[1, 0])
    scan = date(2026, 4, 19)
    eval_with_evaluate = {**_EVAL, "recommendation": "EVALUATE", "status": "PENDING"}
    data = {"recommendations": [_REC], "evaluations": [eval_with_evaluate]}

    with patch("shared.neon.insert_records.daily.get_db", return_value=db):
        from shared.neon.insert_records import insert_daily_record

        ok = await insert_daily_record(scan, data)
    assert ok is True
    # eval row was persisted (not filtered out by allowlist mismatch)
    eval_call = [c for c in db.executemany.call_args_list if "daily_evaluations" in str(c[0][0])]
    assert len(eval_call) == 1
    assert eval_call[0][0][1][0][2] == "EVALUATE"
