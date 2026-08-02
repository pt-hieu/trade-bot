"""Watchlist Update Ensemble — 3 sector evaluators + coordinator.

Architecture: Fan-out / Fan-in (mirrors positions_ensemble.py).
  - Pre-fetch: Python gathers all data, pre-computes zone tags and sector heat.
  - Fan-out: 3 sector evaluator agents run in parallel (tool-free, context-injected).
  - Fan-in: Coordinator merges evaluations into final WatchlistUpdateResult.
  - Post-hoc: Python validates confidence and detects churn deterministically.

Module layout (post-modularisation, SWI-212):
  * ``config.py`` — sector groupings + ticker universe.
  * ``schemas.py`` — SectorEvaluation pydantic schema.
  * ``formatters.py`` — context formatters + RSI-zone / sector-heat pre-compute.
  * ``audit.py`` — coordinator-vs-evaluator diff audit.
  * ``__init__.py`` — sector evaluator + coordinator + run_watchlist_update_ensemble.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import cast

from pydantic_ai import Agent

from shared.agent_config import AgentConfig, build_usage_limits, load_agent_config
from shared.errors import report_caught
from shared.neon.articles import list_articles_range
from shared.neon.catalyst_summaries import get_active_geopolitical_shock
from shared.neon.catalysts import get_active_catalysts_db, get_upcoming_capital_events_db
from shared.neon.portfolio import get_portfolio_holdings
from shared.neon.watchlist import get_swing_watchlist_with_rsi
from shared.rules.catalyst_context_filter import filter_catalyst_context
from shared.vnstock_client import fetch_technicals_batch

from ..agent_factory import AgentDeps, create_agent
from ..ensemble_concurrency import gated_fanout
from ..tools.geopolitical import build_geopolitical_context
from ..watchlist_update import WatchlistUpdateResult
from ..watchlist_validators import (
    detect_churn,
    enforce_sector_cap,
    filter_existing_additions,
    flag_overbought_stocks,
    remove_portfolio_conflicts,
    validate_confidence,
)
from .audit import _audit_coordinator_diff
from .config import _ALL_TICKERS, GROUP_SECTOR_LABELS, SECTOR_GROUPS
from .formatters import (
    _compute_sector_heat,
    _format_articles,
    _format_catalysts,
    _format_portfolio_context,
    _format_previous_decisions,
    _format_technicals,
    _format_watchlist_status,
    _load_previous_report,
)
from .schemas import SectorEvaluation

logger = logging.getLogger(__name__)


async def _run_sector_evaluator(
    group_name: str,
    tickers: list[str],
    articles_ctx: str,
    catalysts_ctx: str,
    technicals_ctx: str,
    prev_decisions_ctx: str,
    watchlist_ctx: str,
    scan_date: date,
    agent: Agent[AgentDeps, SectorEvaluation],
    evaluator_config: AgentConfig,
    geopolitical_ctx: str = "",
) -> SectorEvaluation:
    """Run one sector evaluator agent and return its evaluation."""
    sector_labels = GROUP_SECTOR_LABELS[group_name]

    prompt = (
        f"## SECTOR EVALUATOR: {group_name.upper()} ({', '.join(sector_labels)})\n"
        f"Scan date: {scan_date}\n"
        f"Tickers in scope: {', '.join(tickers)}\n\n"
        f"{watchlist_ctx}\n\n"
        f"{technicals_ctx}\n\n"
        f"{articles_ctx}\n\n"
        f"{catalysts_ctx}\n\n"
        f"{prev_decisions_ctx}\n\n"
        + (f"{geopolitical_ctx}\n\n" if geopolitical_ctx else "")
        + "Evaluate each ON-WATCHLIST ticker using the REMOVAL criteria.\n"
        "Evaluate each OFF-WATCHLIST ticker using the ADDITION criteria.\n"
        "Score each using the rubric in your instructions. Only include scores >= 50 in output.\n"
        "Show your arithmetic for every score."
    )

    try:
        # HOOK-ALLOW: unguarded-agent-run reason=weekly-scope, not daily hot path
        deps = AgentDeps(scan_date=None, agent_key=evaluator_config.agent_key)
        result = await agent.run(
            prompt, deps=deps, usage_limits=build_usage_limits(evaluator_config)
        )
        return result.output
    except Exception as e:
        return SectorEvaluation(
            sector_summary=f"{group_name} evaluator failed: {e}",
            hot_sectors=[],
            cold_sectors=[],
            removals=[],
            additions=[],
            conflicts_identified=[f"Agent error: {e}"],
        )


async def _coordinate(
    evaluations: list[tuple[str, SectorEvaluation]],
    articles_ctx: str,
    scan_date: date,
    portfolio_ctx: str = "",
    pinned_ctx: str = "",
    geopolitical_ctx: str = "",
) -> WatchlistUpdateResult:
    """Merge sector evaluations into final WatchlistUpdateResult."""
    config = await load_agent_config("watchlist_coordinator")
    # HOOK-ALLOW: no-tickers-scope (coordinator merges sector evaluations)
    agent = create_agent(config, output_type=WatchlistUpdateResult)

    def _fmt_evaluation(name: str, ev: SectorEvaluation) -> str:
        lines = [f"## {name.upper()} SECTOR GROUP"]
        lines.append(f"Summary: {ev.sector_summary}")
        lines.append(f"Hot sectors: {', '.join(ev.hot_sectors) or 'None'}")
        lines.append(f"Cold sectors: {', '.join(ev.cold_sectors) or 'None'}")
        if ev.conflicts_identified:
            lines.append(f"Conflicts: {'; '.join(ev.conflicts_identified)}")
        if ev.removals:
            lines.append("\nProposed removals:")
            for r in ev.removals:
                lines.append(
                    f"  - {r.ticker} ({r.sector}): score={r.score}, confidence={r.confidence}"
                )
                for reason in r.reasons:
                    lines.append(f"    * {reason}")
        else:
            lines.append("Proposed removals: None")
        if ev.additions:
            lines.append("\nProposed additions:")
            for a in ev.additions:
                lines.append(
                    f"  - {a.ticker} ({a.sector}): score={a.score}, confidence={a.confidence}"
                )
                for reason in a.reasons:
                    lines.append(f"    * {reason}")
        else:
            lines.append("Proposed additions: None")
        return "\n".join(lines)

    context = "\n\n".join(_fmt_evaluation(name, ev) for name, ev in evaluations)

    prompt = (
        f"Scan date: {scan_date}\n\n"
        + (f"{geopolitical_ctx}\n\n" if geopolitical_ctx else "")
        + f"{portfolio_ctx}\n\n"
        f"{pinned_ctx}\n\n"
        "Here are the sector evaluation reports:\n\n"
        f"{context}\n\n"
        "Merge these into the final WatchlistUpdateResult following your coordination rules:\n"
        "- Apply diversification cap (max 2 additions per sector)\n"
        "- Resolve hot/cold sector conflicts\n"
        "- Deduplicate removals and additions by ticker\n"
        "- Do NOT add stocks already in portfolio holdings\n"
        "- Do NOT propose removing PINNED stocks\n"
        "- Generate market_summary, rotation_signal, and weekly_outlook"
    )

    try:
        # HOOK-ALLOW: unguarded-agent-run reason=weekly-scope, not daily hot path
        deps = AgentDeps(scan_date=None, agent_key=config.agent_key)
        result = await agent.run(prompt, deps=deps, usage_limits=build_usage_limits(config))
        return result.output
    except Exception as e:
        raise ValueError(f"Coordinator failed: {e}") from e


async def _safe_fetch_technicals() -> dict:
    """Fetch technicals and return empty dict on error (used in pre-fetch gather)."""
    try:
        result = await fetch_technicals_batch(_ALL_TICKERS)
        if isinstance(result, dict) and "error" in result:
            print(f"  [watchlist_ensemble] Technicals error: {result['error']}")
            return {}
        return result
    except Exception as e:
        report_caught("watchlist_ensemble.fetch_technicals", e)
        return {}


async def run_watchlist_update_ensemble(scan_date: date | None = None) -> dict:
    """Run the full watchlist update using the sector ensemble.

    Returns dict matching WatchlistUpdateResult schema — drop-in replacement
    for the old run_watchlist_update().
    """
    if scan_date is None:
        scan_date = date.today()

    week_start = scan_date - timedelta(days=7)

    print("  [watchlist_ensemble] Pre-fetching shared context...")
    _gather_result = await asyncio.gather(
        get_swing_watchlist_with_rsi(),
        list_articles_range(week_start, scan_date),
        get_active_catalysts_db(),
        get_upcoming_capital_events_db(),
        load_agent_config("watchlist_sector_evaluator"),
        _safe_fetch_technicals(),
        get_portfolio_holdings(),
        get_active_geopolitical_shock(),
    )
    watchlist_rsi_data = cast(list[dict], _gather_result[0])
    articles = cast(list[dict], _gather_result[1])
    catalysts = cast(list[dict], _gather_result[2])
    capital_events = cast(list[dict], _gather_result[3])
    evaluator_config = cast(AgentConfig, _gather_result[4])
    technicals_raw = cast(dict, _gather_result[5])
    portfolio_data = cast(list[dict], _gather_result[6])
    geopolitical_shock = cast("dict | None", _gather_result[7])

    current_watchlist: set[str] = {item["ticker"] for item in watchlist_rsi_data}
    pinned_tickers: set[str] = {
        item["ticker"] for item in watchlist_rsi_data if item.get("is_pinned")
    }
    held_tickers: set[str] = (
        {slice_row["ticker"] for slice_row in portfolio_data} if portfolio_data else set()
    )
    print(f"  [watchlist_ensemble] Current watchlist: {len(current_watchlist)} tickers")
    print(f"  [watchlist_ensemble] Pinned: {sorted(pinned_tickers) if pinned_tickers else 'none'}")
    print(f"  [watchlist_ensemble] Portfolio: {sorted(held_tickers) if held_tickers else 'none'}")

    technicals: dict = {k.upper(): v for k, v in technicals_raw.items()}
    print(f"  [watchlist_ensemble] Technicals: {len(technicals)} tickers loaded")

    prev_report = _load_previous_report()

    # HOOK-ALLOW: no-tickers-scope (evaluator reused across multiple sector groups)
    evaluator_agent = create_agent(evaluator_config, output_type=SectorEvaluation)

    sector_heat = _compute_sector_heat(technicals)
    print(f"  [watchlist_ensemble] Sector heat: {sector_heat}")

    articles_ctx = _format_articles(articles)
    ensemble_universe: set[str] = current_watchlist | held_tickers | pinned_tickers
    filtered_catalysts = filter_catalyst_context(catalysts, ensemble_universe)
    catalysts_ctx = _format_catalysts(filtered_catalysts, capital_events)
    geopolitical_ctx = build_geopolitical_context(geopolitical_shock)
    if geopolitical_ctx:
        print(
            f"  [watchlist_ensemble] Geopolitical shock active: {(geopolitical_shock or {}).get('catalyst_event', '?')}"
        )

    print(f"  [watchlist_ensemble] Running {len(SECTOR_GROUPS)} sector evaluators...")

    # Cap concurrent inflight LLM requests — one evaluator per sector group
    # would otherwise fan out unbounded on a single OpenRouter key, the
    # same tail-latency hang hazard the 2026-05-15 incident surfaced for
    # the sector ensemble. gated_fanout() is the shared cap.
    #
    # limit=2, not 1: this ensemble runs STANDALONE (weekly_watchlist_update.py,
    # bare asyncio.run — no _API_SEMAPHORE, no outer total-timeout wall), so
    # strict serialization would be a flat ~Nx wall-time hit with nothing to
    # absorb it (unlike sector.py, which runs under _API_SEMAPHORE and the
    # 7200s morning wall). The fan-out here is only len(SECTOR_GROUPS) (4)
    # evaluators — well under the 12-inflight peak that tripped 2026-05-15 —
    # so a peak of 2 stays comfortably in the safe zone while halving wall
    # time vs limit=1. Worst case: ceil(groups / 2) waves × per-evaluator
    # failover budget.
    _gated = gated_fanout(limit=2)

    async def _eval_group(group_name: str) -> tuple[str, SectorEvaluation]:
        tickers = SECTOR_GROUPS[group_name]
        ev = await _run_sector_evaluator(
            group_name,
            tickers,
            articles_ctx,
            catalysts_ctx,
            _format_technicals(technicals, tickers, sector_heat),
            _format_previous_decisions(prev_report, tickers),
            _format_watchlist_status(current_watchlist, tickers, pinned_tickers),
            scan_date,
            evaluator_agent,
            evaluator_config,
            geopolitical_ctx,
        )
        print(
            f"  [watchlist_ensemble] {group_name}: {len(ev.additions)} additions, {len(ev.removals)} removals"
        )
        return group_name, ev

    evaluations = list(await asyncio.gather(*[_gated(_eval_group(g)) for g in SECTOR_GROUPS]))

    print("  [watchlist_ensemble] Running coordinator...")
    portfolio_ctx = _format_portfolio_context(portfolio_data)
    pinned_ctx = (
        f"## PINNED STOCKS (cannot be removed, do NOT propose removal)\n"
        f"{', '.join(sorted(pinned_tickers)) if pinned_tickers else 'None'}"
    )
    result = await _coordinate(
        evaluations, articles_ctx, scan_date, portfolio_ctx, pinned_ctx, geopolitical_ctx
    )

    proposed_add_tickers = {s.ticker for _, ev in evaluations for s in ev.additions}
    coord_add_tickers = {s.ticker for s in result.additions}
    _audit_coordinator_diff("additions", proposed_add_tickers, coord_add_tickers)
    proposed_rem_tickers = {s.ticker for _, ev in evaluations for s in ev.removals}
    coord_rem_tickers = {s.ticker for s in result.removals}
    _audit_coordinator_diff("removals", proposed_rem_tickers, coord_rem_tickers)

    validated_additions = validate_confidence(result.additions, technicals)
    validated_additions = filter_existing_additions(validated_additions, current_watchlist)
    validated_additions, validated_removals = detect_churn(
        validated_additions, result.removals, prev_report
    )
    validated_additions, validated_removals = flag_overbought_stocks(
        validated_additions, validated_removals, current_watchlist, pinned_tickers, technicals
    )

    validated_removals = remove_portfolio_conflicts(
        current_watchlist, held_tickers, validated_removals
    )

    pre_filter = len(validated_additions)
    validated_additions = [a for a in validated_additions if a.ticker not in held_tickers]
    if pre_filter != len(validated_additions):
        logger.info(
            "Portfolio filter: removed %d already-held tickers from additions",
            pre_filter - len(validated_additions),
        )

    validated_additions = enforce_sector_cap(validated_additions)

    pre_filter = len(validated_additions)
    validated_additions = [a for a in validated_additions if a.score >= 50]
    if pre_filter != len(validated_additions):
        logger.info(
            "Score filter: removed %d additions with score < 50 (churn penalty)",
            pre_filter - len(validated_additions),
        )

    validated_removals = [r for r in validated_removals if r.ticker not in pinned_tickers]

    return {
        "market_summary": result.market_summary,
        "hot_sectors": result.hot_sectors,
        "cold_sectors": result.cold_sectors,
        "rotation_signal": result.rotation_signal,
        "removals": [r.model_dump() for r in validated_removals],
        "additions": [a.model_dump() for a in validated_additions],
        "weekly_outlook": result.weekly_outlook,
        "_technicals": technicals,
    }


__all__ = [
    "GROUP_SECTOR_LABELS",
    "SECTOR_GROUPS",
    "SectorEvaluation",
    "_audit_coordinator_diff",
    "_safe_fetch_technicals",
    "run_watchlist_update_ensemble",
]
