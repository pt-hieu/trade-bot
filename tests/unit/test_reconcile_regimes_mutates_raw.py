"""SWI-133 / Fix 5: regime reconciliation is producer-side, single-source.

Originally MON-2026-04-22-004 centralised reconciliation in
derive_intermediates. The 2026-04-29 audit found that approach still left
Logfire spans + raw JSON outputs from market_level / sector_rotation
shipping un-reconciled values, because the agents emitted the raw regime
BEFORE derive_intermediates re-mutated the dict.

Fix 5 moves the mutation upstream into post_process_phase1 (single
source of truth) AND adds a fail-loud verification in
derive_intermediates: any divergence between raw_regime and
reconcile_regimes(raw, global_risk_regime) means a producer bypassed the
post_process_phase1 reconciliation, so the pipeline aborts loud.
"""

from __future__ import annotations

import pytest

from pipeline.helpers import ProducerLeakError, derive_intermediates, reconcile_regimes


@pytest.mark.parametrize(
    ("raw_regime", "global_risk_regime", "expected_regime"),
    [
        ("RISK_ON", "ELEVATED", "RISK_OFF"),
        ("NEUTRAL", "ELEVATED", "RISK_OFF"),
        ("RISK_OFF", "ELEVATED", "RISK_OFF"),
        ("RISK_ON", "CRISIS", "RISK_OFF"),
        ("RISK_ON", "CAUTIOUS", "NEUTRAL"),
        ("NEUTRAL", "CAUTIOUS", "NEUTRAL"),
        ("RISK_OFF", "CAUTIOUS", "RISK_OFF"),
        ("RISK_ON", "CALM", "RISK_ON"),
        ("NEUTRAL", "CALM", "NEUTRAL"),
    ],
)
def test_reconcile_regimes_collapses_to_floor(
    raw_regime: str,
    global_risk_regime: str,
    expected_regime: str,
) -> None:
    """Pure-function test of the reconciliation rule. Producer-side callers
    (sector_rotation, post_process_phase1) feed raw regime + risk floor;
    reconcile_regimes returns the gate-aligned regime."""
    assert reconcile_regimes(raw_regime, global_risk_regime) == expected_regime


@pytest.mark.asyncio
async def test_derive_intermediates_passes_through_already_reconciled(
    monkeypatch,
) -> None:
    """Post-Fix-5 happy path: post_process_phase1 already reconciled the
    market_level dict. derive_intermediates is now a verification step:
    raw_regime arrives matching reconcile_regimes(raw, risk), so no raise."""

    async def _stub_overlay(regime: str = "") -> None:
        return None

    monkeypatch.setattr(
        "shared.calibration_overlay.init_calibration_overlay",
        _stub_overlay,
    )

    intermediates = await derive_intermediates(
        raw_regime="RISK_OFF",  # already reconciled upstream
        macro_metrics={"global_risk_regime": "ELEVATED"},
        early_mode="NORMAL",
        sector_rotation=None,
        trailing_stops_context="",
        technicals={},
        geopolitical_context="",
        market_level={"regime": "RISK_OFF"},
    )
    assert intermediates.market_regime == "RISK_OFF"


@pytest.mark.asyncio
async def test_derive_intermediates_raises_producer_leak(monkeypatch) -> None:
    """SWI-133 / Fix 5 fail-loud: if a producer-side reconciliation was
    bypassed, derive_intermediates must abort the pipeline."""

    async def _stub_overlay(regime: str = "") -> None:
        return None

    monkeypatch.setattr(
        "shared.calibration_overlay.init_calibration_overlay",
        _stub_overlay,
    )

    with pytest.raises(ProducerLeakError):
        await derive_intermediates(
            raw_regime="RISK_ON",  # un-reconciled — bypass leaked through
            macro_metrics={"global_risk_regime": "ELEVATED"},
            early_mode="NORMAL",
            sector_rotation=None,
            trailing_stops_context="",
            technicals={},
            geopolitical_context="",
            market_level={"regime": "RISK_ON"},
        )
