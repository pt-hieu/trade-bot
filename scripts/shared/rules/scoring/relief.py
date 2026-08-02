"""Regime-relief eligibility predicate — mirror of composer Rule 5a.

Per /challenge round-3: includes ``candidate_risk_reward >= RR_FLOOR_ELEVATED``
so the scoring suppressor cannot admit candidates the production composer
Rule 5a (``recommendation_gate.py:335``) would reject under its
``max(RR_FLOOR_ELEVATED, exp_signal, fam_signal)`` floor cap.
"""

from __future__ import annotations

from typing import Final, TypedDict

from ..rr_floors import RR_FLOOR_ELEVATED

# Mirrors recommendation_gate.py:_STRESSED_REGIMES + Rule 5a's
# MIN_BULLISH_BELIEFS_FOR_RELIEF threshold (line 65).
_STRESSED_REGIMES: Final[frozenset[str]] = frozenset({"ELEVATED", "RISK_OFF"})
_MIN_BULLISH_BELIEFS_FOR_RELIEF: Final[int] = 2


class ReliefContext(TypedDict, total=False):
    """Inputs used by :func:`is_regime_relief_eligible`.

    Mirrors the predicate at ``recommendation_gate.py:316-321`` plus the
    v4 ``candidate_risk_reward >= RR_FLOOR_ELEVATED`` guard.
    """

    underlying_stress: bool
    shock_active: bool
    has_high_positive_macro_catalyst: bool
    has_candidate_positive_catalyst: bool
    bullish_sector_belief_count: int
    candidate_risk_reward: float


def is_regime_relief_eligible(
    regime: str,
    relief_context: ReliefContext,
) -> tuple[bool, str | None]:
    """Mirror of ``recommendation_gate.py:316-321`` Rule 5a, with v4 RR floor.

    Returns ``(eligible, block_reason)``. When ``eligible=False``,
    ``block_reason`` cites the first failed predicate so audit rows can
    explain *why* the suppressor did not fire.

    Predicates (all required):
      - regime ∈ {ELEVATED, RISK_OFF}
      - underlying_stress OR shock_active
      - has_high_positive_macro_catalyst OR has_candidate_positive_catalyst
      - bullish_sector_belief_count >= MIN_BULLISH_BELIEFS_FOR_RELIEF (2)
      - candidate_risk_reward >= RR_FLOOR_ELEVATED (3.0)  [v4 round-3]
    """
    if regime not in _STRESSED_REGIMES:
        return False, "regime_not_stressed"

    underlying = bool(relief_context.get("underlying_stress"))
    shock = bool(relief_context.get("shock_active"))
    if not (underlying or shock):
        return False, "no_underlying_or_shock"

    macro_cat = bool(relief_context.get("has_high_positive_macro_catalyst"))
    candidate_cat = bool(relief_context.get("has_candidate_positive_catalyst"))
    if not (macro_cat or candidate_cat):
        return False, "no_positive_catalyst"

    beliefs = int(relief_context.get("bullish_sector_belief_count") or 0)
    if beliefs < _MIN_BULLISH_BELIEFS_FOR_RELIEF:
        return False, f"insufficient_bullish_beliefs_{beliefs}_lt_{_MIN_BULLISH_BELIEFS_FOR_RELIEF}"

    candidate_rr = float(relief_context.get("candidate_risk_reward") or 0.0)
    if candidate_rr < RR_FLOOR_ELEVATED:
        return False, f"candidate_rr_{candidate_rr:.2f}_below_floor_{RR_FLOOR_ELEVATED:.1f}"

    return True, None
