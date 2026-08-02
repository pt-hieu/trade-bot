"""Portfolio domain tools — trades, learnings, watchlist, positions, research, thesis."""

import asyncio
import json as _json
import logging
from datetime import date
from typing import Literal

from ...types import RequiredTickers
from ..helpers import batch_cache_key, cached_tool_call, prose_formatter
from ..registry import ToolDomain, register_domain_tool

logger = logging.getLogger(__name__)

LearningsQuery = Literal[
    "summary",
    "winning_patterns",
    "losing_patterns",
    "sector_bias",
    "ticker_accuracy",
    "midday_insights",
    "mode_compliance",
    "rotation_patterns",
    "macro_patterns",
    "calibration",
]


async def get_trades() -> str:
    """Get recent trades including today's exits/entries.

    Returns:
        Prose listing the 5 most recent trades (open or closed) ordered by
        COALESCE(exit_date, entry_date) DESC, with ticker, status, entry/exit,
        P&L % and strategy per trade.
    """
    from ...portfolio import get_recent_trades_async

    result = await get_recent_trades_async(limit=5)
    return prose_formatter(result)


async def get_learnings(
    query: LearningsQuery,
    sector: str | None = None,
    ticker: str | None = None,
    action: str | None = None,
) -> str:
    """Get historical learnings with selective retrieval.

    Args:
        query: ONE OF (case-sensitive enum):
            summary | winning_patterns | losing_patterns | sector_bias |
            ticker_accuracy | midday_insights | mode_compliance |
            rotation_patterns | macro_patterns | calibration.
        sector: Optional sector filter (e.g. "banking").
        ticker: Optional ticker filter (e.g. "FPT").
        action: Optional action filter.

    Example invocation (use the broker's `call_tools` meta-tool):
        call_tools([{
            "name": "portfolio.get_learnings",
            "args": {"query": "winning_patterns", "sector": "banking"}
        }])

    Returns:
        str(dict) — {query, data[, count, hot, cold, error]}. `data` shape
        varies per query: summary→metrics dict, winning/losing_patterns→list,
        sector_bias→hot/cold arrays.
    """
    from ...portfolio import get_learnings_async

    result = await get_learnings_async(query=query, sector=sector, ticker=ticker, action=action)
    return str(result)


async def get_watchlist() -> str:
    """Get long-term watchlist with entry zones, conviction, sector.

    Returns:
        Stringified dict with top-level {watchlist, prose}. `watchlist` is
        keyed by ticker with per-entry {sector, conviction, entry_zone, ...};
        `prose` is a readable summary of the same data.
    """
    from ...portfolio import get_longterm_watchlist_async

    result = await get_longterm_watchlist_async()
    return str(result)


async def get_position_scale() -> str:
    """Get position sizing multiplier based on recent win rate.
    MUST call this before calculating position sizes for TOP PICKS.

    Returns:
        Stringified dict with {scale_factor (0.5-1.0 float), win_rate,
        swing_win_rate, swing_sample_size, shock_multiplier, note, prose}.
        `prose` is a one-line readable summary.
    """
    from ...portfolio import get_position_scale_factor

    result = await get_position_scale_factor()
    return str(result)


async def get_executed_trades(*, _ctx: dict) -> str:
    """Get trades actually executed today (opened or closed).

    Returns:
        Stringified dict with {opened: list[dict], closed: list[dict],
        prose: str}. Each opened/closed entry has ticker, shares, price,
        and pnl_vnd (closed only). Empty lists if no trades today.
    """
    from ...portfolio import get_trades_for_date_async

    raw_scan_date = _ctx.get("scan_date")
    scan_date_val: date = raw_scan_date if isinstance(raw_scan_date, date) else date.today()
    result = await get_trades_for_date_async(scan_date_val)
    return str(result)


async def get_longterm_config(tickers: RequiredTickers) -> str:
    """Check if one or more tickers are in the long-term watchlist.
    Pass a list like ['FPT', 'TCB'].

    Returns:
        Stringified dict keyed by UPPER(ticker). Each value is either
        {is_longterm: True, ...config_fields} for longterm names, or
        {is_longterm: False, note: "{ticker} is a swing position"} for
        swing names. All requested tickers always appear in the output.
    """
    from ...portfolio import get_longterm_watchlist_async

    watchlist = await get_longterm_watchlist_async()
    results = {}
    for ticker in tickers:
        upper_ticker = ticker.upper()
        if isinstance(watchlist, dict) and upper_ticker in watchlist:
            config = dict(watchlist[upper_ticker])
            config["is_longterm"] = True
            results[upper_ticker] = config
        else:
            results[upper_ticker] = {
                "is_longterm": False,
                "note": f"{upper_ticker} is a swing position",
            }
    return str(results)


_RESEARCH_SECTION_ORDER = (
    "overview",
    "financials",
    "moat",
    "management",
    "growth",
    "risks",
    "valuation",
    "thesis",
)


def _format_research_prose(ticker: str, research: dict | None) -> str:
    """Format a single ticker's research sections as prose."""
    upper = ticker.upper()
    if research and research.get("sections"):
        sections = research["sections"]
        parts: list[str] = []
        for key in _RESEARCH_SECTION_ORDER:
            if key in sections:
                parts.append(f"[{key.upper()}]\n{sections[key][:600]}")
        if parts:
            return f"=== {upper} ===\n" + "\n\n".join(parts)
    return f"No research available for {upper}"


async def _fetch_research_prose(tickers: list[str]) -> str:
    from shared.neon.longterm import get_company_research_batch

    batch = await get_company_research_batch(tickers)
    return "\n\n".join(
        _format_research_prose(ticker, batch.get(ticker.upper())) for ticker in tickers
    )


async def read_research(tickers: RequiredTickers, *, _ctx: dict) -> str:
    """Read detailed research notes for one or more stocks.

    Returns:
        Prose block per ticker with sections (overview, financials, moat,
        management, growth, risks, valuation, thesis), each capped at
        600 chars. "No research available for {ticker}" when missing.
    """
    cache = _ctx.get("_tool_cache")
    return await cached_tool_call(
        cache,
        batch_cache_key("portfolio.read_research", tickers),
        lambda: _fetch_research_prose(tickers),
    )


async def _fetch_ensemble_history_prose(tickers: list[str], days_back: int) -> str:
    from ...portfolio import get_ensemble_history_batch_async

    batch = await get_ensemble_history_batch_async(tickers, days_back)
    return "\n\n".join(prose_formatter(batch.get(ticker.upper(), {})) for ticker in tickers)


async def get_ensemble_history(tickers: RequiredTickers, days_back: int = 7, *, _ctx: dict) -> str:
    """Get historical analyst ensemble votes for one or more positions.
    Shows if EXIT/TRIM has been consistently signaled.

    Returns:
        Prose block per ticker with daily vote counts by action
        (BUY/HOLD/TRIM/EXIT) over `days_back` days, plus majority-action
        trend. Empty if no votes recorded.
    """
    cache = _ctx.get("_tool_cache")
    return await cached_tool_call(
        cache,
        batch_cache_key("portfolio.get_ensemble_history", tickers, days_back),
        lambda: _fetch_ensemble_history_prose(tickers, days_back),
    )


async def get_sector_allocation() -> str:
    """Get sector allocation targets vs actual holdings with drift analysis.

    Returns:
        Prose table listing each sector's target_pct, actual_pct, and
        drift (OVER/UNDER/ON_TARGET), plus overall concentration warning.
    """
    from ...portfolio import get_sector_allocation_async

    result = await get_sector_allocation_async()
    return prose_formatter(result)


async def get_retro_constraints(*, _ctx: dict) -> str:
    """Get hard trading constraints derived from historical win/loss patterns.
    Use this before recommending new entries.

    Returns:
        str(dict) — {max_entries, scale_override, min_rr_override,
        avoid_actions[], constraint_text, win_rate}. Fail-closed:
        constraint_text="RETRO CONSTRAINTS - Unavailable" on data gaps.
    """
    from ...retro_constraints import compute_retro_constraints

    scan_date = _ctx.get("scan_date")
    result = await compute_retro_constraints(scan_date)
    return str(result)


def format_thesis_prose(ticker: str, thesis: dict | None, updates: list[dict]) -> str:
    """Format a single ticker's thesis state as prose."""
    upper = ticker.upper()
    if not thesis:
        return f"No thesis tracked for {upper} yet."

    lines = [f"THESIS: {upper} — {thesis.get('overall_thesis_status') or 'UNKNOWN'}"]

    pillars = thesis.get("pillars") or []
    if isinstance(pillars, str):
        pillars = _json.loads(pillars)
    if pillars:
        lines.append("\nPillars:")
        for pillar in pillars:
            status = pillar.get("status") or "?"
            name = pillar.get("name") or ""
            evidence = pillar.get("evidence") or ""
            lines.append(f"  [{status}] {name}: {evidence}")

    kill = thesis.get("kill_criteria") or []
    if isinstance(kill, str):
        kill = _json.loads(kill)
    active_kill = [k for k in kill if k.get("status") in ("WARNING", "TRIGGERED")]
    if active_kill:
        lines.append("\nKill Criteria (active):")
        for kill_item in active_kill:
            status = kill_item.get("status") or "?"
            condition = kill_item.get("condition") or ""
            lines.append(f"  [{status}] {condition}")

    if updates:
        lines.append(
            f"\nLast updated: {updates[0].get('update_date')} via {updates[0].get('source')}"
        )
    return "\n".join(lines)


async def fetch_thesis_prose_by_ticker(tickers: list[str]) -> dict[str, str]:
    """Fetch thesis prose per ticker as `{TICKER: prose}`. Shared by the broker
    tool (which joins to a single string) and Phase-0 injection (which keeps
    the dict for per-ticker truncation).
    """
    from shared.thesis_tracker import get_thesis_batch, get_thesis_updates_batch

    if not tickers:
        return {}
    try:
        theses, updates = await asyncio.gather(
            get_thesis_batch(tickers),
            get_thesis_updates_batch(tickers, limit_per_ticker=3),
        )
    except Exception as error:
        logger.warning("portfolio.get_thesis batch failed: %s", error)
        return {
            ticker.upper(): f"{ticker.upper()}: Thesis data unavailable: {error}"
            for ticker in tickers
        }

    return {
        ticker.upper(): format_thesis_prose(
            ticker,
            theses.get(ticker.upper()),
            updates.get(ticker.upper(), []),
        )
        for ticker in tickers
    }


async def _fetch_thesis_prose(tickers: list[str]) -> str:
    by_ticker = await fetch_thesis_prose_by_ticker(tickers)
    return "\n\n".join(
        by_ticker[ticker.upper()] for ticker in tickers if ticker.upper() in by_ticker
    )


async def get_thesis(tickers: RequiredTickers, *, _ctx: dict) -> str:
    """Get thesis tracker for one or more stocks: pillars, kill criteria, conviction history.

    Returns:
        Prose block per ticker: overall status (INTACT/WEAKENING/BROKEN),
        pillars with per-pillar status + evidence, active kill criteria
        (WARNING/TRIGGERED), last update. "No thesis tracked for {ticker}
        yet" when missing.
    """
    cache = _ctx.get("_tool_cache")
    return await cached_tool_call(
        cache,
        batch_cache_key("portfolio.get_thesis", tickers),
        lambda: _fetch_thesis_prose(tickers),
    )


register_domain_tool(
    "portfolio.get_trades",
    ToolDomain.PORTFOLIO,
    get_trades,
    returns_hint="prose — 5 most recent trades (open + closed)",
)
register_domain_tool(
    "portfolio.get_learnings",
    ToolDomain.PORTFOLIO,
    get_learnings,
    returns_hint="str(dict) — {query, data} (data shape varies)",
)
register_domain_tool(
    "portfolio.get_watchlist",
    ToolDomain.PORTFOLIO,
    get_watchlist,
    returns_hint="str(dict) — {watchlist[ticker→...], prose}",
)
register_domain_tool(
    "portfolio.get_position_scale",
    ToolDomain.PORTFOLIO,
    get_position_scale,
    returns_hint="str(dict) — {scale_factor, win_rate, note, prose}",
)
register_domain_tool(
    "portfolio.get_executed_trades",
    ToolDomain.PORTFOLIO,
    get_executed_trades,
    context_keys=("scan_date",),
    returns_hint="str(dict) — {opened[], closed[], prose}",
)
register_domain_tool(
    "portfolio.get_longterm_config",
    ToolDomain.PORTFOLIO,
    get_longterm_config,
    accepts_tickers=True,
    returns_hint="str(dict[TICKER→{is_longterm, ...|note}])",
)
register_domain_tool(
    "portfolio.read_research",
    ToolDomain.PORTFOLIO,
    read_research,
    context_keys=("_tool_cache",),
    accepts_tickers=True,
    returns_hint="prose per ticker — 8 research sections",
)
register_domain_tool(
    "portfolio.get_ensemble_history",
    ToolDomain.PORTFOLIO,
    get_ensemble_history,
    context_keys=("_tool_cache",),
    accepts_tickers=True,
    returns_hint="prose per ticker — daily ensemble votes",
)
register_domain_tool(
    "portfolio.get_sector_allocation",
    ToolDomain.PORTFOLIO,
    get_sector_allocation,
    returns_hint="prose — target vs actual + drift",
)
register_domain_tool(
    "portfolio.get_retro_constraints",
    ToolDomain.PORTFOLIO,
    get_retro_constraints,
    context_keys=("scan_date",),
    returns_hint="str(dict) — {max_entries, scale, avoid, constraint_text}",
)
register_domain_tool(
    "portfolio.get_thesis",
    ToolDomain.PORTFOLIO,
    get_thesis,
    context_keys=("_tool_cache",),
    accepts_tickers=True,
    returns_hint="prose per ticker — pillars + kill criteria",
)
