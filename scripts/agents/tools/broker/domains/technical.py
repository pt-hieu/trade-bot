"""Technical domain tools — technicals, trade setup."""

from datetime import date

from ...types import RequiredTickers
from ..helpers import batch_cache_key, cached_tool_call
from ..registry import ToolDomain, register_domain_tool


def _scan_date(_ctx: dict) -> date | None:
    raw = _ctx.get("scan_date")
    return raw if isinstance(raw, date) else None


async def _fetch_technicals(tickers: list[str], scan_date: date | None) -> str:
    from ...technicals import get_batch_ticker_data_async

    batch = await get_batch_ticker_data_async(tickers, scan_date)
    return str({ticker.upper(): batch.get(ticker.upper(), {}) for ticker in tickers})


async def _fetch_trade_setup(tickers: list[str], scan_date: date | None) -> str:
    from ...technicals import compute_batch_trade_setup_async

    batch = await compute_batch_trade_setup_async(tickers, scan_date)
    return str({ticker.upper(): batch.get(ticker.upper(), {}) for ticker in tickers})


async def get_technicals(tickers: RequiredTickers, *, _ctx: dict) -> str:
    """Get RSI, MACD, MA, support/resistance for one or more tickers.
    Pass a list like ['FPT', 'TCB'].

    Returns:
        str(dict) keyed by UPPER(ticker). Each value includes {close, rsi,
        macd, trend, levels, prose, trade_setup, price_action}. `trade_setup`
        is pre-computed with {entry, stop, target, risk_reward, shares,
        valid}. Missing data: {ticker, error}.
    """
    scan_date = _scan_date(_ctx)
    cache = _ctx.get("_tool_cache")
    return await cached_tool_call(
        cache,
        batch_cache_key("technical.get_technicals", tickers, scan_date),
        lambda: _fetch_technicals(tickers, scan_date),
    )


async def calculate_trade_setup(tickers: RequiredTickers, *, _ctx: dict) -> str:
    """Calculate deterministic Entry/Stop/Target/R:R from technical levels.
    Pass a list like ['FPT', 'TCB'].
    MUST use for every BUY/ADD recommendation. Only recommend if valid=True.

    Returns:
        str(dict) keyed by UPPER(ticker). Each value is a trade setup with
        {entry, stop, target, risk_reward (raw float net-of-cost),
        risk_reward_gross, target_basis ("conservative"|"aggressive"),
        rr_stretch (optional display hint), shares, position_vnd, valid,
        close, levels_used}. On failure: {ticker, valid: False, error}.
    """
    scan_date = _scan_date(_ctx)
    cache = _ctx.get("_tool_cache")
    return await cached_tool_call(
        cache,
        batch_cache_key("technical.calculate_trade_setup", tickers, scan_date),
        lambda: _fetch_trade_setup(tickers, scan_date),
    )


register_domain_tool(
    "technical.get_technicals",
    ToolDomain.TECHNICAL,
    get_technicals,
    context_keys=("scan_date", "_tool_cache"),
    accepts_tickers=True,
    returns_hint="str(dict[TICKER→{rsi, macd, levels, trade_setup, prose}])",
)
register_domain_tool(
    "technical.calculate_trade_setup",
    ToolDomain.TECHNICAL,
    calculate_trade_setup,
    context_keys=("scan_date", "_tool_cache"),
    accepts_tickers=True,
    returns_hint="str(dict[TICKER→{entry, stop, target, rr, valid}])",
)
