"""Fundamental domain tools — valuation, financial health, comparison, history, earnings, comps.

Note: the vnstock API is single-symbol for these endpoints, so the `_gather_*`
helpers still run per-ticker via `asyncio.gather`. This is the exception to
the batch invariant — pushing batch through to the HTTP layer would require
a new `/fundamentals/batch` endpoint, tracked as a deferred item.
"""

import asyncio
import logging

from shared.lint_markers import allow_single_ticker_fetcher

from ...types import RequiredTickers
from ..helpers import batch_cache_key, cached_tool_call, prose_formatter
from ..registry import ToolDomain, register_domain_tool

logger = logging.getLogger(__name__)


async def _gather_valuation(tickers: list[str]) -> str:
    from ...fundamentals import get_valuation_async

    results = await asyncio.gather(*[get_valuation_async(ticker) for ticker in tickers])
    return "\n\n".join(prose_formatter(result) for result in results)


async def _gather_financial_health(tickers: list[str]) -> str:
    from ...fundamentals import get_financial_health_async

    results = await asyncio.gather(*[get_financial_health_async(ticker) for ticker in tickers])
    return "\n\n".join(prose_formatter(result) for result in results)


async def _gather_valuation_history(tickers: list[str]) -> str:
    from ...fundamentals import tool_get_valuation_history as _impl

    results = await asyncio.gather(*[_impl(ticker) for ticker in tickers])
    return "\n\n".join(results)


async def _gather_earnings_quality(tickers: list[str]) -> str:
    from ...fundamentals import tool_get_earnings_quality as _impl

    results = await asyncio.gather(*[_impl(ticker) for ticker in tickers])
    return "\n\n".join(results)


async def get_valuation(tickers: RequiredTickers, *, _ctx: dict) -> str:
    """Get PE, PB, ROE, margins, D/E with trend for one or more tickers.
    Pass a list like ['FPT', 'TCB'].

    Returns:
        Prose block per ticker with latest PE/PB/ROE/ROA/margins/D/E,
        quarter-over-quarter trend directions, and multi-quarter moat
        signals (consistent ROE, margin stability). Blocks joined by
        blank lines. CHEAP/FAIR/EXPENSIVE labels live in get_valuation_history.
    """
    cache = _ctx.get("_tool_cache")
    return await cached_tool_call(
        cache,
        batch_cache_key("fundamental.get_valuation", tickers),
        lambda: _gather_valuation(tickers),
    )


async def get_financial_health(tickers: RequiredTickers, *, _ctx: dict) -> str:
    """Get income statement and balance sheet highlights for one or more tickers.

    Returns:
        Prose block per ticker with revenue/net income/EBITDA (income
        side) and total assets/debt/equity/cash (balance side) — latest
        quarter plus YoY change.
    """
    cache = _ctx.get("_tool_cache")
    return await cached_tool_call(
        cache,
        batch_cache_key("fundamental.get_financial_health", tickers),
        lambda: _gather_financial_health(tickers),
    )


async def get_comparison(tickers: list[str], *, _ctx: dict) -> str:
    """Compare PE, PB, ROE, margins, D/E side-by-side across multiple tickers.

    Returns:
        Prose table with one column per ticker and one row per metric
        (PE, PB, ROE, Net Margin, D/E). Highlights the best and worst
        on each row.
    """
    from ...fundamentals import tool_get_financial_comparison as _impl

    cache = _ctx.get("_tool_cache")
    return await cached_tool_call(
        cache,
        batch_cache_key("fundamental.get_comparison", tickers),
        lambda: _impl(tickers),
    )


async def get_valuation_history(tickers: RequiredTickers, *, _ctx: dict) -> str:
    """Get 8-quarter valuation percentiles and EPS/margin trajectory for one or more tickers.

    Shows where PE/PB/ROE/margin sits in its own history (CHEAP/FAIR/EXPENSIVE/EXTREME).
    Use before assigning BUY — expensive stocks need stronger confirmation.

    Returns:
        Prose block per ticker with 8Q percentile ranks for PE/PB/ROE,
        EPS trajectory (growing/flat/declining), margin trend, and a
        CHEAP/FAIR/EXPENSIVE/EXTREME verdict per metric.
    """
    cache = _ctx.get("_tool_cache")
    return await cached_tool_call(
        cache,
        batch_cache_key("fundamental.get_valuation_history", tickers),
        lambda: _gather_valuation_history(tickers),
    )


async def get_earnings_quality(tickers: RequiredTickers, *, _ctx: dict) -> str:
    """Decompose 4Q earnings into core operating profit vs non-core items for one or more tickers.

    Core ratio < 50% signals asset revaluation, financial income, or JV gains —
    common in Vietnamese BDS stocks. Always check before high-conviction calls.

    Returns:
        Prose block per ticker with 4Q core operating profit, non-core
        components (financial income, JV gains, asset revaluation), core
        ratio percentage, and a HIGH/MEDIUM/LOW quality verdict.
    """
    cache = _ctx.get("_tool_cache")
    return await cached_tool_call(
        cache,
        batch_cache_key("fundamental.get_earnings_quality", tickers),
        lambda: _gather_earnings_quality(tickers),
    )


# Section headers emitted by `get_full_analysis`. Agent prompts in
# positions_value.yaml / positions_thesis.yaml / longterm_review.yaml read
# sections positionally — pytest pins these strings so drift fails loudly.
VALUATION_HEADER = "=== VALUATION ==="
EARNINGS_QUALITY_HEADER = "=== EARNINGS QUALITY ==="
VALUATION_HISTORY_HEADER = "=== VALUATION HISTORY ==="


async def gather_full_analysis_by_ticker(tickers: list[str]) -> dict[str, str]:
    """Valuation + earnings quality + 8Q history per ticker as `{TICKER: prose}`.

    Calls each section helper once over the whole batch (`_gather_*` already
    parallelizes per ticker internally), then splits the positional results
    back per ticker. Avoids the N-fold cache fragmentation that a per-ticker
    `_gather_full_analysis([t])` loop would cause.
    """
    if not tickers:
        return {}
    from ...fundamentals import (
        get_valuation_async,
        tool_get_earnings_quality,
        tool_get_valuation_history,
    )

    valuation_results, eq_results, vh_results = await asyncio.gather(
        asyncio.gather(*[get_valuation_async(ticker) for ticker in tickers]),
        asyncio.gather(*[tool_get_earnings_quality(ticker) for ticker in tickers]),
        asyncio.gather(*[tool_get_valuation_history(ticker) for ticker in tickers]),
    )
    return {
        ticker.upper(): (
            f"{VALUATION_HEADER}\n"
            f"{prose_formatter(valuation_results[index])}\n\n"
            f"{EARNINGS_QUALITY_HEADER}\n"
            f"{eq_results[index]}\n\n"
            f"{VALUATION_HISTORY_HEADER}\n"
            f"{vh_results[index]}"
        )
        for index, ticker in enumerate(tickers)
    }


async def _gather_full_analysis(tickers: list[str]) -> str:
    """Valuation + earnings quality + 8Q valuation history in parallel.

    Thin wrapper: defers to `gather_full_analysis_by_ticker` so the per-ticker
    dict path and the broker tool's joined-string path share one fetch+gather.
    """
    by_ticker = await gather_full_analysis_by_ticker(tickers)
    return "\n\n".join(
        by_ticker[ticker.upper()] for ticker in tickers if ticker.upper() in by_ticker
    )


async def get_full_analysis(tickers: RequiredTickers, *, _ctx: dict) -> str:
    """Full fundamental review: valuation + earnings quality + 8Q valuation history.

    Returns one consolidated string with three sections per ticker. Call this
    instead of the 3 individual tools when you need the complete fundamental
    picture — saves 2 LLM round-trips vs calling them separately.

    Returns:
        Prose with three labeled sections per ticker:
        === VALUATION === (current ratios + trend)
        === EARNINGS QUALITY === (core vs non-core decomposition)
        === VALUATION HISTORY === (8Q percentiles + EPS trajectory)
    """
    cache = _ctx.get("_tool_cache")
    return await cached_tool_call(
        cache,
        batch_cache_key("fundamental.get_full_analysis", tickers),
        lambda: _gather_full_analysis(tickers),
    )


@allow_single_ticker_fetcher  # comps compares ONE target against peers; batching the target is semantically wrong
async def get_comps(ticker: str, peers: list[str] | None = None) -> str:
    """Compare a stock against sector peers on operating and valuation metrics.

    Returns a statistics table (max/p75/median/p25/min) and target's
    percentile rank for each metric. Metrics are sector-specific:
    banking uses ROE/ROA/NIM, real estate uses margins/D/E, etc.

    Args:
        ticker: Target stock symbol (e.g., 'TCB')
        peers: Peer tickers to compare against. If None, uses same-sector
               tickers from swing/longterm watchlists automatically.

    Returns:
        Prose table with peer-group statistics (max/p75/median/p25/min)
        per metric plus the target's percentile rank on each row.
        "No sector peers found" when peer list is empty.
    """
    from shared.neon.watchlist import get_sector_peers

    from ...comps import compute_comps, format_comps_prose

    try:
        peer_list = peers or await get_sector_peers(ticker)
        if not peer_list:
            return f"No sector peers found for {ticker}."
        comps = await compute_comps(ticker, peer_list)
        return format_comps_prose(comps)
    except Exception as error:
        logger.warning("fundamental.get_comps failed for %s: %s", ticker, error)
        return f"Comps unavailable for {ticker}: {error}"


register_domain_tool(
    "fundamental.get_valuation",
    ToolDomain.FUNDAMENTAL,
    get_valuation,
    context_keys=("_tool_cache",),
    accepts_tickers=True,
    returns_hint="prose per ticker — PE/PB/ROE + 4Q trend",
)
register_domain_tool(
    "fundamental.get_financial_health",
    ToolDomain.FUNDAMENTAL,
    get_financial_health,
    context_keys=("_tool_cache",),
    accepts_tickers=True,
    returns_hint="prose per ticker — income + balance sheet",
)
register_domain_tool(
    "fundamental.get_comparison",
    ToolDomain.FUNDAMENTAL,
    get_comparison,
    context_keys=("_tool_cache",),
    returns_hint="prose table — side-by-side ratios across tickers",
)
register_domain_tool(
    "fundamental.get_valuation_history",
    ToolDomain.FUNDAMENTAL,
    get_valuation_history,
    context_keys=("_tool_cache",),
    accepts_tickers=True,
    returns_hint="prose per ticker — 8Q percentiles + trajectory",
)
register_domain_tool(
    "fundamental.get_earnings_quality",
    ToolDomain.FUNDAMENTAL,
    get_earnings_quality,
    context_keys=("_tool_cache",),
    accepts_tickers=True,
    returns_hint="prose per ticker — core vs non-core ratio",
)
register_domain_tool(
    "fundamental.get_full_analysis",
    ToolDomain.FUNDAMENTAL,
    get_full_analysis,
    context_keys=("_tool_cache",),
    accepts_tickers=True,
    returns_hint="prose — 3 sections: VALUATION, EQ, HISTORY",
    supersedes=(
        "fundamental.get_valuation",
        "fundamental.get_earnings_quality",
        "fundamental.get_valuation_history",
    ),
)
register_domain_tool(
    "fundamental.get_comps",
    ToolDomain.FUNDAMENTAL,
    get_comps,
    returns_hint="prose table — peer stats + percentile rank",
)
