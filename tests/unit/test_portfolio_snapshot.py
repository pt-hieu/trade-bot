"""SWI-121: HoldingsSnapshot dataclass + freshest updated_at extraction."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from shared.neon.portfolio import HoldingsSnapshot


def test_holdings_snapshot_is_frozen_dataclass() -> None:
    snap = HoldingsSnapshot(holdings=[], snapshot_at=None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.holdings = []  # type: ignore[misc]


def test_holdings_snapshot_carries_timestamp() -> None:
    ts = datetime(2026, 5, 12, 23, 12, tzinfo=UTC)
    snap = HoldingsSnapshot(holdings=[{"ticker": "FPT"}], snapshot_at=ts)
    assert snap.snapshot_at == ts
    assert snap.holdings[0]["ticker"] == "FPT"


def test_holdings_snapshot_at_is_none_when_no_rows() -> None:
    snap = HoldingsSnapshot(holdings=[], snapshot_at=None)
    assert snap.snapshot_at is None
