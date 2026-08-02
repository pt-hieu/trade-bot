"""Single source of truth for the pipeline entry gate decision.

The entry gate determines whether new BUY entries are allowed for the day.
Two blocking conditions exist:
  1. Cash gate: early_mode != NORMAL (LOW_CASH or REALLOCATION)
  2. Regime gate: global_risk_regime == CRISIS

Two-phase lifecycle:
  - Pre-Phase1: call with early_mode only (regime unknown yet)
  - Post-Phase1: call with both (regime may override)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypedDict

from .catalyst_override import STACKED_POSITIVE_MIN_CATALYSTS

TradingMode = Literal["NORMAL", "LOW_CASH", "REALLOCATION"]
RiskRegime = Literal["CALM", "CAUTIOUS", "ELEVATED", "RISK_OFF", "CRISIS"]

# Catalyst boost cannot pull the effective per-ticker floor below this value.
# Even during a shock regime with a HIGH/POSITIVE catalyst, the minimum floor
# for catalyst-adjusted entries stays >= 2.5 so regime safety overrides
# catalyst enthusiasm. Only applied when an adjustment is active.
SHOCK_FLOOR_MINIMUM_RR: float = 2.5

BLOCKED_TRADING_MODES: frozenset[TradingMode] = frozenset({"LOW_CASH", "REALLOCATION"})


def is_trading_mode_healthy(mode: TradingMode | str) -> bool:
    """True when ``mode`` permits new entries on cash-availability grounds.

    Single source of truth for the cash-side mode predicate. Negation of
    ``BLOCKED_TRADING_MODES`` so adding a new blocked mode (e.g.
    ``CAUTIOUS``) flips every consumer at once.
    """
    return mode not in BLOCKED_TRADING_MODES


CRISIS_ENTRIES_BLOCKED_REASON = "NEW ENTRIES BLOCKED: CRISIS risk regime — defensive mode only"
LOW_CASH_ENTRIES_BLOCKED_REASON = "NEW ENTRIES BLOCKED: LOW_CASH — insufficient deployable capital"
REALLOCATION_ENTRIES_BLOCKED_REASON = (
    "NEW ENTRIES BLOCKED: REALLOCATION mode — must exit before entering"
)


@dataclass(frozen=True)
class EntryGateResult:
    """Result of entry gate evaluation."""

    entries_allowed: bool
    entries_blocked_reason: str | None


def determine_entry_gate(
    early_mode: str,
    global_risk_regime: str | None = None,
) -> EntryGateResult:
    """Evaluate whether new BUY entries are allowed.

    Args:
        early_mode: Trading mode from determine_mode().
        global_risk_regime: Risk regime from macro analysis. None pre-Phase1.

    Rules (priority order): CRISIS > REALLOCATION > LOW_CASH > allow.
    """
    if global_risk_regime == "CRISIS":
        return EntryGateResult(
            entries_allowed=False,
            entries_blocked_reason=CRISIS_ENTRIES_BLOCKED_REASON,
        )

    if early_mode == "REALLOCATION":
        return EntryGateResult(
            entries_allowed=False,
            entries_blocked_reason=REALLOCATION_ENTRIES_BLOCKED_REASON,
        )

    if early_mode == "LOW_CASH":
        return EntryGateResult(
            entries_allowed=False,
            entries_blocked_reason=LOW_CASH_ENTRIES_BLOCKED_REASON,
        )

    return EntryGateResult(entries_allowed=True, entries_blocked_reason=None)


class CandidateGateResult(TypedDict):
    """Outcome of a per-candidate R:R + sizing gate check."""

    passed: bool
    reason: str | None
    effective_rr_floor: float


# Stacked-shock relief floor cap. When a per-ticker stacked-shock signal
# fires (≥2 HIGH/MEDIUM POSITIVE catalysts on the ticker AND it is in the
# active geopolitical shock's `affected_tickers` list), the candidate's
# effective R:R floor caps at this value. Stays >= SHOCK_FLOOR_MINIMUM_RR
# so the regime-safety invariant is preserved — only the daily 3.0+ floor
# is relaxed, never below the 2.5 shock-only floor.
STACKED_SHOCK_RR_FLOOR_CAP: float = 3.0

# Sizing-floor multiplier when stacked-shock relief fires. Acknowledges
# the higher conviction (stacked positive catalysts) by allowing a smaller
# minimum position than the daily floor — but only on tickers the relief
# applies to. Other candidates same day still pay the full sizing floor.
STACKED_SHOCK_SIZING_MULTIPLIER: float = 0.75


def check_candidate_gate(
    trade_setup: dict,
    rr_floor: float,
    sizing_floor_vnd: int,
    *,
    catalyst_rr_adjustment: float = 0.0,
    stacked_shock_relief: bool = False,
) -> CandidateGateResult:
    """Per-candidate gate: setup validity, R:R floor, minimum position size.

    Used by morning's ``extract_top_picks`` (FIXED_TARGET branch) and intraday
    revision pick generation. The catalyst adjustment lets a HIGH/POSITIVE
    catalyst lower the floor for its affected tickers only — clamped to
    ``SHOCK_FLOOR_MINIMUM_RR`` so catalyst enthusiasm never undercuts regime
    safety. Morning callers pass ``adjustment=0`` and see identical behavior
    to the legacy inline ``chosen_rr < min_rr`` check.

    ``stacked_shock_relief`` (L2, 2026-04-27): when True (caller computed
    that the ticker is shock-affected AND has ≥2 HIGH/MEDIUM POSITIVE
    catalysts), the effective R:R floor caps at
    :data:`STACKED_SHOCK_RR_FLOOR_CAP` and the sizing floor is multiplied
    by :data:`STACKED_SHOCK_SIZING_MULTIPLIER`. Per-ticker ONLY — keeps the
    relief from leaking across the fleet. Other candidates same day still
    see the daily floor.
    """
    adjustment = max(0.0, catalyst_rr_adjustment or 0.0)
    effective_floor = (
        max(rr_floor - adjustment, SHOCK_FLOOR_MINIMUM_RR) if adjustment > 0 else rr_floor
    )
    effective_sizing_floor = sizing_floor_vnd
    if stacked_shock_relief:
        effective_floor = min(effective_floor, STACKED_SHOCK_RR_FLOOR_CAP)
        if sizing_floor_vnd > 0:
            effective_sizing_floor = int(sizing_floor_vnd * STACKED_SHOCK_SIZING_MULTIPLIER)

    if not trade_setup.get("valid"):
        reason_detail = trade_setup.get("error") or "valid=False"
        return CandidateGateResult(
            passed=False,
            reason=f"setup_invalid: {reason_detail}",
            effective_rr_floor=effective_floor,
        )

    # ATR_TRAIL setups have no fixed R:R — gating is performed upstream by
    # `apply_exit_strategy.rr_gate` against the trail anchor. Skip the floor
    # ONLY when the trailing intent is explicit via exit_family; do NOT
    # extend this to "missing target = trailing" — that would let any
    # malformed setup bypass the floor check.
    raw_rr = trade_setup.get("risk_reward")
    if trade_setup.get("exit_family") == "ATR_TRAIL":
        candidate_rr: float | None = None
    elif raw_rr is None:
        candidate_rr = 0.0
    else:
        candidate_rr = float(raw_rr)
    if candidate_rr is not None and candidate_rr < effective_floor:
        return CandidateGateResult(
            passed=False,
            reason=f"rr_below_floor: {candidate_rr:.2f} < {effective_floor:.2f}",
            effective_rr_floor=effective_floor,
        )

    if effective_sizing_floor > 0:
        position_vnd = trade_setup.get("position_vnd") or 0
        if position_vnd < effective_sizing_floor:
            return CandidateGateResult(
                passed=False,
                reason=f"position_below_sizing_floor: {position_vnd} < {effective_sizing_floor}",
                effective_rr_floor=effective_floor,
            )

    return CandidateGateResult(passed=True, reason=None, effective_rr_floor=effective_floor)


def is_stacked_shock_relief(
    ticker: str,
    shock_affected: frozenset[str] | set[str],
    high_positive_count: Mapping[str, int],
) -> bool:
    """Per-ticker flag: ticker is shock-affected AND has ≥2 HIGH/MEDIUM POSITIVE catalysts.

    Shared between morning's `extract_top_picks` and revision's
    `generate_revision_picks` so the stacked-shock relief criteria stay
    in lockstep across the two pick paths. Caller pre-computes
    `shock_affected` (via :func:`shared.rules.geopolitical.derive_shock_affected_tickers`)
    and `high_positive_count` (via :func:`shared.rules.catalyst_override.count_high_positive_per_ticker`)
    once before iterating candidates so this stays O(1) per ticker.
    """
    return (
        ticker in shock_affected
        and high_positive_count.get(ticker, 0) >= STACKED_POSITIVE_MIN_CATALYSTS
    )
