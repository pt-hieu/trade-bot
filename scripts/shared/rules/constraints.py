"""Centralized constraint logic — single source of truth for pipeline decision spine.
Pure deterministic Python. No async, no DB, no LLM.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, TypedDict

from shared.formatting import format_vnd
from shared.neon._types import GoalData, SwingTradeStats

if TYPE_CHECKING:
    from shared.rules.recommendation_gate import RecommendationGateDecision

# Named constants for urgency-based R:R defaults (distinct from regime floors in rr_floors.py)
MIN_RR_NORMAL = 2.5  # NORMAL urgency tier default
MAX_PICKS_NORMAL = 3  # NORMAL urgency tier default
# (CIRCUIT_BREAKER_RR_CAP retired 2026-04-20 — the composer in
# `shared/rules/recommendation_gate.py` is now the single source of truth
# for R:R ceilings. Retro overrides are applied via min() in compose_with_retro
# and again in the composer, so an uncapped high min_rr can no longer leak
# into the validator.)


class PipelineConstraints(TypedDict, total=False):
    """Typed contract consumed by picks, validator, strategy_director, and sections.

    ``min_rr`` / ``max_new_entries`` are the PRE-COMPOSITION urgency inputs
    (producer contract). ``effective_min_rr`` / ``effective_max_new_entries``
    are the POST-COMPOSITION outputs of `compose_recommendation_gate` — wired
    here via `inject_gate_composition()` so reader-facing consumers (brief
    renderer, picks entry-criteria text) read the single authoritative value.
    """

    budget_vnd: int
    max_new_entries: int
    min_rr: float
    urgency_tier: str
    goal_gap: int
    deployable: int
    retro_constraint_text: str | None
    retro_max_entries: int | None
    retro_scale_override: float | None
    retro_min_rr_override: float | None
    expectancy_floor: float | None
    rolling_win_rate: float | None
    entries_allowed: bool
    entries_blocked_reason: str | None
    effective_min_rr: float
    effective_max_new_entries: int


def is_long_horizon_goal(goal_type: str, days_left: int) -> bool:
    """Non-Monthly/Quarterly with >365 days left — excluded from urgency."""
    return goal_type not in ("Monthly", "Quarterly") and days_left > 365


def calculate_goal_urgency(on_track: bool, days_left: int) -> dict:
    """Deterministic urgency tier → {urgency, min_rr, max_picks}.

    Higher urgency → LOWER min_rr + MORE picks (take more shots).
    All min_rr >= RR_FLOOR_DEFAULT (2.0 in rr_floors.py) — safety nets handle the rest.
    """
    if on_track:
        return {"urgency": "NORMAL", "min_rr": 2.5, "max_picks": 3}
    elif days_left > 15:
        return {
            "urgency": "AWARENESS",
            "min_rr": 2.5,
            "max_picks": 4,
            "note": "Behind schedule — note in GOAL PROGRESS",
        }
    elif days_left > 10:
        return {"urgency": "ELEVATED", "min_rr": 2.3, "max_picks": 4}
    elif days_left > 5:
        return {"urgency": "HIGH", "min_rr": 2.0, "max_picks": 5}
    else:
        return {
            "urgency": "ACCEPTANCE",
            "min_rr": 2.0,
            "max_picks": 3,
            "note": "Month nearly over — take disciplined shots",
        }


def _reachability_note(remaining: float, days_left: int, projected_str: str = "") -> str:
    """Build reachability note string."""
    base = f"Need {format_vnd(remaining)} in {days_left} days."
    if projected_str:
        return f"{base} {projected_str} Goal requires cash contribution."
    return f"{base} Goal requires cash contribution."


def _assess_reachability_naive(
    remaining: float, days_left: int, deployable: float
) -> tuple[str | None, str]:
    """Fallback reachability using 3% daily assumption (< 5 closed trades)."""
    max_achievable = deployable * 0.03 * days_left
    ratio = (max_achievable / remaining) if remaining > 0 else 0
    if ratio >= 1.0:
        return None, ""
    elif ratio >= 0.5:
        return (
            "STRETCH",
            f"Need {format_vnd(remaining)} in {days_left} days. Achievable but requires consistent wins.",
        )
    return "UNREACHABLE", _reachability_note(
        remaining, days_left, f"Max realistic: ~{format_vnd(int(max_achievable))} (< 5 trades)."
    )


def assess_reachability(
    remaining: float,
    days_left: int,
    deployable: float,
    trade_stats: SwingTradeStats | None,
) -> tuple[str | None, str]:
    """Assess goal reachability. Returns (level, note). None = ON_TRACK."""
    if deployable <= 0:
        return "UNREACHABLE", "No deployable capital available."
    if not trade_stats or trade_stats.get("total_trades", 0) < 5:
        return _assess_reachability_naive(remaining, days_left, deployable)

    expectancy = trade_stats.get("expectancy_vnd", 0)
    trades_per_month = trade_stats.get("trades_per_month", 0)
    if expectancy <= 0 or trades_per_month <= 0:
        return "UNREACHABLE", _reachability_note(
            remaining, days_left, "Historical expectancy negative/zero."
        )

    projected = expectancy * trades_per_month * (days_left / 30.0)
    ratio = projected / remaining
    pace_str = (
        f"Projected ~{format_vnd(int(projected))} at current pace "
        f"({format_vnd(int(expectancy))}/trade x {trades_per_month:.1f} trades/mo)."
    )
    if ratio >= 1.5:
        return None, ""
    elif ratio >= 0.7:
        return (
            "STRETCH",
            f"Need {format_vnd(remaining)} in {days_left} days. {pace_str} Achievable with consistent execution.",
        )
    return "UNREACHABLE", _reachability_note(remaining, days_left, pace_str)


def compute_goal_metrics(
    goal: GoalData,
    deployable: float,
    trade_stats: SwingTradeStats | None = None,
    scan_date: date | None = None,
    format_prose: bool = True,
) -> dict:
    """Enrich a goal dict with urgency, achievability, days_left, and prose."""
    target = goal.get("target", 0)
    realized = goal.get("realized", 0)
    remaining = target - realized
    progress_pct = (realized / target * 100) if target > 0 else 0

    reference_date = scan_date or date.today()
    deadline = goal.get("deadline", "")
    if deadline:
        if isinstance(deadline, str):
            deadline_date = datetime.strptime(deadline, "%Y-%m-%d").date()
        else:
            deadline_date = deadline
        days_left = max(0, (deadline_date - reference_date).days)
    else:
        days_left = 0
        deadline_date = None

    # on_track: 70% of linear pace threshold — swing trading is lumpy, allows ~30% variance
    start_date_val = goal.get("start_date", "")
    if start_date_val and deadline_date and target > 0:
        if isinstance(start_date_val, str):
            start_dt = datetime.strptime(start_date_val, "%Y-%m-%d").date()
        else:
            start_dt = start_date_val
        total_days = max((deadline_date - start_dt).days, 1)
        elapsed_days = total_days - days_left
        if elapsed_days <= 0:
            on_track = True  # goal just started
        elif realized < 0:
            on_track = False  # net losses — always behind
        else:
            expected_progress = (elapsed_days / total_days) * target
            on_track = realized >= expected_progress * 0.7
    else:
        on_track = days_left > 20  # fallback when dates missing

    goal_type = goal.get("goal_type", "Monthly")
    is_long_horizon = is_long_horizon_goal(goal_type, days_left)

    result = {
        "name": goal.get("name", "Unknown"),
        "goal_type": goal_type,
        "target": target,
        "realized": realized,
        "remaining": remaining,
        "progress_pct": round(progress_pct, 1),
        "days_left": days_left,
        "deadline": str(deadline) if deadline else "",
        "daily_target": round(remaining / max(1, days_left), 0) if days_left > 0 else 0,
        "trades_count": goal.get("trades_count", 0),
        "on_track": on_track,
    }

    urgency = calculate_goal_urgency(on_track, days_left)

    if remaining > 0 and days_left > 0:
        achievability, note = assess_reachability(remaining, days_left, deployable, trade_stats)
        if achievability:
            result["achievability"] = achievability
            result["achievability_note"] = note
            if achievability == "UNREACHABLE" and not is_long_horizon:
                result["on_track"] = False
                # DETERMINED replaces old AGGRESSIVE (6:1 R:R) that caused death spiral
                urgency = {
                    "urgency": "DETERMINED",
                    "min_rr": 2.0,
                    "max_picks": 5,
                    "note": "One disciplined trade can change momentum",
                }
        elif achievability is None and on_track:
            result["achievability"] = "ON_TRACK"

    result["urgency"] = urgency

    if format_prose:
        from agents.tools.portfolio_formatters import _format_goal_prose

        result["prose"] = _format_goal_prose(result)

    return result


URGENCY_ORDER = {
    "DETERMINED": 5,
    "ACCEPTANCE": 4,
    "HIGH": 3,
    "ELEVATED": 2,
    "AWARENESS": 1,
    "NORMAL": 0,
}


def select_most_urgent_goal(goals: list[dict]) -> dict | None:
    """Most urgent short-horizon goal. Long-horizon goals excluded."""
    if not goals:
        return None
    short_goals = [
        goal
        for goal in goals
        if not is_long_horizon_goal(goal.get("goal_type") or "Monthly", goal.get("days_left") or 0)
    ]
    if not short_goals:
        return {
            "urgency": {"urgency": "NORMAL", "min_rr": MIN_RR_NORMAL, "max_picks": MAX_PICKS_NORMAL}
        }
    return max(
        short_goals,
        key=lambda goal: URGENCY_ORDER.get(
            (goal.get("urgency") or {}).get("urgency") or "NORMAL", 0
        ),
    )


def compute_directive_constraints(goals: list[dict], cash: dict) -> PipelineConstraints:
    """Compute deterministic constraints from goals + cash."""
    deployable = cash.get("deployable") or 0

    most_urgent_goal = select_most_urgent_goal(goals)
    urgency = (most_urgent_goal.get("urgency") or {}) if most_urgent_goal else {}
    urgency_tier = urgency.get("urgency") or "NORMAL"
    min_rr = urgency.get("min_rr") or MIN_RR_NORMAL
    max_picks = urgency.get("max_picks") or MAX_PICKS_NORMAL

    if deployable <= 0:
        max_new_entries = 0
    elif urgency_tier == "ACCEPTANCE":
        max_new_entries = 1
    else:
        max_new_entries = max_picks if max_picks else 0

    goal_gap = 0  # remaining amount for retro recovery math
    if most_urgent_goal:
        goal_gap = most_urgent_goal.get("remaining") or 0
    return PipelineConstraints(
        budget_vnd=int(deployable),
        max_new_entries=max_new_entries,
        min_rr=min_rr,
        urgency_tier=urgency_tier,
        goal_gap=int(goal_gap),
        deployable=int(deployable),
    )


def compose_with_retro(constraints: PipelineConstraints, retro: dict) -> PipelineConstraints:
    """Apply retro overrides. max() for entries, min() for R:R (anti-death-spiral).

    Also derives an ``expectancy_floor`` from the rolling win rate (Van Tharp
    R-multiples). The floor is *not* min'd into ``min_rr`` — it's a separate
    field consumed by the final validator gate so the anti-death-spiral logic
    on ``min_rr`` keeps working while expectancy still forces discipline on
    cold streaks.
    """
    from shared.rules.expectancy import compute_expectancy_floor

    constraints["retro_constraint_text"] = retro.get("constraint_text")
    constraints["retro_max_entries"] = retro.get("max_entries")
    constraints["retro_scale_override"] = retro.get("scale_override")
    constraints["retro_min_rr_override"] = retro.get("min_rr_override")

    if retro.get("max_entries") is not None:
        constraints["max_new_entries"] = max(
            constraints.get("max_new_entries") or 0, retro["max_entries"]
        )
    if retro.get("min_rr_override") is not None:
        constraints["min_rr"] = min(
            constraints.get("min_rr") or MIN_RR_NORMAL, retro["min_rr_override"]
        )

    rolling_win_rate = retro.get("win_rate")
    constraints["rolling_win_rate"] = rolling_win_rate
    constraints["expectancy_floor"] = compute_expectancy_floor(rolling_win_rate)

    return constraints


def apply_circuit_breakers(constraints: PipelineConstraints) -> PipelineConstraints:
    """Hard floor: max_entries >= 1. Prevents death spiral.

    The min_rr ceiling is now enforced by
    `shared/rules/recommendation_gate.compose_recommendation_gate` — this
    function is reduced to the max_entries invariant so producers and the
    composer stay consistent.
    """
    constraints["max_new_entries"] = max(constraints.get("max_new_entries") or 0, 1)
    return constraints


def inject_entry_gate(
    constraints: PipelineConstraints,
    entries_allowed: bool,
    entries_blocked_reason: str | None,
) -> PipelineConstraints:
    """Add entry gate result to constraints dict."""
    constraints["entries_allowed"] = entries_allowed
    if entries_blocked_reason:
        constraints["entries_blocked_reason"] = entries_blocked_reason
    return constraints


def inject_gate_composition(
    constraints: PipelineConstraints,
    gate_decision: RecommendationGateDecision,
) -> PipelineConstraints:
    """Ripple ``compose_recommendation_gate`` output into reader-facing keys.

    The gate composer produces the authoritative R:R floor and max-entries
    pair after mixing urgency, regime, retro, and streak rules. Downstream
    reader surfaces (brief ENTRY CRITERIA, synthesis narrative) must read
    the COMPOSED value, not the urgency input. Writes
    ``effective_min_rr`` / ``effective_max_new_entries`` so the pre-composition
    keys (``min_rr`` / ``max_new_entries``) remain intact as the producer
    contract — avoids circular composer-input contamination.
    """
    constraints["effective_min_rr"] = float(gate_decision.effective_rr_floor)
    constraints["effective_max_new_entries"] = int(gate_decision.max_new_entries)
    return constraints
