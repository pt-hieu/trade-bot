"""Tuning constants for belief aggregation.

Values were tuned against the 2026-04-14 positions_* calibration data.
`sector_aggregator.yaml` worked example must mirror the dissent floors —
the LLM-generated and Python-deterministic paths must agree.
"""

from __future__ import annotations

from agents.belief_models import BASE_RATE_BEAR, BASE_RATE_BULL, BASE_RATE_NEUTRAL

# Fallback base rates for tests / fresh envs. Production overrides via
# compute_empirical_base_rates() from belief_queries when wiring the
# anchor; this dict bootstraps the module-load path.
FALLBACK_BASE_RATES = {
    "BULLISH": BASE_RATE_BULL,
    "NEUTRAL": BASE_RATE_NEUTRAL,
    "BEARISH": BASE_RATE_BEAR,
}

# Three distinct calibration mechanisms — distinguish when auditing weight:
#   1. Aggregator double-counting filter (`shared/rules/belief_calibration_exemption.py`)
#      runs BEFORE aggregation; aggregator beliefs never reach the sigmoid.
#   2. Brier down-weight threshold (below) — anchored to "worse than emitting
#      base rates verbatim". Reduction: `(brier - threshold)/0.4 * sigmoid(scored-18)`.
#   3. Cold-start floor (`MIN_SCORED_SOFT_FLOOR`) — sigmoid returns 1.0 when
#      scored < 18 regardless of brier.
from ._anchors import uninformed_brier_anchor  # noqa: E402

# Production rebinds the runtime anchor each scan via
# ``set_runtime_base_rates(empirical_rates)`` from ``phase_beliefs``.
# Consumers MUST read through ``current_brier_down_weight_threshold()``
# so the rebind takes effect at every call site.
BRIER_DOWN_WEIGHT_THRESHOLD = uninformed_brier_anchor(FALLBACK_BASE_RATES)

_CACHED_THRESHOLD: float = BRIER_DOWN_WEIGHT_THRESHOLD


def current_brier_down_weight_threshold() -> float:
    """Return the live Brier down-weight threshold (cached; rebind via setter)."""
    return _CACHED_THRESHOLD


def set_runtime_base_rates(rates: dict[str, float]) -> None:
    """Bind empirical base rates and refresh anchor-derived runtime values.

    Rebinds the Brier down-weight threshold AND the dissent-preservation
    floors/gate so all anchor-derived knobs move together (SWI-122).
    """
    global _CACHED_THRESHOLD
    global _runtime_dissent_bull_floor, _runtime_dissent_conv_floor, _runtime_dissent_agg_gate
    anchor = uninformed_brier_anchor(rates)
    _CACHED_THRESHOLD = anchor
    _runtime_dissent_bull_floor = round(_FLOOR_RATIO * anchor, 4)
    _runtime_dissent_conv_floor = _runtime_dissent_bull_floor
    _runtime_dissent_agg_gate = round(_GATE_RATIO * anchor, 4)


# Joint-pool eligibility threshold — pooling has different semantics from
# down-weighting (informative iff all members are bad enough), so the
# snapshot 0.65 stays.
BRIER_JOINT_POOL_THRESHOLD = 0.65

# Cold-start safety floor. Must equal _CALIBRATION_SIGMOID_MIDPOINT so
# agents crossing the floor don't hit a 100% → 82% cliff in a single step.
MIN_SCORED_SOFT_FLOOR = 18

# Sigmoid centered at 18, scale 4: weight halved at scored=18, near-zero
# (<5%) at scored=30.
_CALIBRATION_SIGMOID_MIDPOINT = 18
_CALIBRATION_SIGMOID_SCALE = 4

# Dissent preservation: lift a high-conviction directional view toward
# the aggregated probability when the weighted mean would flatten to
# NEUTRAL. Floors derived from the uninformed-Brier anchor so they track
# the empirical base-rate distribution (SWI-122) — module-load fallback
# values shown below seed before runtime rates bind.
_FLOOR_RATIO = 0.95  # dissent floor sits 95% of anchor — close to gate without falling below
_GATE_RATIO = 0.85
_FALLBACK_DISSENT_BULL_FLOOR = round(_FLOOR_RATIO * uninformed_brier_anchor(FALLBACK_BASE_RATES), 4)
_FALLBACK_DISSENT_CONV_FLOOR = _FALLBACK_DISSENT_BULL_FLOOR
_FALLBACK_DISSENT_AGG_GATE = round(_GATE_RATIO * uninformed_brier_anchor(FALLBACK_BASE_RATES), 4)

# Mutable runtime values rebound by ``set_runtime_base_rates``.
_runtime_dissent_bull_floor: float = _FALLBACK_DISSENT_BULL_FLOOR
_runtime_dissent_conv_floor: float = _FALLBACK_DISSENT_CONV_FLOOR
_runtime_dissent_agg_gate: float = _FALLBACK_DISSENT_AGG_GATE


def current_dissent_thresholds() -> tuple[float, float, float]:
    """Live (bull_floor, conv_floor, agg_gate) tuple — anchor-relative.

    Single getter so callers read all three values in lock-step. Avoids the
    drift hazard of three siblings calling three setters across pipeline
    runs. ``set_runtime_base_rates`` rebinds all three together (SWI-122).
    """
    return (
        _runtime_dissent_bull_floor,
        _runtime_dissent_conv_floor,
        _runtime_dissent_agg_gate,
    )


# Preserved value lands within 5 points of the dissenter so the downstream
# base-rate anchor still has a nudging effect. Intentionally absolute (not
# anchor-relative): the 5pt nudge encodes a calibration ergonomic, not a
# distributional property.
DISSENT_PRESERVATION_RELAX = 0.05
