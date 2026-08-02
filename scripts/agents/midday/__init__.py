"""Midday Market Check Agent using PydanticAI.

Runs at 12 PM Vietnam time (market break) to:
1. Review pre-computed entries hit, big movers, position alerts
2. Determine trading mode from cash balance
3. Generate qualitative morning reflection + afternoon plan

Numeric data is pre-computed in midday_check.py to prevent LLM hallucination.

Module layout (post-modularisation, SWI-212):
  * ``models.py`` — Pydantic schemas (RecommendationOverride, AfternoonAction,
    MiddayQualitative) + override_reason_mentions_stop helper.
  * ``prompt_builder.py`` — _build_prompt + create_midday_agent + section filter.
  * ``guardrails.py`` — auto-inject CANCEL overrides + plan_type resolver.
  * ``__init__.py`` — run_midday_check_async orchestrator + re-exports.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from shared.agent_config import build_usage_limits
from shared.observability import observe_agent_output
from shared.rules.afternoon_ticker_reconciler import reconcile_afternoon_tickers

from ..agent_factory import AgentDeps
from .guardrails import _append_override, resolve_plan_type_for_ticker
from .models import (
    STOP_REASON_TOKENS,
    AfternoonAction,
    MiddayQualitative,
    MiddayStatus,
    RecommendationOverride,
    override_reason_mentions_stop,
)
from .prompt_builder import _build_prompt, _truncate_directive, create_midday_agent

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY = 3  # seconds

# vnstock returns prices in thousands VND
PRICE_MULTIPLIER = 1000


def _merge_result(qualitative: MiddayQualitative, precomputed: dict) -> dict:
    """Merge LLM qualitative output with pre-computed numeric data."""
    return {
        "trading_mode": "NORMAL",
        "deployable_cash": precomputed.get("deployable_cash", 0),
        "entries_hit": precomputed.get("entries_hit", []),
        "big_movers": precomputed.get("big_movers", []),
        "position_alerts": precomputed.get("position_alerts", []),
        "morning_position_alerts": precomputed.get("morning_position_alerts", []),
        "morning_reflection": qualitative.morning_reflection,
        "afternoon_plan": [action.model_dump() for action in qualitative.afternoon_plan],
        "afternoon_note": qualitative.afternoon_note,
        "capital_note": qualitative.capital_note,
        "recommendation_overrides": [o.model_dump() for o in qualitative.recommendation_overrides],
    }


def _fallback_result(error: Exception | None = None) -> dict:
    """Return fallback result when analysis fails."""
    return {
        "trading_mode": "NORMAL",
        "deployable_cash": 0,
        "entries_hit": [],
        "big_movers": [],
        "position_alerts": [],
        "morning_reflection": f"Analysis failed: {error}" if error else "Analysis failed",
        "afternoon_plan": [
            {
                "ticker": None,
                "action": "NOTE",
                "confidence": "LOW",
                "reason": "Manual review required",
            }
        ],
        "afternoon_note": None,
        "capital_note": "Could not determine trading mode",
    }


async def run_midday_check_async(
    morning_recommendations: list[dict],
    scan_date: date | None = None,
    midday_prices: dict | None = None,
    precomputed: dict | None = None,
    trading_mode: str = "NORMAL",
    portfolio_context: str = "",
    recent_trades_context: str = "",
    learnings_context: str = "",
    executed_trades_context: str = "",
    midday_prices_context: str = "",
    holdings: list[dict] | None = None,
) -> dict:
    """Run midday check analysis (async)."""
    if scan_date is None:
        scan_date = date.today()
    if precomputed is None:
        precomputed = {}

    agent, config = await create_midday_agent()
    prompt = _build_prompt(
        morning_recommendations,
        precomputed,
        trading_mode=trading_mode,
        portfolio_context=portfolio_context,
        recent_trades_context=recent_trades_context,
        learnings_context=learnings_context,
        executed_trades_context=executed_trades_context,
        midday_prices_context=midday_prices_context,
    )

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            # HOOK-ALLOW: unguarded-agent-run reason=midday uses FallbackModel
            result = await agent.run(
                prompt,
                deps=AgentDeps(
                    scan_date=scan_date,
                    agent_key=config.agent_key,
                    midday_prices=midday_prices or {},
                ),
                usage_limits=build_usage_limits(config),
            )
            qualitative = result.output
            observe_agent_output(agent="midday", result=result, max_tokens=96000, logger=logger)

            morning_action_by_ticker = {
                rec["ticker"]: rec.get("action") or "HOLD"
                for rec in morning_recommendations
                if rec.get("ticker")
            }
            holdings_by_ticker: dict[str, list[dict]] = {}
            for holding in holdings or []:
                ticker_key = (holding.get("ticker") or "").upper()
                if ticker_key:
                    holdings_by_ticker.setdefault(ticker_key, []).append(holding)

            # SWI-254: Resolve plan_type for LLM-emitted overrides BEFORE the
            # guardrail loop so dedup `(ticker, plan_type)` collapses an LLM
            # null and a guardrail-emitted SWING/LONGTERM into one row.
            # Off-portfolio overrides keep plan_type=None (intentional —
            # not subject to guardrail injection so dedup is moot).
            #
            # `morning_action` is a provenance FACT (what the morning rec
            # said), not a midday judgment — Python owns it. The LLM
            # collapsed ACV's conditional counter-thesis into a firm
            # 'TRIM' (run2 2026-05-14); overwrite from the single source
            # so LLM and guardrail overrides derive it identically.
            for override in qualitative.recommendation_overrides:
                if override.plan_type is None:
                    override.plan_type = resolve_plan_type_for_ticker(
                        override.ticker, holdings_by_ticker
                    )
                override.morning_action = morning_action_by_ticker.get(override.ticker) or "HOLD"

            for alert in precomputed.get("position_alerts") or []:
                if alert.get("level_type") != "STOP_INTRADAY_TOUCH":
                    continue
                ticker = alert.get("ticker")
                if not ticker:
                    continue
                stop_level = alert.get("level") or 0
                _append_override(
                    qualitative,
                    ticker=ticker,
                    plan_type=None,
                    morning_action=morning_action_by_ticker.get(ticker) or "HOLD",
                    reason=f"Stop breached at {stop_level:,.0f} — auto-generated guardrail",
                    revised_stop=float(stop_level) if stop_level else None,
                    holdings_by_ticker=holdings_by_ticker,
                )

            for breach in precomputed.get("max_loss_breaches") or []:
                ticker = breach.get("ticker") or ""
                plan_type = (breach.get("plan_type") or "").upper()
                if not ticker or not plan_type:
                    continue
                _append_override(
                    qualitative,
                    ticker=ticker,
                    plan_type=plan_type,
                    morning_action=morning_action_by_ticker.get(ticker) or "HOLD",
                    reason=(
                        f"MAX LOSS CEILING breached: {plan_type} slice down "
                        f"{breach.get('loss_pct', 0):.1f}% vs ceiling "
                        f"{breach.get('ceiling_pct', 0):.0f}% — auto-generated guardrail"
                    ),
                )

            from ..midday_guardrails import (
                apply_crisis_gate,
                apply_defensive_gate,
                apply_downtrend_gate,
            )

            apply_crisis_gate(qualitative, morning_recommendations, precomputed)
            apply_defensive_gate(qualitative, morning_recommendations, precomputed)
            apply_downtrend_gate(qualitative, morning_recommendations, precomputed)

            reconcile_afternoon_tickers(qualitative.afternoon_plan, holdings or [])

            return _merge_result(qualitative, precomputed)
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY * (attempt + 1)
                print(f"  Attempt {attempt + 1}/{MAX_RETRIES + 1} failed: {e}")
                print(f"  Retrying in {delay}s...")
                await asyncio.sleep(delay)
            else:
                print(f"  All {MAX_RETRIES + 1} attempts failed: {e}")

    return _fallback_result(last_error)


__all__ = [
    "MAX_RETRIES",
    "PRICE_MULTIPLIER",
    "RETRY_DELAY",
    "STOP_REASON_TOKENS",
    "AfternoonAction",
    "MiddayQualitative",
    "MiddayStatus",
    "RecommendationOverride",
    "_append_override",
    "_build_prompt",
    "_fallback_result",
    "_merge_result",
    "_truncate_directive",
    "create_midday_agent",
    "override_reason_mentions_stop",
    "resolve_plan_type_for_ticker",
    "run_midday_check_async",
]
