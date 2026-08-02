"""Recommendation-gate composer — single source of truth.

Composes trading-mode, regime, urgency, retro, streak, expectancy, and
structural-fallback inputs into ONE `RecommendationGateDecision` consumed
by the validator, the brief renderer, and the picks writer. Replaces the
previously scattered authority over "today's R:R floor" (see
`research/rr-floor-audit-2026-04-20.md` for the pre-consolidation map).

Pure deterministic Python. No async, no DB, no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .entry_gates import (
    BLOCKED_TRADING_MODES,
    CRISIS_ENTRIES_BLOCKED_REASON,
    LOW_CASH_ENTRIES_BLOCKED_REASON,
    REALLOCATION_ENTRIES_BLOCKED_REASON,
    RiskRegime,
    TradingMode,
)
from .exit_strategy import resolve_exit_strategy
from .expectancy import is_fail_closed_placeholder
from .rr_floors import RR_FLOOR_CRISIS, RR_FLOOR_DEFAULT, RR_FLOOR_ELEVATED

if TYPE_CHECKING:
    from .expectancy import FamilyExpectancyFloors

# Shock-only floor: applied when the regime is pinned to ELEVATED/RISK_OFF
# by a geopolitical phase but the underlying VIX/DXY/USD-VND indicators are
# calm. Prevents the full 3.0 floor from suppressing every entry on days
# like 2026-04-20 where a stale shock floor masked a broad VN rally.
RR_FLOOR_SHOCK_ONLY = 2.5

_STRESSED_REGIMES: frozenset[str] = frozenset({"ELEVATED", "RISK_OFF"})

# Streak-aware floor relaxation — fires when a ≥3-day 0-BUY streak is
# attributed to the R:R gate. Graduated cap:
#   3-6 days  → base relax    (rr_floor: -0.5, mixed: -0.25)
#   7-9 days  → double relax  (rr_floor: -1.0, mixed: -0.5) + streak_escalation
#   10+ days  → structural    (no auto-relax; emits streak_structural_review)
# Fail-closed when profile is `regime_gated` / `belief_flattening` / missing.
_STREAK_MIN_LENGTH_FOR_RELAX = 3
_STREAK_ESCALATION_LENGTH = 7
_STREAK_STRUCTURAL_LENGTH = 10
_STREAK_RR_FLOOR_RELAX = 0.5
_STREAK_MIXED_RELAX = 0.25

# Rule 5a threshold — minimum bullish sector beliefs (direction=BULLISH)
# required alongside a positive catalyst signal to cap the stressed-regime
# R:R floor at RR_FLOOR_ELEVATED. 2+ beliefs mean the sector consensus is
# not single-source; below that we fail-closed at the stressed floor.
MIN_BULLISH_BELIEFS_FOR_RELIEF = 2


TRADING_MODE_BLOCK_REASONS: dict[str, str] = {
    "LOW_CASH": LOW_CASH_ENTRIES_BLOCKED_REASON,
    "REALLOCATION": REALLOCATION_ENTRIES_BLOCKED_REASON,
}
REGIME_BLOCK_REASON_CRISIS = CRISIS_ENTRIES_BLOCKED_REASON
STRATEGY_FAILED_BLOCK_REASON = "NEW ENTRIES BLOCKED: strategy_director_failed under stressed regime"


@dataclass(frozen=True)
class RecommendationGateDecision:
    """Composed decision for today's recommendation production.

    Every downstream consumer (validator, brief renderer, picks writer)
    MUST read from this single object. Audit trail (`applied_rules`) is
    persisted into `daily_records.gate_decision_json` so SQL post-hoc
    review can show *which* rules mutated state on any given day.
    """

    effective_rr_floor: float
    max_new_entries: int
    entries_allowed: bool
    entries_blocked_reason: str | None
    applied_rules: tuple[str, ...]
    inputs_digest: dict[str, object] = field(default_factory=dict)
    # Floor applied to non-beneficiary entries during an active geopolitical-shock
    # phase. When no shock is active this mirrors `effective_rr_floor` so downstream
    # interpolation always has a non-None value. Replaces the prior hardcoded
    # `R:R >= 4.0` literal in entry_strategist.yaml (MON-2026-04-21, Fix 3).
    shock_rr_floor: float = RR_FLOOR_SHOCK_ONLY

    def to_jsonb(self) -> dict[str, object]:
        """Serialize for `daily_records.gate_decision_json` persistence."""
        return {
            "effective_rr_floor": self.effective_rr_floor,
            "max_new_entries": self.max_new_entries,
            "entries_allowed": self.entries_allowed,
            "entries_blocked_reason": self.entries_blocked_reason,
            "applied_rules": list(self.applied_rules),
            "inputs_digest": dict(self.inputs_digest),
            "shock_rr_floor": self.shock_rr_floor,
        }


def _base_floor(
    urgency_min_rr: float,
    expectancy_floor: float | None,
    strategy: str | None,
    family_floors: FamilyExpectancyFloors | None,
) -> float:
    """Compute base floor from urgency, default, expectancy, and family floors."""
    effective_expectancy = expectancy_floor or 0.0
    if family_floors is not None:
        family_name = resolve_exit_strategy(strategy).name
        effective_expectancy = max(effective_expectancy, family_floors[family_name])
    return max(urgency_min_rr, RR_FLOOR_DEFAULT, effective_expectancy)


def _regime_boost(
    current_floor: float,
    global_risk_regime: str,
    underlying_stress: bool,
) -> tuple[float, str | None]:
    """Apply regime-aware floor raise. Returns (new_floor, rule_fired)."""
    if global_risk_regime == "CRISIS":
        return max(current_floor, RR_FLOOR_CRISIS), "regime_boost_crisis"
    if global_risk_regime in _STRESSED_REGIMES:
        if underlying_stress:
            return max(current_floor, RR_FLOOR_ELEVATED), "regime_boost_elevated_stressed"
        return max(current_floor, RR_FLOOR_SHOCK_ONLY), "regime_boost_elevated_shock_only"
    return current_floor, None


def _streak_relaxation(
    current_floor: float,
    streak_alert: dict | None,
    *,
    has_high_positive_macro_catalyst: bool = False,
    cash_healthy: bool = False,
) -> tuple[float, tuple[str, ...]]:
    """Relax floor when a 0-BUY streak is attributed to the R:R gate.

    Returns (new_floor, rules_fired). `rules_fired` carries either the
    relax rule alone, or paired with `streak_escalation` (7-9d) or
    `streak_structural_review` (10+d).

    `has_high_positive_macro_catalyst` flips `belief_flattening` /
    `regime_gated` to `rr_floor` so the relax staircase fires (AUDIT-
    2026-04-24-001). Single rule fires, profile-gate invariant preserved.
    """
    if not streak_alert:
        return current_floor, ()
    length = int(streak_alert.get("length") or 0)
    if length < _STREAK_MIN_LENGTH_FOR_RELAX:
        return current_floor, ()
    profile = streak_alert.get("gate_profile") or ""
    flipped_from_belief_flattening = False
    if has_high_positive_macro_catalyst and profile in ("belief_flattening", "regime_gated"):
        profile = "rr_floor"
    elif cash_healthy and length >= _STREAK_ESCALATION_LENGTH and profile == "belief_flattening":
        # 7+d belief_flattening + healthy cash: flip + soft-tier (flag
        # holds multiplier at 1.0 so day-1 delta stays 0.5).
        profile = "rr_floor"
        flipped_from_belief_flattening = True
    if profile not in ("rr_floor", "mixed"):
        return current_floor, ()

    # 10+ days → structural; do NOT auto-relax. Surface the rule so the
    # audit trail (daily_records.gate_decision_json) shows the escalation
    # and downstream streak-alert consumers can route to human triage.
    if length >= _STREAK_STRUCTURAL_LENGTH:
        return current_floor, ("streak_structural_review",)

    # 7-9 days → double the base relax amount. Fail-closed bounds remain
    # RR_FLOOR_DEFAULT (low) and RR_FLOOR_ELEVATED (high).
    is_escalation = length >= _STREAK_ESCALATION_LENGTH and not flipped_from_belief_flattening
    multiplier = 2.0 if is_escalation else 1.0
    if profile == "rr_floor":
        delta = _STREAK_RR_FLOOR_RELAX * multiplier
        relax_rule = "streak_relax_rr_floor"
    else:
        delta = _STREAK_MIXED_RELAX * multiplier
        relax_rule = "streak_relax_mixed"
    new_floor = max(RR_FLOOR_DEFAULT, current_floor - delta)
    new_floor = min(new_floor, RR_FLOOR_ELEVATED)
    rules: tuple[str, ...] = (relax_rule, "streak_escalation") if is_escalation else (relax_rule,)
    return new_floor, rules


def compose_recommendation_gate(
    *,
    trading_mode: TradingMode | str,
    market_regime: str,
    global_risk_regime: RiskRegime | str,
    urgency_tier: str,
    urgency_min_rr: float,
    urgency_max_picks: int,
    underlying_stress: bool,
    strategy_director_failed: bool = False,
    retro_min_rr_override: float | None = None,
    retro_max_entries: int | None = None,
    expectancy_floor: float | None = None,
    family_floors: FamilyExpectancyFloors | None = None,
    streak_alert: dict | None = None,
    strategy: str | None = None,
    has_high_positive_macro_catalyst: bool = False,
    bullish_sector_belief_count: int = 0,
    has_candidate_positive_catalyst: bool = False,
    shock_active: bool = False,
    cash_healthy: bool = False,
) -> RecommendationGateDecision:
    """Compose today's recommendation gate.

    Rule order (deterministic, audit-logged):
      1. cash-gate block (LOW_CASH / REALLOCATION)
      2. regime-gate block (CRISIS)
      3. structural block (strategy director failed in stressed regime)
      4. base floor (urgency ∨ default ∨ expectancy ∨ family)
      5. regime boost (ELEVATED/RISK_OFF → 2.5 shock-only or 3.0 stressed; CRISIS → 4.5)
      6. retro override (anti-death-spiral min)
      7. streak-profile relaxation (rr_floor / mixed)
      8. circuit-breaker max_entries floor
      9. catalyst + sector-belief relief (Rule 5a — placed LAST so legitimate
         retro/streak downward adjustments fire first; excludes fail-closed
         placeholder expectancy/family signals from the cap so cold-start
         4.0 defaults don't mask the catalyst relief)
    """
    applied: list[str] = []

    # Start with composed entries count — retro max_entries takes MAX (anti-death-spiral).
    max_entries = urgency_max_picks
    if retro_max_entries is not None:
        max_entries = max(max_entries, retro_max_entries)
        applied.append("retro_max_entries")

    # ── Rule 1: trading-mode block ─────────────────────────────────
    if trading_mode in BLOCKED_TRADING_MODES:
        applied.append(f"trading_mode_block_{trading_mode.lower()}")
        return _blocked(
            reason=TRADING_MODE_BLOCK_REASONS[trading_mode],
            applied=applied,
            inputs_digest=_digest(locals()),
        )

    # ── Rule 2: regime-gate block ──────────────────────────────────
    if global_risk_regime == "CRISIS":
        applied.append("regime_block_crisis")
        return _blocked(
            reason=REGIME_BLOCK_REASON_CRISIS,
            applied=applied,
            inputs_digest=_digest(locals()),
        )

    # ── Rule 3: structural block ───────────────────────────────────
    if strategy_director_failed and global_risk_regime in (
        *_STRESSED_REGIMES,
        "CRISIS",
    ):
        applied.append("strategy_director_failed_stressed")
        return _blocked(
            reason=STRATEGY_FAILED_BLOCK_REASON,
            applied=applied,
            inputs_digest=_digest(locals()),
        )

    # ── Rule 4: base floor ─────────────────────────────────────────
    floor = _base_floor(
        urgency_min_rr=urgency_min_rr,
        expectancy_floor=expectancy_floor,
        strategy=strategy,
        family_floors=family_floors,
    )
    applied.append("base_floor")

    # ── Rule 5: regime boost ───────────────────────────────────────
    boosted, boost_rule = _regime_boost(floor, global_risk_regime, underlying_stress)
    if boost_rule is not None:
        floor = boosted
        applied.append(boost_rule)

    # ── Rule 6: retro override ─────────────────────────────────────
    if retro_min_rr_override is not None:
        floor = min(floor, float(retro_min_rr_override))
        applied.append("retro_min_rr_override")

    # ── Rule 7: streak-profile relaxation ──────────────────────────
    relaxed, relax_rules = _streak_relaxation(
        floor,
        streak_alert,
        has_high_positive_macro_catalyst=has_high_positive_macro_catalyst,
        cash_healthy=cash_healthy,
    )
    if relax_rules:
        floor = relaxed
        applied.extend(relax_rules)

    # ── Rule 8: circuit-breaker max_entries floor ──────────────────
    max_entries = max(max_entries, 1)
    applied.append("circuit_breaker_max_entries")

    # ── Rule 5a: catalyst + sector-belief relief under stressed regime ─
    # Placed LAST so retro_override + streak_relaxation legitimate downward
    # adjustments fire first. Cap uses ``max(RR_FLOOR_ELEVATED, observed-
    # expectancy, observed-family)`` — fail-closed placeholder values
    # (>= FAIL_CLOSED_FLOOR) are excluded so cold-start 4.0 defaults don't
    # mask the catalyst relief. Observed expectancy/family (real computed
    # signals) still preserved. Never fires under CRISIS (Rule 2 blocks).
    #
    # L3 (2026-04-27): the guard widens from `underlying_stress` alone to
    # `(underlying_stress OR shock_active)`. On shock-pinned-regime +
    # calm-VIX days the underlying VIX/DXY signals are False but a
    # geopolitical shock is still pinning the regime to ELEVATED — without
    # the OR, Rule 5a never fires regardless of catalyst/belief state.
    # `shock_active` is sourced from `geopolitical_shock.phase_name in
    # ACTIVE_SHOCK_PHASES` and is a real composer kwarg threaded into the
    # digest so `recompose_for_strategy_failure` round-trips it.
    if (
        global_risk_regime in _STRESSED_REGIMES
        and (underlying_stress or shock_active)
        and (has_high_positive_macro_catalyst or has_candidate_positive_catalyst)
        and bullish_sector_belief_count >= MIN_BULLISH_BELIEFS_FOR_RELIEF
    ):
        exp_signal = (
            0.0 if is_fail_closed_placeholder(expectancy_floor) else float(expectancy_floor or 0.0)
        )

        fam_signal = 0.0
        if family_floors is not None:
            family_name = resolve_exit_strategy(strategy).name
            fam_raw = float(family_floors[family_name])
            # Family floors share the FAIL_CLOSED_FLOOR sentinel
            # (``compute_family_expectancy_floors`` delegates to
            # ``compute_expectancy_floor``).
            fam_signal = 0.0 if is_fail_closed_placeholder(fam_raw) else fam_raw

        cap = max(RR_FLOOR_ELEVATED, exp_signal, fam_signal)
        if floor > cap:
            floor = cap
            applied.append("catalyst_belief_relief")

    # Shock floor: elevated R:R requirement applied narrowly to non-beneficiary
    # entries during an active geopolitical-shock phase. When there's no shock,
    # mirror the effective floor so downstream interpolation always emits a
    # consistent pair of numbers. Pre-Fix-3 this was hardcoded `R:R >= 4.0` in
    # entry_strategist.yaml and drifted from the operational floor.
    shock_floor = (
        max(float(floor), RR_FLOOR_ELEVATED)
        if global_risk_regime in _STRESSED_REGIMES
        else float(floor)
    )

    return RecommendationGateDecision(
        effective_rr_floor=float(floor),
        max_new_entries=int(max_entries),
        entries_allowed=True,
        entries_blocked_reason=None,
        applied_rules=tuple(applied),
        inputs_digest=_digest(locals()),
        shock_rr_floor=shock_floor,
    )


def recompose_for_strategy_failure(
    decision: RecommendationGateDecision,
) -> RecommendationGateDecision:
    """Rebuild a decision with `strategy_director_failed=True`.

    Called from the `phase_strategy` deterministic-fallback path so the
    structural-block rule (Rule 3) gets a chance to fire on days the LLM
    director fails under a stressed regime. Re-uses the original decision's
    `inputs_digest` so the two decisions share one input set and only
    differ on the failure flag.
    """
    digest = dict(decision.inputs_digest)
    digest["strategy_director_failed"] = True
    return compose_recommendation_gate(
        trading_mode=digest.get("trading_mode") or "NORMAL",  # type: ignore[arg-type]
        market_regime=digest.get("market_regime") or "NEUTRAL",  # type: ignore[arg-type]
        global_risk_regime=digest.get("global_risk_regime") or "CAUTIOUS",  # type: ignore[arg-type]
        urgency_tier=digest.get("urgency_tier") or "NORMAL",  # type: ignore[arg-type]
        urgency_min_rr=digest.get("urgency_min_rr") or 2.5,  # type: ignore[arg-type]
        urgency_max_picks=digest.get("urgency_max_picks") or 3,  # type: ignore[arg-type]
        underlying_stress=bool(digest.get("underlying_stress")),
        strategy_director_failed=True,
        retro_min_rr_override=digest.get("retro_min_rr_override"),  # type: ignore[arg-type]
        retro_max_entries=digest.get("retro_max_entries"),  # type: ignore[arg-type]
        expectancy_floor=digest.get("expectancy_floor"),  # type: ignore[arg-type]
        streak_alert=digest.get("streak_alert"),  # type: ignore[arg-type]
        strategy=digest.get("strategy"),  # type: ignore[arg-type]
        has_high_positive_macro_catalyst=bool(digest.get("has_high_positive_macro_catalyst")),
        bullish_sector_belief_count=int(digest.get("bullish_sector_belief_count") or 0),  # type: ignore[arg-type]
        has_candidate_positive_catalyst=bool(digest.get("has_candidate_positive_catalyst")),
        shock_active=bool(digest.get("shock_active")),
        cash_healthy=bool(digest.get("cash_healthy")),
    )


def _blocked(
    *,
    reason: str,
    applied: list[str],
    inputs_digest: dict[str, object],
) -> RecommendationGateDecision:
    """Construct a blocked decision. `entries_allowed=False ⇒ max_entries=0`."""
    return RecommendationGateDecision(
        effective_rr_floor=RR_FLOOR_CRISIS,
        max_new_entries=0,
        entries_allowed=False,
        entries_blocked_reason=reason,
        applied_rules=tuple(applied),
        inputs_digest=inputs_digest,
    )


_DIGEST_KEYS: tuple[str, ...] = (
    "trading_mode",
    "market_regime",
    "global_risk_regime",
    "urgency_tier",
    "urgency_min_rr",
    "urgency_max_picks",
    "underlying_stress",
    "strategy_director_failed",
    "retro_min_rr_override",
    "retro_max_entries",
    "expectancy_floor",
    "streak_alert",
    "strategy",
    "has_high_positive_macro_catalyst",
    "bullish_sector_belief_count",
    "has_candidate_positive_catalyst",
    "shock_active",
    "cash_healthy",
)


def _digest(local_vars: dict[str, object]) -> dict[str, object]:
    """Snapshot the composer's inputs for the audit trail.

    The ``streak_alert`` slot is a T-1 snapshot — see
    ``retro/streak.py::detect_zero_buy_streak`` (SWI-125 Surface 3).
    """
    snapshot: dict[str, object] = {}
    for key in _DIGEST_KEYS:
        if key in local_vars:
            snapshot[key] = local_vars[key]
    return snapshot
