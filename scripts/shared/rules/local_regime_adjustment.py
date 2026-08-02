"""Local VN-market regime adjustment — pure deterministic Python.

L1 of the 2026-04-24 regime-fix plan. The global classifier in
``agents.macro.calculate_global_regime`` decides risk regime purely from
global macro signals (VIX, DXY, USD/VND, oil) plus the geopolitical
shock floor. That classifier is blind to VN-local context — foreign flow
direction, VN-Index short-term trend, breadth ratio — which is why
2026-04-23 printed ELEVATED under a stale shock while foreign money
accumulated 255B VND and breadth ran bullish.

This rule runs AFTER the global classifier (and after
``apply_shock_floor``) as a post-parallel merge step in Phase 1 once both
``macro_metrics`` and ``foreign_flow`` have returned. It never overrides
CRISIS and never mutates the upstream phase record.

The downgrade gate deliberately avoids ``classify_underlying_stress`` —
that classifier fail-closes True on any USD/VND=PRESSURE reading, which
is the common SBV-rate case and would block the downgrade even when
every VN-local signal says RISK_ON (see /challenge Agent 2 F2).
"""

from __future__ import annotations

REGIME_ORDER: dict[str, int] = {"CALM": 0, "CAUTIOUS": 1, "ELEVATED": 2, "CRISIS": 3}
REGIME_DOWNGRADE: dict[str, str] = {"ELEVATED": "CAUTIOUS"}
REGIME_UPGRADE: dict[str, str] = {"CAUTIOUS": "ELEVATED"}

# Breadth / VN-Index thresholds. Values are whole percent for
# ``vn_index_3d_pct`` (e.g. +1.5 = +1.5%), raw ratio for breadth.
_BULLISH_BREADTH_RATIO = 1.3
_BEARISH_BREADTH_RATIO = 0.7
_BULLISH_VN_INDEX_3D = 0.0
_BEARISH_VN_INDEX_3D = -2.0


def apply_local_vn_adjustment(
    *,
    computed_regime: str,
    vix_signal: str,
    usd_vnd_signal: str,
    foreign_flow_signal: str | None,
    breadth_ratio: float | None,
    vn_index_3d_pct: float | None,
) -> tuple[str, list[str]]:
    """Adjust the global regime based on VN-local evidence.

    Downgrade ELEVATED -> CAUTIOUS when every VN signal is bullish AND
    global signals are not in genuine stress. Upgrade CAUTIOUS ->
    ELEVATED when VN signals signal broad risk-off. CRISIS is never
    overridden. Missing VN signals never trigger an adjustment (fail
    safe — the global regime stands).

    Returns ``(adjusted_regime, rules_fired)``. ``rules_fired`` is the
    audit trail persisted onto ``MacroMetricsOutput.regime_adjustments``
    for SQL post-hoc review.

    Args:
        computed_regime: Output of ``calculate_global_regime`` *after*
            ``apply_shock_floor`` — CALM / CAUTIOUS / ELEVATED / CRISIS.
        vix_signal: Raw VIX classification — LOW / MODERATE / HIGH /
            EXTREME.
        usd_vnd_signal: Raw USD/VND classification — NEUTRAL / PRESSURE
            / FLIGHT.
        foreign_flow_signal: Per ``agents.foreign_flow`` classifier —
            RISK_ON / RISK_OFF / NEUTRAL (or None when missing).
        breadth_ratio: advance / decline. ``None`` when breadth fetch
            failed.
        vn_index_3d_pct: Rolling 3-trading-day VN-Index close-to-close
            change in whole percent. ``None`` when price history is
            missing.
    """
    rules: list[str] = []

    if computed_regime == "CRISIS":
        return computed_regime, rules

    vix = (vix_signal or "").upper()
    usd_vnd = (usd_vnd_signal or "").upper()
    flow = (foreign_flow_signal or "").upper() or None

    # Downgrade path — requires the full VN-bullish trio AND the absence
    # of genuine global stress (FLIGHT / HIGH-VIX / EXTREME-VIX).
    if (
        computed_regime in REGIME_DOWNGRADE
        and flow == "RISK_ON"
        and breadth_ratio is not None
        and breadth_ratio >= _BULLISH_BREADTH_RATIO
        and vn_index_3d_pct is not None
        and vn_index_3d_pct >= _BULLISH_VN_INDEX_3D
        and vix not in ("HIGH", "EXTREME")
        and usd_vnd != "FLIGHT"
    ):
        adjusted = REGIME_DOWNGRADE[computed_regime]
        rules.append(f"local_vn_downgrade_{computed_regime.lower()}_to_{adjusted.lower()}")
        return adjusted, rules

    # Upgrade path — VN-local stress accumulates even when global signals
    # look CAUTIOUS. Runs regardless of VIX/USD-VND since the goal is
    # catching risk-off rotations the global classifier missed.
    if (
        computed_regime in REGIME_UPGRADE
        and flow == "RISK_OFF"
        and breadth_ratio is not None
        and breadth_ratio <= _BEARISH_BREADTH_RATIO
        and vn_index_3d_pct is not None
        and vn_index_3d_pct <= _BEARISH_VN_INDEX_3D
    ):
        adjusted = REGIME_UPGRADE[computed_regime]
        rules.append(f"local_vn_upgrade_{computed_regime.lower()}_to_{adjusted.lower()}")
        return adjusted, rules

    return computed_regime, rules


__all__ = ["apply_local_vn_adjustment"]
