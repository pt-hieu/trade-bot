"""Phase 3d: Strategy Director — generate position guidance and entry strategy."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import TYPE_CHECKING

from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded

from agents import generate_strategy_directive
from agents.strategy_sections import build_deterministic_sections
from shared.rules.recommendation_gate import (
    RecommendationGateDecision,
    recompose_for_strategy_failure,
)
from shared.rules.rr_floors import RR_FLOOR_ELEVATED

from .rendering import derive_holding_actions
from .types import InjectedContext, Phase1Result, Phase2Result

if TYPE_CHECKING:
    from shared.rules.constraints import PipelineConstraints

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 2
_RETRY_DELAY = 3


def _build_deterministic_fallback(
    phase1_results: Phase1Result,
    phase2_results: Phase2Result,
    deterministic_sections: str,
    failure_reason: str,
    gate_decision: RecommendationGateDecision | None,
) -> tuple[str, str, dict]:
    """Build minimal directive when LLM strategy director fails.

    Structural failure flows through the shared `RecommendationGateDecision`
    — the caller first re-composes with `strategy_director_failed=True` so
    Rule 3 (`strategy_director_failed_stressed`) can fire under stressed
    regimes. `entries_allowed=False` drives the DEFENSIVE branch here.
    """
    market_level = phase1_results.market_level or {}
    regime = market_level.get("regime") or "CAUTIOUS"
    macro = phase1_results.macro_metrics or {}
    risk_regime = macro.get("global_risk_regime") or "CAUTIOUS"

    # Position guidance from position alerts
    position_alerts_data = phase2_results.position_alerts or {}
    position_alerts = position_alerts_data.get("alerts", [])
    guidance_lines = ["## POSITION GUIDANCE (auto-generated fallback)"]
    if position_alerts:
        for a in position_alerts:
            ticker = a.get("ticker") or "?"
            action = a.get("action") or "MONITOR"
            reason = (a.get("reason") or "")[:80]
            guidance_lines.append(f"- {ticker}: {action} — {reason}")
    else:
        guidance_lines.append("- No position alerts")
    position_guidance = "\n".join(guidance_lines)

    # Entry strategy: header + STANCE inferred from regime + embedded sections.
    # Constraints read the composer's decision so brief, validator, and
    # picks writer all see the same effective floor on every fallback path.
    if gate_decision is not None and not gate_decision.entries_allowed:
        stance_line = (
            f"DEFENSIVE [confidence: LOW] -- Strategy directive unavailable; "
            f"{gate_decision.entries_blocked_reason or 'entries blocked'}. "
            f"Capital preservation."
        )
        constraints = {
            "budget_vnd": 0,
            "max_new_entries": 0,
            "min_rr": gate_decision.effective_rr_floor,
        }
    else:
        stance_line = (
            f"NEUTRAL [confidence: LOW] -- Strategy directive unavailable; "
            f"defaulting to conservative. Regime {regime}, global risk {risk_regime}."
        )
        composed_floor = (
            gate_decision.effective_rr_floor if gate_decision is not None else RR_FLOOR_ELEVATED
        )
        composed_max = gate_decision.max_new_entries if gate_decision is not None else 1
        constraints = {
            "budget_vnd": 50_000_000,
            "max_new_entries": max(composed_max, 1),
            "min_rr": composed_floor,
        }

    entry_strategy = (
        "TODAY'S THEME\n"
        f"Strategy directive unavailable -- deterministic fallback active ({failure_reason}).\n\n"
        "STANCE\n"
        f"{stance_line}\n\n"
        f"{deterministic_sections}\n\n"
        "KEY RISK\n"
        "- Strategy generation failed; entry recommendations rely on pre-computed picks "
        "and constraints only. Validate any new entries manually against the embedded "
        "ENTRY CRITERIA TODAY block before acting."
    )

    return position_guidance, entry_strategy, constraints


async def run_strategy_director(
    phase1_results: Phase1Result,
    phase2_results: Phase2Result,
    trading_mode: dict | None,
    scan_date,
    pre_computed_picks: list[dict] | None,
    sector_rotation: dict | None,
    injected: InjectedContext,
    pre_computed_constraints: PipelineConstraints | None = None,
    goals: list[dict] | None = None,
    cash: dict | None = None,
    gate_decision: RecommendationGateDecision | None = None,
) -> tuple[str | None, str | None, PipelineConstraints | dict | None]:
    """Run strategy director and persist directive to DB.

    Returns (position_guidance, entry_strategy, directive_constraints).
    """
    phase1_dict = asdict(phase1_results)
    phase2_with_rotation = asdict(phase2_results)
    phase2_with_rotation["sector_rotation"] = sector_rotation

    # Pre-compute deterministic_sections once and pass into both the LLM
    # directive and the fallback below — avoids drift between success and
    # failure paths and prevents the strategy director from rebuilding the
    # same sections (~4 DB queries) on every successful run.
    deterministic_sections = await build_deterministic_sections(
        goals or [],
        cash or {},
        pre_computed_constraints or {},
        phase1_dict,
    )

    # Single canonical derivation of holding actions — shared with synthesis.py.
    # entry_strategist's MINDSET section reads the formatted summary so it
    # cannot drift from today's holdings decisions.
    holdings_actions = derive_holding_actions(phase2_results.position_alerts or {})
    holdings_verb_summary = ", ".join(
        f"{a.ticker}={a.verb}{a.qty_pct}%" if a.qty_pct is not None else f"{a.ticker}={a.verb}"
        for a in holdings_actions
    )

    last_error = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            (
                position_guidance,
                entry_strategy,
                directive_constraints,
            ) = await generate_strategy_directive(
                phase1_results=phase1_dict,
                phase2_results=phase2_with_rotation,
                trading_mode=trading_mode,
                pre_computed_constraints=pre_computed_constraints or {},
                goals=goals or [],
                cash=cash or {},
                scan_date=scan_date,
                pre_computed_picks=pre_computed_picks,
                trailing_stops_context=injected.trailing_stops_context,
                geopolitical_context=injected.geopolitical_context,
                portfolio_context=injected.portfolio_context,
                catalyst_context=injected.catalyst_context,
                catalyst_boost_context=injected.catalyst_boost_context,
                articles_context=injected.articles_context,
                regime_context=injected.regime_context,
                macro_interpretation=injected.macro_interpretation,
                commodity_context=injected.commodity_context,
                vn_economy_context=injected.vn_economy_context,
                recent_trades_context=injected.recent_trades,
                learnings_context=injected.learnings_formatted.get("entry_strategist", ""),
                memory_context=injected.memory_context,
                deterministic_sections=deterministic_sections,
                holdings_verb_summary=holdings_verb_summary,
                gate_decision=gate_decision,
            )
            print(f"  Position guidance: {len(position_guidance or '')} chars", flush=True)
            print(f"  Entry strategy: {len(entry_strategy or '')} chars", flush=True)
            print(f"  Constraints: {directive_constraints}", flush=True)

            return position_guidance, entry_strategy, directive_constraints
        except (UsageLimitExceeded, UnexpectedModelBehavior) as e:
            # Deterministic given the prompt — retrying reproduces the same loop.
            # Skip remaining attempts and fall straight to the deterministic fallback.
            last_error = e
            logger.warning(
                "Strategy directive hit %s — skipping retry, falling through to "
                "deterministic fallback: %s",
                type(e).__name__,
                e,
            )
            break
        except Exception as e:
            last_error = e
            if attempt < _MAX_ATTEMPTS - 1:
                logger.warning(
                    "Strategy directive attempt %d failed: %s. Retrying...", attempt + 1, e
                )
                await asyncio.sleep(_RETRY_DELAY)

    # Both attempts failed — deterministic fallback
    logger.warning(
        "Strategy directive failed after %d attempts: %s. Using deterministic fallback.",
        _MAX_ATTEMPTS,
        last_error,
    )
    failure_reason = (
        f"{type(last_error).__name__}: {last_error}" if last_error else "unknown failure"
    )
    # Re-compose with strategy_director_failed=True so Rule 3 fires under
    # stressed regimes. Without this, the fallback path inherits a gate
    # that was built during phase3a (before the director's failure was
    # knowable) and the structural-block rule stays dead code.
    if gate_decision is not None:
        gate_decision = recompose_for_strategy_failure(gate_decision)
    position_guidance, entry_strategy, constraints = _build_deterministic_fallback(
        phase1_results,
        phase2_results,
        deterministic_sections,
        failure_reason,
        gate_decision,
    )
    print(f"  FALLBACK position guidance: {len(position_guidance)} chars", flush=True)
    print(f"  FALLBACK entry strategy: {len(entry_strategy)} chars", flush=True)

    return position_guidance, entry_strategy, constraints
