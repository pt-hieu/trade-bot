"""R:R floor constants and regime-based floor computation.

Used by recommendation_validator as the final enforcement gate.
Constraint composition logic lives in shared/rules/constraints.py.

Exit-family stratification: ``get_rr_floor`` accepts an optional ``strategy``
argument so callers route to the right per-family expectancy cohort. When
``strategy`` omits or resolves to FIXED_TARGET, behavior is byte-identical
to the pre-refactor path.
"""

from __future__ import annotations

from .exit_strategy import resolve_exit_strategy
from .expectancy import FamilyExpectancyFloors

RR_FLOOR_DEFAULT = 2.0
RR_FLOOR_ELEVATED = 3.0
RR_FLOOR_CRISIS = 4.5

# Display threshold: R:R values within this distance of an active floor are
# rendered at 2 decimals so auditors can see narrow gate clearances.
BORDERLINE_RR_EPSILON = 0.1


def get_rr_floor(
    global_risk_regime: str,
    min_rr: float,
    expectancy_floor: float | None = None,
    strategy: str | None = None,
    family_floors: FamilyExpectancyFloors | None = None,
) -> float:
    """Higher-risk regimes demand higher R:R to justify entry.

    Args:
        global_risk_regime: Risk regime from macro analysis.
        min_rr: Minimum R:R from goal urgency.
        expectancy_floor: Optional rolling-win-rate-derived floor (unified).
            Kept for backward compatibility. If ``family_floors`` is also
            supplied, the family-specific entry for the resolved family
            takes precedence.
        strategy: Strategy label (TREND, MEAN_REVERSION, ...). Used to
            resolve the exit family and route to ``family_floors`` when
            present. Omitting this argument preserves pre-refactor behavior.
        family_floors: Per-family floors produced by
            ``shared.rules.expectancy.compute_family_expectancy_floors``.

    Returns:
        Effective R:R floor — entries below this are rejected.
    """
    effective_expectancy = expectancy_floor or 0.0
    if family_floors is not None:
        family = resolve_exit_strategy(strategy).name
        effective_expectancy = max(effective_expectancy, family_floors[family])

    base = max(min_rr, RR_FLOOR_DEFAULT, effective_expectancy)
    if global_risk_regime in ("RISK_OFF", "ELEVATED"):
        return max(base, RR_FLOOR_ELEVATED)
    if global_risk_regime == "CRISIS":
        return max(base, RR_FLOOR_CRISIS)
    return base
