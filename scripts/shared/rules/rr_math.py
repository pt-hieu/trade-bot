"""Net-of-cost R:R math — single source of truth for the cost model.

Round-trip transaction cost is split symmetrically around entry notional.
Using entry price (not target) as the notional baseline is a conservative
approximation — actual exit notional on a winner is higher, so true cost
drag is slightly greater than modelled (~5% relative overestimate on R:R,
well inside calibration noise).
"""

from __future__ import annotations

from typing import TypedDict


class RRDiagnostics(TypedDict):
    """Geometry-anomaly flags emitted alongside (rr_net, rr_gross).

    Flags are advisory: shipped setups are never rejected on these — see
    SWI-358's binding decision (visibility over gating). Downstream
    `scoring_health` reads `degenerate_risk` post-hoc to fail loud when
    such a row reaches the audit table.
    """

    degenerate_risk: bool
    extreme_rr: bool
    risk_gross: float
    rr_raw: float


# SWI-358: diagnostic thresholds for geometry anomalies. Used by
# `compute_net_rr_diagnosed` and consumed by setup_calc / scoring_health
# for observability — these flags never reject a setup (binding user
# decision: surface visibility, do not block).
#
# - MIN_RISK_PCT: floor on `risk_gross / entry` below which risk is
#   considered degenerate (sub-microstructure noise for VN HOSE — ~5–10
#   ticks at typical large-cap prices).
# - EXTREME_RR_THRESHOLD: any raw R:R above this is suspicious and warrants
#   investigation (matches the SAB 2026-05-12 fingerprint where corrupted
#   units produced rr=609).
# - STRUCTURAL_ZERO_SIM: the sim_p_target value that indicates the audit
#   pipeline could not populate exit-sim probability.
MIN_RISK_PCT = 0.005
EXTREME_RR_THRESHOLD = 20.0
STRUCTURAL_ZERO_SIM = 0.0


def _compute_net_rr_core(
    entry: float,
    stop: float,
    target: float,
    cost_pct: float = 0.0,
) -> tuple[float, float, RRDiagnostics]:
    """Core R:R computation returning (rr_net, rr_gross, diagnostics).

    Geometry is the same as the public ``compute_net_rr`` — this function
    just exposes diagnostics so callers that want to surface anomalies
    (extreme R:R, degenerate risk denominators) can do so without
    re-implementing the cost arithmetic.

    Diagnostics:
        degenerate_risk: True when risk_gross / entry < MIN_RISK_PCT.
        extreme_rr:      True when raw rr_gross > EXTREME_RR_THRESHOLD.
        risk_gross:      Raw entry - stop (may be <= 0 for invalid geometry).
        rr_raw:          Raw reward/risk ratio prior to cost adjustment.
    """
    risk_gross = entry - stop
    reward_gross = target - entry
    rr_raw = (reward_gross / risk_gross) if risk_gross > 0 else 0.0
    degenerate_risk = bool(entry > 0 and 0 < risk_gross < entry * MIN_RISK_PCT)
    extreme_rr = bool(rr_raw > EXTREME_RR_THRESHOLD)
    diagnostics: RRDiagnostics = {
        "degenerate_risk": degenerate_risk,
        "extreme_rr": extreme_rr,
        "risk_gross": risk_gross,
        "rr_raw": rr_raw,
    }
    if risk_gross <= 0:
        return 0.0, 0.0, diagnostics

    half_cost = entry * cost_pct / 2
    risk_net = risk_gross + 2 * half_cost
    reward_net = reward_gross - 2 * half_cost

    rr_net = (reward_net / risk_net) if reward_net > 0 and risk_net > 0 else 0.0
    rr_gross = (reward_gross / risk_gross) if reward_gross > 0 else 0.0
    return rr_net, rr_gross, diagnostics


def compute_net_rr(
    entry: float,
    stop: float,
    target: float,
    cost_pct: float = 0.0,
) -> tuple[float, float]:
    """Return (rr_net, rr_gross) for an entry/stop/target triple.

    Both values are 0.0 when geometry is invalid (risk <= 0 or reward <= 0).
    Gates compare on ``rr_net``; ``rr_gross`` is for transparency only.

    Thin shim over ``_compute_net_rr_core`` — diagnostics discarded for
    backward compatibility with existing callers.
    """
    rr_net, rr_gross, _ = _compute_net_rr_core(entry, stop, target, cost_pct)
    return rr_net, rr_gross


def compute_net_rr_diagnosed(
    entry: float,
    stop: float,
    target: float,
    cost_pct: float = 0.0,
) -> tuple[float, float, RRDiagnostics]:
    """Same as ``compute_net_rr`` but also returns geometry diagnostics.

    See ``_compute_net_rr_core`` for the diagnostic dict shape.
    """
    return _compute_net_rr_core(entry, stop, target, cost_pct)


def compute_net_rr_only(
    entry: float,
    stop: float,
    target: float,
    cost_pct: float = 0.0,
) -> float | None:
    """Net-of-cost R:R only. Returns None when geometry is invalid.

    Use this when the gross value isn't needed (e.g., stretch-target hint).
    """
    rr_net, _ = compute_net_rr(entry, stop, target, cost_pct)
    return rr_net if rr_net > 0 else None
