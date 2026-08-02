"""Expectancy-driven R:R floor.

Pure deterministic Python. No async, no DB, no LLM. Used by the validator
gate to demand higher R:R when historical win rate is low.

Theory (Van Tharp R-multiples): expectancy E = win_rate × avg_win_R −
loss_rate × |avg_loss_R|. Standard assumption avg_loss_R ≈ 1.0 (stops are
the unit of loss), so the equation collapses to:

    E ≥ target → win_rate × min_rr − (1 − win_rate) ≥ target
                → min_rr ≥ (target + 1 − win_rate) / win_rate

For target = 0.3R per trade (≈ 30% edge), low win rates demand much higher
R:R to stay positive in expectation.

Stratified floors
-----------------
FIXED_TARGET and ATR_TRAIL exit families have different expected win-rate
profiles — TREND recs are rare high-magnitude winners; MEAN_REVERSION recs
are frequent small winners. A single rolling floor under-penalises a cold
TF streak while over-penalising MR churn (or vice-versa).
``compute_family_expectancy_floors`` returns a per-family mapping so
``get_rr_floor`` can pick the right cohort for the rec being validated.
"""

from __future__ import annotations

from typing import Literal, TypedDict

# Minimum expectancy in R-multiples we demand from new entries
_TARGET_EXPECTANCY_R = 0.3

# Hard lower bound — even at 100% win rate, we still want some asymmetry
_FLOOR_FLOOR = 2.0

# Fail-closed default when win-rate data is missing or zero.
#
# Public sentinel — downstream code (recommendation_gate.Rule 5a) needs
# to distinguish the fail-closed placeholder value from real observed
# expectancy floors. Exporting instead of duplicating the literal keeps
# the safety default single-sourced.
FAIL_CLOSED_FLOOR = 4.0


ExitFamilyName = Literal["FIXED_TARGET", "ATR_TRAIL"]


class FamilyExpectancyFloors(TypedDict):
    """Rolling-expectancy floor per exit family."""

    FIXED_TARGET: float
    ATR_TRAIL: float


def is_fail_closed_placeholder(value: float | None) -> bool:
    """True when ``value`` is the fail-closed sentinel (no real observation).

    Downstream gates (recommendation_gate.Rule 5a) treat values at or above
    ``FAIL_CLOSED_FLOOR`` as the cold-start placeholder rather than an
    observed expectancy/family signal, so they can be safely excluded from
    catalyst-relief caps.
    """
    if value is None:
        return True
    return value >= FAIL_CLOSED_FLOOR


def compute_expectancy_floor(win_rate: float | None) -> float:
    """Return min R:R such that expectancy ≥ ``_TARGET_EXPECTANCY_R``.

    Args:
        win_rate: Rolling win rate as a fraction in [0, 1]. ``None`` or 0
            triggers the fail-closed default (high floor) — never trust an
            unknown distribution.

    Returns:
        Minimum required R:R, never below ``_FLOOR_FLOOR``.
    """
    if win_rate is None or win_rate <= 0:
        return FAIL_CLOSED_FLOOR
    if win_rate >= 1.0:
        return _FLOOR_FLOOR

    raw = (_TARGET_EXPECTANCY_R + 1.0 - win_rate) / win_rate
    return max(_FLOOR_FLOOR, raw)


def compute_family_expectancy_floors(
    mr_win_rate: float | None,
    tf_win_rate: float | None,
) -> FamilyExpectancyFloors:
    """Return exit-family-stratified floors.

    Callers that have family-specific rolling win rates (populated by the
    retrospective pipeline from ``daily_evaluations.strategy``) should pass
    both. Falls back to the fail-closed floor per family when one side has
    no samples — the other family's floor is unaffected.
    """
    return FamilyExpectancyFloors(
        FIXED_TARGET=compute_expectancy_floor(mr_win_rate),
        ATR_TRAIL=compute_expectancy_floor(tf_win_rate),
    )
