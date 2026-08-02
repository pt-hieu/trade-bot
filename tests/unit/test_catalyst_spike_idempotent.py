"""SWI-275: detect_catalyst_spike uses last_revision_at as baseline floor."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TypedDict

import pytest

from shared.neon import catalyst_signals


class CatalystRow(TypedDict):
    catalyst_key: str
    event: str
    status: str
    impact: str | None
    confidence: str | None
    affected_tickers: list[str]
    phases: list[str] | None
    updated_at: datetime
    catalyst_type: str | None


class _StubDb:
    """Minimal fake DB capturing the args fetch_val/fetch_all receive."""

    def __init__(self, baseline: datetime, catalyst_rows: list[CatalystRow]) -> None:
        self._baseline = baseline
        self._catalyst_rows = catalyst_rows
        self.spike_query_args: tuple[object, ...] | None = None

    async def fetch_val(self, query: str, *args: object) -> datetime:
        # Baseline lookup uses GREATEST + COALESCE — verify both columns appear.
        assert "GREATEST" in query
        assert "last_revision_at" in query
        return self._baseline

    async def fetch_all(self, query: str, *args: object) -> list[CatalystRow]:
        self.spike_query_args = args
        baseline = args[0]
        assert isinstance(baseline, datetime)
        return [row for row in self._catalyst_rows if row["updated_at"] > baseline]


@pytest.mark.asyncio
async def test_detect_catalyst_spike_excludes_already_consumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    morning = datetime(2026, 5, 9, 0, 0, tzinfo=UTC)  # 7am VN
    revision = morning + timedelta(hours=1)  # 8am VN — bumped at first run
    fresh_news = revision + timedelta(minutes=30)  # arrives later

    rows: list[CatalystRow] = [
        {  # Stale: updated_at == morning, already consumed by first revision.
            "catalyst_key": "stale",
            "event": "old",
            "status": "active",
            "impact": None,
            "confidence": None,
            "affected_tickers": ["FPT"],
            "phases": None,
            "updated_at": morning,
            "catalyst_type": None,
        },
        {  # Fresh: post-revision update, should be detected.
            "catalyst_key": "fresh",
            "event": "new",
            "status": "imminent",
            "impact": "BUY",
            "confidence": "HIGH",
            "affected_tickers": ["VCB"],
            "phases": None,
            "updated_at": fresh_news,
            "catalyst_type": "regulatory",
        },
    ]
    stub = _StubDb(baseline=revision, catalyst_rows=rows)

    async def _fake_get_db() -> _StubDb:
        return stub

    monkeypatch.setattr(catalyst_signals, "get_db", _fake_get_db)

    has_spike, trigger, changed = await catalyst_signals.detect_catalyst_spike(date(2026, 5, 9))

    assert has_spike is True
    assert len(changed) == 1
    assert changed[0]["catalyst_key"] == "fresh"
    assert stub.spike_query_args == (revision,)
    assert "new" in trigger


def test_lock_namespace_is_fixed_constant() -> None:
    """Cross-process advisory lock requires a stable, non-randomized namespace.

    Python 3 randomizes string hashes per process, so hash("...") is unsafe
    here. Pin to a literal int.
    """
    from catalyst_check import _CATALYST_LOCK_NAMESPACE

    assert _CATALYST_LOCK_NAMESPACE == 0x63617461
