"""SWI-183 — cross-retry preservation through monitor_positions_ensemble.

Simulates two retry attempts of the daily-scan as fresh processes by
running the upsert/merge layer directly with an in-memory store standing
in for `morning_position_alerts`. Asserts that an attempt-1 1/3 EXIT is
overridden by an attempt-2 3/3 HOLD via [COVERAGE_GAP_OVERRIDE] — the
opposite of the 2026-04-28 silent downgrade.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from shared.rules.audit_tags import COVERAGE_GAP_OVERRIDE  # noqa: E402


@pytest.mark.asyncio
async def test_attempt2_full_coverage_overrides_attempt1_partial_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared.neon import position_alerts as pa

    store: dict[tuple[date, str], dict] = {}

    async def fake_get(scan_date: date) -> list[dict]:
        return [v for (d, _), v in store.items() if d == scan_date]

    async def fake_insert(scan_date: date, alerts: list[dict]) -> int:
        for alert in alerts:
            ticker = alert.get("ticker")
            if not ticker:
                continue
            store[(scan_date, ticker)] = dict(alert)
        return len(alerts)

    monkeypatch.setattr(pa, "get_morning_position_alerts", fake_get)
    monkeypatch.setattr(pa, "insert_morning_position_alerts", fake_insert)

    scan = date(2026, 4, 28)

    # Attempt 1: 1/3 coverage emits EXIT (the wrong call from the incident).
    attempt1_alerts = [
        {
            "ticker": "FPT",
            "action": "EXIT",
            "urgency": "high",
            "reason": "ADX 28 -DI dominant; 3 insider sells; RS 0.87x",
            "coverage_responding": 1,
            "coverage_total": 3,
        }
    ]
    await pa.upsert_with_passthrough(scan, attempt1_alerts)
    persisted_after_1 = await fake_get(scan)
    assert len(persisted_after_1) == 1
    assert persisted_after_1[0]["action"] == "EXIT"

    # Attempt 2: 3/3 coverage emits HOLD (the correct call).
    attempt2_alerts = [
        {
            "ticker": "FPT",
            "action": "HOLD",
            "urgency": "low",
            "reason": "Floor 92k intact; MACD bullish divergence forming; RS in peer-beta zone.",
            "coverage_responding": 3,
            "coverage_total": 3,
        }
    ]
    await pa.upsert_with_passthrough(scan, attempt2_alerts)

    final = await fake_get(scan)
    assert len(final) == 1
    final_alert = final[0]
    assert final_alert["action"] == "HOLD"
    assert COVERAGE_GAP_OVERRIDE in final_alert["reason"]
    assert final_alert["coverage_responding"] == 3
    assert final_alert["coverage_total"] == 3


@pytest.mark.asyncio
async def test_attempt2_equal_coverage_preserves_attempt1_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Symmetric guard: equal coverage on both attempts → action-rank wins."""
    from shared.neon import position_alerts as pa

    store: dict[tuple[date, str], dict] = {}

    async def fake_get(scan_date: date) -> list[dict]:
        return [v for (d, _), v in store.items() if d == scan_date]

    async def fake_insert(scan_date: date, alerts: list[dict]) -> int:
        for alert in alerts:
            store[(scan_date, alert["ticker"])] = dict(alert)
        return len(alerts)

    monkeypatch.setattr(pa, "get_morning_position_alerts", fake_get)
    monkeypatch.setattr(pa, "insert_morning_position_alerts", fake_insert)

    scan = date(2026, 4, 28)
    await pa.upsert_with_passthrough(
        scan,
        [
            {
                "ticker": "FPT",
                "action": "EXIT",
                "reason": "broke",
                "coverage_responding": 3,
                "coverage_total": 3,
            }
        ],
    )
    await pa.upsert_with_passthrough(
        scan,
        [
            {
                "ticker": "FPT",
                "action": "HOLD",
                "reason": "stable",
                "coverage_responding": 3,
                "coverage_total": 3,
            }
        ],
    )
    final = await fake_get(scan)
    assert final[0]["action"] == "EXIT"
