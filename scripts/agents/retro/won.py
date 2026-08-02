"""
Single source of truth for evaluation win/loss determination.

Used by both compute_evaluations() (per-eval won field) and
compute_day_summary() (aggregate win_rate) to prevent logic drift.
"""

from typing import Literal

# Single source of truth for the recommendation-action vocabulary. Producers
# (positions_ensemble_*, synthesis_picks, recommendation_builder, ...) and
# consumers (retro compute, alert_registrar, brief renderers) import this
# Literal so pyright catches vocabulary drift at static-analysis time. The
# 2026-04-29 SWI-140 incident — where producers learned EVALUATE without the
# retro consumer following — is the recurrence test.
RecommendationAction = Literal[
    "BUY",
    "ADD",
    "LIMIT_BUY",
    "HOLD",
    "EXIT",
    "TRIM",
    "EVALUATE",
    "SKIP",
    "AVOID",
    "WAIT",
    "WATCH",
]

# Actions that represent entry trades (counted in entry hit rate / win rate)
ENTRY_ACTIONS: frozenset[RecommendationAction] = frozenset({"BUY", "ADD", "LIMIT_BUY"})

# Actions excluded from scoring entirely
EXCLUDED_ACTIONS: frozenset[RecommendationAction] = frozenset({"SKIP", "AVOID", "WAIT", "WATCH"})

# Actions that pass through as HOLD-state (need position data for real P/L)
# and require stop/target evaluation against EOD prices. EVALUATE was added
# 2026-04-29 (SWI-140): EVALUATE positions are still held, so stop_hit must
# be computed.
HOLD_ACTIONS: frozenset[RecommendationAction] = frozenset({"HOLD", "EXIT", "TRIM", "EVALUATE"})

# Union of every known action. Pyright asserts membership when callers iterate
# RecommendationAction; the runtime set drives the fail-loud guard in
# compute._evaluate_single's catch-all.
ALL_KNOWN_ACTIONS: frozenset[RecommendationAction] = ENTRY_ACTIONS | EXCLUDED_ACTIONS | HOLD_ACTIONS


class UnknownActionError(ValueError):
    """Raised when retro compute encounters an action outside ALL_KNOWN_ACTIONS.

    Catches producer-side vocabulary additions that were not propagated to
    the retro consumer (SWI-140). Fail loud at the consumer entry — silently
    falling through to a default ``status='HOLD'`` corrupts ground truth and
    cascades into Fix 4's eval_critic confidently-wrong findings.
    """


def compute_won(
    evaluation: dict,
    hold_loss_threshold_pct: float = 2.0,
    plan_type: str | None = None,
) -> bool | None:
    """Determine if an evaluation is a win, loss, or not scoreable.

    Args:
        evaluation: The evaluation dict with status, recommendation, day_change, etc.
        hold_loss_threshold_pct: Max day_change drop (%) before LONGTERM HOLD scores
            as loss. Default 2.0 — VN large-caps move 2-3% daily.
        plan_type: "SWING", "LONGTERM", or None. Controls HOLD win semantics:
            - SWING: strict positive daily gain (day_change > 0)
            - LONGTERM: thesis-intact (day_change >= -threshold)
            - None: unified fallback using threshold (conservative)

    Returns:
        True = win, False = loss, None = not scoreable (excluded/missed)
    """
    status = evaluation.get("status") or ""
    action = (evaluation.get("recommendation") or "").upper()

    # Not scoreable: excluded tickers or non-actionable recommendations
    if status == "EXCLUDED" or action in EXCLUDED_ACTIONS:
        return None

    # Not scoreable: no price data
    if status == "MISSED":
        return None

    # Trade was actually executed — deterministic win/loss from actual P/L
    if evaluation.get("trade_executed"):
        actual_pl_pct = evaluation.get("actual_pl_pct")
        if actual_pl_pct is not None:
            return actual_pl_pct > 0
        return None

    # Clear win
    if status == "WIN":
        return True

    # HOLD positions: win depends on day_change and plan_type
    if status == "HOLD":
        day_change = evaluation.get("day_change")
        if day_change is None:
            return None
        if action in ("TRIM", "EXIT"):
            # TRIM/EXIT held: win if stock didn't drop (ignoring was ok)
            return day_change >= 0

        if plan_type == "SWING":
            # Swing HOLD: strict positive — flat days are NOT wins
            return day_change > 0
        # LONGTERM or unknown: thesis-intact semantics
        return day_change >= -hold_loss_threshold_pct

    # Not scoreable: trade unresolved (entry hit but no target/stop by close)
    if status == "PENDING":
        return None

    # LOSS, STOP_BREACHED, or any other status
    return False
