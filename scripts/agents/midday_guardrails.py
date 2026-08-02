"""Deterministic post-LLM guardrails for midday agent.

These run AFTER the LLM returns its output and auto-inject CANCEL overrides
for recommendations that violate hard rules. No LLM judgment involved.
"""

import logging
from collections.abc import Callable

from pipeline.recommendation_builder import BUY_ACTIONS

from .midday import MiddayQualitative, RecommendationOverride

logger = logging.getLogger(__name__)


def _apply_guardrail_cancellations(
    qualitative: MiddayQualitative,
    morning_recommendations: list[dict],
    should_cancel: Callable[[str, dict], tuple[bool, str]],
) -> None:
    """Apply deterministic cancellation guardrail to ADD/BUY recommendations.

    Args:
        qualitative: LLM output with recommendation_overrides list (mutated in place)
        morning_recommendations: Parsed morning brief recommendations
        should_cancel: (ticker, technicals_dict) -> (cancel_flag, reason_string)
    """
    existing_overrides = {o.ticker for o in qualitative.recommendation_overrides}
    for rec in morning_recommendations:
        ticker = rec.get("ticker") or ""
        action = (rec.get("action") or "").upper()
        if action in BUY_ACTIONS and ticker not in existing_overrides:
            cancel, reason = should_cancel(ticker, rec)
            if cancel:
                qualitative.recommendation_overrides.append(
                    RecommendationOverride(
                        ticker=ticker,
                        morning_action=rec.get("action") or "",
                        midday_status="CANCEL",
                        reason=reason,
                    )
                )
                logger.warning("Auto-cancelled %s %s (%s)", action, ticker, reason)


ADX_DOWNTREND_THRESHOLD = 35


def apply_defensive_gate(
    qualitative: MiddayQualitative,
    morning_recommendations: list[dict],
    precomputed: dict,
) -> None:
    """CANCEL ADD/BUY when stance is DEFENSIVE."""
    strategy_directive = precomputed.get("strategy_directive") or {}
    directive_text = (
        strategy_directive.get("directive") or ""
        if isinstance(strategy_directive, dict)
        else str(strategy_directive)
    )
    if "DEFENSIVE" not in directive_text.upper():
        return

    _apply_guardrail_cancellations(
        qualitative,
        morning_recommendations,
        should_cancel=lambda _ticker, _rec: (
            True,
            "DEFENSIVE stance — ADD/BUY blocked by deterministic gate",
        ),
    )


def apply_crisis_gate(
    qualitative: MiddayQualitative,
    morning_recommendations: list[dict],
    precomputed: dict,
) -> None:
    """CANCEL ADD/BUY when morning entry gate blocked entries (e.g. CRISIS regime).

    Reads entries_allowed from strategy_directives.constraints, persisted by
    the morning pipeline. Deterministic — no LLM judgment involved.
    """
    strategy_directive = precomputed.get("strategy_directive") or {}
    constraints = (
        strategy_directive.get("constraints") or {} if isinstance(strategy_directive, dict) else {}
    )
    entries_allowed = constraints.get("entries_allowed", True)
    if entries_allowed:
        return

    blocked_reason = constraints.get("entries_blocked_reason") or "entry gate blocked"

    _apply_guardrail_cancellations(
        qualitative,
        morning_recommendations,
        should_cancel=lambda _ticker, _rec: (
            True,
            f"CRISIS GATE — {blocked_reason}",
        ),
    )


def apply_downtrend_gate(
    qualitative: MiddayQualitative,
    morning_recommendations: list[dict],
    precomputed: dict,
) -> None:
    """CANCEL ADD/BUY when ADX > threshold AND Supertrend DOWN."""
    held_technicals = precomputed.get("held_technicals") or {}

    def _check_downtrend(ticker: str, _rec: dict) -> tuple[bool, str]:
        ticker_tech = held_technicals.get(ticker) or {}
        # Flat canonical shape — see shared/api/technicals.py::get_technicals.
        adx_value = ticker_tech.get("adx") or 0
        supertrend_direction = (ticker_tech.get("supertrend_direction") or "").upper()
        if adx_value > ADX_DOWNTREND_THRESHOLD and supertrend_direction == "DOWN":
            return (
                True,
                f"Strong downtrend — ADX {adx_value:.0f} > {ADX_DOWNTREND_THRESHOLD} + Supertrend DOWN",
            )
        return False, ""

    _apply_guardrail_cancellations(
        qualitative, morning_recommendations, should_cancel=_check_downtrend
    )
