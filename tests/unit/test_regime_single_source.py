"""Single source-of-truth invariant for market_regime across producers.

SWI-133 / Fix 5 update: reconciliation moved upstream from
derive_intermediates into post_process_phase1. derive_intermediates now
verifies (raises ProducerLeakError on drift) instead of mutating, so
this test exercises the post-reconciliation invariant: when callers
pass an already-reconciled raw_regime, all three views agree.
"""

from __future__ import annotations

import pytest

from pipeline.helpers import derive_intermediates


@pytest.mark.asyncio
async def test_regime_agrees_across_market_level_intermediates_and_rotation(
    monkeypatch,
) -> None:
    async def _stub_overlay(regime: str = "") -> None:
        return None

    monkeypatch.setattr(
        "shared.calibration_overlay.init_calibration_overlay",
        _stub_overlay,
    )

    # Producer-side reconciliation in post_process_phase1 already ran:
    # market_level['regime'] is reconciled, regime_raw preserves the
    # pre-reconciliation value.
    market_level = {
        "regime": "RISK_OFF",
        "regime_raw": "RISK_ON",
        "regime_confidence": 0.65,
    }
    macro_metrics = {"global_risk_regime": "ELEVATED"}
    sector_rotation = {
        "hot_sectors": ["Banking", "IT"],
        "cold_sectors": ["Real Estate"],
    }

    intermediates = await derive_intermediates(
        raw_regime="RISK_OFF",  # already reconciled upstream
        macro_metrics=macro_metrics,
        early_mode="NORMAL",
        sector_rotation=sector_rotation,
        trailing_stops_context="",
        technicals={},
        geopolitical_context="",
        market_level=market_level,
    )

    if intermediates.sector_rotation and not intermediates.sector_rotation.get("market_regime"):
        intermediates.sector_rotation["market_regime"] = intermediates.market_regime

    expected = "RISK_OFF"
    assert intermediates.market_regime == expected
    assert market_level["regime"] == expected
    assert intermediates.sector_rotation is not None
    assert intermediates.sector_rotation["market_regime"] == expected
    # regime_raw is preserved by the upstream reconciliation, not by
    # derive_intermediates anymore.
    assert market_level["regime_raw"] == "RISK_ON"


@pytest.mark.asyncio
async def test_regime_agrees_when_no_reconciliation_needed(monkeypatch) -> None:
    """CALM risk regime: no floor applied; raw regime passes through unchanged."""

    async def _stub_overlay(regime: str = "") -> None:
        return None

    monkeypatch.setattr(
        "shared.calibration_overlay.init_calibration_overlay",
        _stub_overlay,
    )

    market_level = {"regime": "NEUTRAL"}
    macro_metrics = {"global_risk_regime": "CALM"}

    intermediates = await derive_intermediates(
        raw_regime="NEUTRAL",
        macro_metrics=macro_metrics,
        early_mode="NORMAL",
        sector_rotation={"hot_sectors": [], "cold_sectors": []},
        trailing_stops_context="",
        technicals={},
        geopolitical_context="",
        market_level=market_level,
    )

    assert intermediates.market_regime == "NEUTRAL"
    assert market_level["regime"] == "NEUTRAL"
