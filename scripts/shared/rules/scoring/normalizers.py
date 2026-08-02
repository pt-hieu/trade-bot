"""Per-feature normalizers — all 0-1 mapping math for scoring inputs.

Pure-Python; no async/DB/LLM. Each ``_normalize_*`` function maps a raw
feature value to a [0, 1] float, with NaN/None guards. ``_NORMALIZERS``
is the registry consumed by :func:`compute_score` in the package root.
"""

from __future__ import annotations

import math
from typing import Final, TypedDict


class CatalystStrengthInputs(TypedDict, total=False):
    """Inputs for catalyst-strength feature normalization."""

    has_high_positive: bool
    has_medium_positive: bool
    has_negative: bool


class ScoreInputs(TypedDict, total=False):
    """Raw feature values fed to :func:`compute_score`.

    All fields optional so callers can score partial candidates (e.g. a
    setup_invalid drop has no setup-derived fields). Missing fields are
    treated as 0.0 by :func:`_normalize_feature` — the resulting score is
    a deterministic lower bound on the candidate's strength.
    """

    risk_reward: float
    sim_p_target: float
    sim_p_stop: float
    sim_ev: float
    strategy_confidence: float
    belief_conviction: float
    catalyst_strength: float | CatalystStrengthInputs
    bullish_sector_belief_count: int
    total_sector_count: int
    rs_20d: float
    volume_vs_avg: float
    trend_alignment: str
    foreign_net_strength: float
    # SWI-305: weight dropped in v2.1.0; column retained in
    # pre_gate_candidates for v2.0.0 historical replay. Ignored by
    # compute_score (not in _NORMALIZERS, weight not in YAML).
    order_imbalance: float


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalize_risk_reward(rr: float) -> float:
    """sqrt-normalize R:R to cap leverage of 10:1 outliers.

    sqrt(rr / 10.0), clamped to [0,1]. R:R=10 → 1.0; R:R=2.5 → 0.5;
    R:R=1 → 0.316. The sqrt curve favors the 2-4 zone (where most
    survivable setups land) without the high-end going superlinear.
    """
    if rr is None or rr <= 0 or math.isnan(rr):
        return 0.0
    return _clamp(math.sqrt(rr / 10.0), 0.0, 1.0)


def _normalize_passthrough(value: float) -> float:
    """Already-normalized [0,1] features pass through with NaN/None guards."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0.0
    return _clamp(float(value), 0.0, 1.0)


def _normalize_inverted(value: float) -> float:
    """Invert a [0,1] feature so lower input → higher score (e.g. p_stop)."""
    return _clamp(1.0 - _normalize_passthrough(value), 0.0, 1.0)


def _normalize_sim_ev(value: float) -> float:
    """Clip to [-0.5, 1.0], shift to [0, 1]. EV is in raw return-pct units.

    The simulator emits sim_ev as a percentage return (e.g. 5.0 → +5%).
    Clip to [-50%, +100%] then linearly map: -50% → 0, 100% → 1.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0.0
    pct = float(value) / 100.0  # convert % → fraction
    clipped = _clamp(pct, -0.5, 1.0)
    return (clipped + 0.5) / 1.5


def _normalize_catalyst_strength(value: float | CatalystStrengthInputs | None) -> float:
    """HIGH_POSITIVE=1.0, MEDIUM_POSITIVE=0.6, NEUTRAL=0, NEGATIVE clipped to 0.

    Accepts either a pre-normalized float in [0,1] or a CatalystStrengthInputs
    dict. NEGATIVE only fires when no positive present.
    """
    if value is None:
        return 0.0
    if isinstance(value, dict):
        if value.get("has_high_positive"):
            return 1.0
        if value.get("has_medium_positive"):
            return 0.6
        if value.get("has_negative"):
            return 0.0
        return 0.0
    return _normalize_passthrough(value)


def _normalize_bullish_count(count: int, total: int) -> float:
    """Normalize bullish-sector count by total active sectors."""
    if total <= 0:
        return 0.0
    return _clamp(count / total, 0.0, 1.0)


def _normalize_rs_20d(value: float) -> float:
    """Clip rs_20d to [0.7, 1.4], linear map to [0, 1]."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0.0
    clipped = _clamp(float(value), 0.7, 1.4)
    return (clipped - 0.7) / 0.7


def _normalize_volume_vs_avg(value: float) -> float:
    """Clip volume_vs_avg to [0.5, 3.0], linear map to [0, 1]."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0.0
    clipped = _clamp(float(value), 0.5, 3.0)
    return (clipped - 0.5) / 2.5


def _normalize_trend_alignment(label: str | None) -> float:
    """UPTREND=1.0, SIDEWAYS=0.5, DOWNTREND=0.0, unknown→0."""
    if not label:
        return 0.0
    upper = label.upper()
    if upper == "UPTREND":
        return 1.0
    if upper == "SIDEWAYS":
        return 0.5
    return 0.0


def _normalize_foreign_net(value: float) -> float:
    """Sigmoid-normalize foreign net (in VND).

    Centred at 0; saturates near ±50B (each unit-billion adds ~10% of the
    sigmoid range). Negative net → score < 0.5; positive → > 0.5.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0.5  # neutral when missing
    billion = float(value) / 1e9
    return 1.0 / (1.0 + math.exp(-billion / 10.0))


_NORMALIZERS: Final[dict[str, object]] = {
    "risk_reward": _normalize_risk_reward,
    "sim_p_target": _normalize_passthrough,
    "sim_p_stop": _normalize_inverted,
    "sim_ev": _normalize_sim_ev,
    "strategy_confidence": _normalize_passthrough,
    "belief_conviction": _normalize_passthrough,
    "catalyst_strength": _normalize_catalyst_strength,
    "rs_20d": _normalize_rs_20d,
    "volume_vs_avg": _normalize_volume_vs_avg,
    "trend_alignment": _normalize_trend_alignment,
    "foreign_net_strength": _normalize_foreign_net,
    # bullish_sector_belief_count handled inline in compute_score
    # (needs total_sector_count companion field).
}
