"""SWI-18: `_persist_discoveries` drops `unparseable` rows but keeps batch alive.

Failure-mode-asymmetry guarantee — junk parses must not blank out a whole
CatalystAddition batch (round-1 challenge: blanket Pydantic validator caused
output_retries=2 retry-storms). Per-row drop + log; siblings persist.
"""

from __future__ import annotations

from datetime import date
from typing import TypedDict
from unittest.mock import AsyncMock, patch

import pytest

from agents.catalysts import _persist_discoveries

SCAN_DATE = date(2026, 4, 27)


class _AdditionFixture(TypedDict):
    event: str
    expected: str
    affected: list[str]
    impact: str
    confidence: str
    catalyst_type: str
    phases: dict[str, dict[str, str]]
    catalyst_factors: list[str]
    official_document_flag: bool


def _addition(event: str, expected: str) -> _AdditionFixture:
    return {
        "event": event,
        "expected": expected,
        "affected": ["VN-INDEX"],
        "impact": "neutral",
        "confidence": "MEDIUM",
        "catalyst_type": "macro",
        "phases": {"pre": {"start": "2026-04-01", "end": "2026-04-30"}},
        "catalyst_factors": [],
        "official_document_flag": False,
    }


@pytest.mark.asyncio
async def test_persist_drops_unparseable_keeps_batch() -> None:
    """A garbage `expected=` row drops; valid siblings still upsert."""
    discoveries = {
        "additions": [
            _addition("rate decision", "Q3 2026"),
            _addition("budget review", "blah blah 2027 maybe sometime"),
            _addition("policy roll-out", "ongoing"),
        ],
    }

    with (
        patch(
            "agents.catalysts.get_active_catalysts_db",
            new=AsyncMock(return_value=[]),
        ),
        patch("agents.catalysts.upsert_catalyst", new=AsyncMock()) as upsert,
        patch(
            "agents.catalysts._record_catalyst_rejection",
            new=AsyncMock(),
        ),
        patch(
            "agents.catalysts.link_catalyst_articles",
            new=AsyncMock(),
        ),
    ):
        await _persist_discoveries(discoveries, scan_date=SCAN_DATE, classified_articles=[])

    persisted_events = [call.args[0]["event"] for call in upsert.call_args_list]
    persisted_statuses = [call.args[0]["expected_status"] for call in upsert.call_args_list]

    assert "rate decision" in persisted_events
    assert "policy roll-out" in persisted_events
    assert "budget review" not in persisted_events, f"unparseable row leaked: {persisted_events}"
    assert set(persisted_statuses).issubset({"dated", "quarter", "month", "relative", "ongoing"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expected_text,expected_status",
    [
        ("2026-08-15", "dated"),
        ("Q3 2026", "quarter"),
        ("August 2026", "month"),
        ("next 30 days", "relative"),
        ("ongoing", "ongoing"),
    ],
)
async def test_persist_admits_each_ok_status(
    expected_text: str,
    expected_status: str,
) -> None:
    """Every status in PERSIST_OK_STATUSES round-trips through the persist gate."""
    discoveries = {"additions": [_addition("event", expected_text)]}

    with (
        patch(
            "agents.catalysts.get_active_catalysts_db",
            new=AsyncMock(return_value=[]),
        ),
        patch("agents.catalysts.upsert_catalyst", new=AsyncMock()) as upsert,
    ):
        await _persist_discoveries(discoveries, scan_date=SCAN_DATE, classified_articles=[])

    assert upsert.await_count == 1
    assert upsert.await_args is not None
    payload = upsert.await_args.args[0]
    assert payload["expected_status"] == expected_status
