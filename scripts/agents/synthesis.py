#!/usr/bin/env python3
"""
Synthesis Agent using PydanticAI.

Combines all analyses into the final morning brief.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.types import GeopoliticalShockDict

    from .synthesis_writers import ThesisParagraph

from .synthesis_formatters import (
    _format_pre_computed_picks,
    _format_pre_computed_picks_fallback,
)
from .synthesis_validators import validate_synthesis_output


def theses_by_ticker(theses: list[ThesisParagraph]) -> dict[str, str]:
    """Adapter: list-of-objects LLM output → ticker-keyed dict for renderers.

    Last-wins on duplicate uppercased tickers; the agent validator already
    surfaces duplicates via warn log, so the dict-comprehension overwrite
    here is a deliberate quality fallback rather than a silent loss.
    """
    return {t.ticker.upper(): t.paragraph for t in theses}


# Re-export public symbols so existing callers keep working without modification
__all__ = [
    "synthesize_with_agent",
    "validate_synthesis_output",
    "_format_pre_computed_picks",
]

logger = logging.getLogger(__name__)


def _slice_to_top_picks_header(picks_text: str) -> str:
    """Drop any pre-header preamble so picks_text begins at the TOP PICKS header.

    Invariant: both producers — `_run_picks_writer` (LLM, returns
    `result.output` raw) and `_format_pre_computed_picks_fallback` — start
    their output at the `TOP PICKS` header line. A chain-of-thought preamble
    before it is an LLM leak (run2 2026-05-14, synthesis_picks narrated
    "Now I have the full picture..." into the published brief header).

    Matches the header defensively (case-insensitive, leading-whitespace
    tolerant) so "Top Picks" / "TOP PICKS (3)" still anchor. If no header
    line is found, keep the text as-is and warn — genuine format drift
    must surface, not be silently swallowed.
    """
    lines = picks_text.split("\n")
    for index, line in enumerate(lines):
        if line.strip().upper().startswith("TOP PICKS"):
            return "\n".join(lines[index:])
    logger.warning("synthesis picks_text has no TOP PICKS header line — keeping as-is")
    return picks_text


async def synthesize_with_agent(
    sector_results: list[str],
    position_alerts: dict | None,
    trading_mode: dict | None = None,
    scan_date: date | None = None,
    holdings_tickers: list[str] | None = None,
    pre_computed_picks: list[dict] | None = None,
    strategy_directive: str | None = None,
    entry_strategy: str | None = None,
    entries_blocked_reason: str | None = None,
    position_beliefs: list[dict] | None = None,
    advocate_reviews: dict | None = None,
    gated_tickers: list[dict] | None = None,
    portfolio_context: str = "",
    catalyst_context: str = "",
    regime_context: str = "",
    geopolitical_context: str = "",
    recent_trades_context: str = "",
    sector_signals: list[dict] | None = None,
    longterm_watchlist: dict[str, dict] | None = None,
    rolling_win_rate: float | None = None,
    expectancy_floor: float | None = None,
    min_rr_floor: float | None = None,
    holdings: list[dict] | None = None,
    holdings_snapshot_at: datetime | None = None,
    geo_shock: GeopoliticalShockDict | None = None,
    critic_feedback: str | None = None,
) -> str:
    """Synthesize stock-level analysis into morning brief.

    Orchestrates two focused sub-agents:
      1. synthesis_holdings — MY HOLDINGS
      2. synthesis_picks   — TOP PICKS + SKIP THESE + WHAT TO DO TODAY

    Holdings writer runs first; its EXIT tickers are passed to picks writer
    to enforce REALLOCATION mode rules.
    """
    import asyncio

    from pipeline.rendering import (
        derive_holding_actions,
        render_my_holdings,
        render_what_to_do_today,
    )
    from pipeline.rendering.skip_these import render_skip_these
    from pipeline.text_utils import extract_exit_tickers
    from shared.rules.skip_selector import select_skip_tickers

    from .synthesis_picks_writer import _run_picks_writer
    from .synthesis_writers import _run_holdings_writer

    if scan_date is None:
        scan_date = date.today()

    # Prefer split director outputs; fall back to legacy combined directive for entry_strategy
    effective_entry_strategy = entry_strategy or strategy_directive

    correlation: dict | None = None
    try:
        from .tools.correlation import compute_portfolio_correlation, get_holdings_sectors_async

        holdings_with_sectors = await get_holdings_sectors_async()
        correlation = compute_portfolio_correlation(holdings_with_sectors)
        if correlation.get("level") not in ("HIGH", "MEDIUM"):
            correlation = None  # Only pass if noteworthy
    except Exception as exc:
        logger.debug("Correlation unavailable: %s", exc)

    flow_context = ""

    # Derive the authoritative HoldingAction list first so the holdings
    # writer (qualitative thesis paragraphs only) can be composed with
    # deterministic stop/P&L/geo fields. Missing geo shock data leaves
    # the badge set empty — that's the safe default.
    victim_set: set[str] = set()
    if geo_shock:
        # `affected_tickers` is the canonical list on GeopoliticalShockDict
        # (scripts/pipeline/types.py) — treat it as downside exposure.
        victim_set = {str(t).upper() for t in (geo_shock.get("affected_tickers") or [])}

    # derive_holding_actions expects {ticker: row} for MY HOLDINGS enrichment;
    # SWING-preferred collapse preserves the MY HOLDINGS card contract.
    from shared.neon import collapse_holdings_by_ticker

    portfolio_rows = collapse_holdings_by_ticker(holdings) if holdings else None

    holdings_actions = derive_holding_actions(
        position_alerts,
        holdings_tickers,
        portfolio_rows=portfolio_rows,
        impacted_tickers_victim=victim_set,
    )

    try:
        holdings_theses = await _run_holdings_writer(
            held_actions=holdings_actions,
            position_alerts=position_alerts,
            correlation=correlation,
            trading_mode=trading_mode,
            flow_context=flow_context,
            scan_date=scan_date,
            position_beliefs=position_beliefs,
            portfolio_context=portfolio_context,
            catalyst_context=catalyst_context,
            regime_context=regime_context,
            geopolitical_context=geopolitical_context,
            recent_trades_context=recent_trades_context,
        )
    except Exception as e:
        return f"Synthesis failed (holdings writer): {e}\n\nRaw sector analyses:\n" + "\n\n".join(
            sector_results
        )

    # Step 1b: Render MY HOLDINGS deterministically from the action list +
    # per-ticker thesis paragraphs. No LLM paraphrase of stop prices,
    # P/L, or shock-phase labels.
    holdings_text = render_my_holdings(
        holdings_actions,
        theses_by_ticker(holdings_theses.theses),
        snapshot_at=holdings_snapshot_at,
    )

    # Step 2: Extract EXIT tickers from the rendered holdings text
    # (regex stays unchanged — the renderer keeps "EXIT <TICKER>" headers).
    exit_tickers = extract_exit_tickers(holdings_text)

    # Step 2b: Resolve SKIP THESE ticker set up front (MON-2026-04-23-001) so
    # the picks writer can be told which tickers are already owned by SKIP
    # and must never appear in TOP PICKS. Same inputs feed the rec-builder,
    # guaranteeing brief-DB parity.
    top_pick_tickers = {
        (p.get("ticker") or "").upper() for p in pre_computed_picks or [] if p.get("ticker")
    }
    holdings_ticker_set = {(t or "").upper() for t in holdings_tickers or []}
    skip_exclusions = top_pick_tickers | holdings_ticker_set
    skip_entries = select_skip_tickers(
        sector_signals=sector_signals,
        gated_tickers=gated_tickers,
        exclusions=skip_exclusions,
    )
    skip_ticker_set = {entry["ticker"] for entry in skip_entries}

    # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
    try:
        # Step 3: Picks writer with holdings context (900s timeout guard —
        # fits the latency-triage per-agent budget: 3 * 75s primary +
        # 120s fallback = 345s, with parallelism headroom (SWI-318).
        # HOOK-ALLOW: outer-wall-helper rationale=SWI-306 orchestration wall over picks_writer (single agent, but 900s = 5× single-agent fallback budget — orchestration headroom for parallel sub-tasks).
        picks_text = await asyncio.wait_for(
            _run_picks_writer(
                entry_strategy=effective_entry_strategy,
                sector_results=sector_results,
                pre_computed_picks=pre_computed_picks,
                entries_blocked_reason=entries_blocked_reason,
                trading_mode=trading_mode,
                exit_tickers=exit_tickers,
                scan_date=scan_date,
                advocate_reviews=advocate_reviews,
                skip_tickers=skip_ticker_set,
                catalyst_context=catalyst_context,
                regime_context=regime_context,
                holdings_tickers=holdings_tickers,
                longterm_watchlist=longterm_watchlist,
                rolling_win_rate=rolling_win_rate,
                expectancy_floor=expectancy_floor,
                min_rr_floor=min_rr_floor,
                critic_feedback=critic_feedback,
            ),
            timeout=900,
        )
    except Exception as e:
        # Any picks-writer failure (timeout, usage-limit, provider error,
        # validation) is recoverable because `pre_computed_picks` is already
        # computed deterministically upstream. Log the exception for debugging
        # and render deterministic picks instead of leaking stringified
        # exceptions into the user-facing morning brief.
        # Historical leaks this covers: TimeoutError (2026-04-21),
        # UsageLimitExceeded (2026-04-08, 2026-04-09).
        logger.warning(
            "synthesis_picks failed for %s (%s: %s) — using deterministic picks fallback",
            scan_date,
            type(e).__name__,
            e,
            exc_info=True,
        )
        picks_text = _format_pre_computed_picks_fallback(pre_computed_picks, sector_results)

    # Step 3b: Render SKIP THESE deterministically from the ticker list
    # resolved in Step 2b.
    skip_text = render_skip_these(skip_entries)

    # Step 4: Render WHAT TO DO TODAY deterministically from structured
    # holding actions + picks (MON-2026-04-16-002). No LLM prose drift.
    # Reuses the same ``holdings_actions`` built in Step 1 so MY HOLDINGS
    # and WHAT TO DO TODAY cannot diverge (HoldingAction is the single
    # canonical extraction — 2d9ff035).
    wttt_text = render_what_to_do_today(
        holdings_actions=holdings_actions,
        top_picks=pre_computed_picks,
        min_rr_floor=min_rr_floor,
        max_new_entries=(trading_mode or {}).get("max_new_entries"),
    )

    # Step 4b: Structurally enforce the "picks_text begins at TOP PICKS"
    # invariant — drops any LLM chain-of-thought preamble before assembly.
    picks_text = _slice_to_top_picks_header(picks_text)

    # Step 5: Merge outputs (MY HOLDINGS → TOP PICKS → SKIP THESE → WHAT TO DO TODAY)
    brief = f"{holdings_text}\n\n{picks_text}\n\n{skip_text}\n\n{wttt_text}"

    # Step 6: Validate merged output against trading mode rules
    mode = trading_mode.get("mode") if trading_mode else None
    deployable = None
    if trading_mode and mode in ("LOW_CASH", "REALLOCATION"):
        deployable = 0  # Conservative assumption for validation

    brief, warnings = validate_synthesis_output(
        brief, mode, deployable, pre_computed_picks=pre_computed_picks
    )

    if warnings:
        # DELIBERATE: publish-with-stub policy (commits 4eb608da 2026-04-16,
        # 43dbdbef 2026-04-19). Mode-compliance warnings append to the brief;
        # the brief still publishes — banners + warnings make crashes visually
        # distinguishable from clean runs. Do NOT add a publish gate here;
        # user reviewed 2026-05-14 and re-affirmed.
        warning_text = "\n\nMODE COMPLIANCE WARNINGS\n" + "\n".join(
            f"- {warning}" for warning in warnings
        )
        brief = brief + warning_text

    return brief
