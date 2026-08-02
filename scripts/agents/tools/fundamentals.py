#!/usr/bin/env python3
"""
Fundamental analysis tools for PydanticAI agents.

All functions are async to share the event loop with agents.
"""

from shared.api.earnings_quality import compute_earnings_quality
from shared.api.earnings_quality import format_earnings_quality_prose as _fmt_eq_prose
from shared.api.fundamentals import get_financial_ratios as _get_ratios
from shared.api.fundamentals import (
    get_financial_ratios_batch as _get_financial_ratios_batch,
)
from shared.api.fundamentals import get_latest_financial_statement as _get_latest_stmt
from shared.api.valuation_history import compute_valuation_history
from shared.api.valuation_history import format_valuation_history_prose as _fmt_vh_prose
from shared.formatting import format_vnd as _format_vnd_base
from shared.lint_markers import allow_single_ticker_fetcher

# ── Prose Formatters ────────────────────────────────────────────────────────


def _fmt(v, suffix: str = "", pct: bool = False) -> str:
    """Format a numeric value for display.

    For pct=True, values are already whole-number % (23.0 = 23%).
    """
    if v is None:
        return "N/A"
    if pct:
        return f"{v:.1f}%"
    return f"{v:.2f}{suffix}"


def _pick(data: dict, *keys) -> float | None:
    """Pick the first non-None value from multiple possible field names (rule 13)."""
    for k in keys:
        val = data.get(k)
        if val is not None and val != 0:
            return val
    return None


def _format_health_prose(ticker: str, income: dict | None, balance: dict | None) -> str:
    """Format financial health summary as prose.

    VCI API field names: 'Net sales', 'Gross Profit', 'Net profit/(loss) after tax',
    'Attributable to parent company', 'Total Assets', "Owner's Equity", 'Liabilities', etc.
    """
    lines = [f"Financial Health — {ticker}:"]

    if income:
        data = income["data"]
        period = income["report_period"]
        revenue = _pick(data, "Net sales", "Net Revenue", "net_revenue", "Revenue", "Sales")
        net_income = _pick(
            data,
            "Net profit/(loss) after tax",
            "Attributable to parent company",
            "netIncome",
            "net_income",
        )
        gross_profit = _pick(data, "Gross Profit", "gross_profit")
        lines.append(f"Latest ({period}):")
        if revenue:
            lines.append(f"  Revenue: {_fmt_vnd(revenue)}")
        if gross_profit:
            lines.append(f"  Gross Profit: {_fmt_vnd(gross_profit)}")
        if net_income:
            lines.append(f"  Net Income: {_fmt_vnd(net_income)}")
    else:
        lines.append("No income data available.")

    if balance:
        data = balance["data"]
        total_assets = _pick(data, "Total Assets", "TOTAL ASSETS", "totalAssets")
        total_equity = _pick(data, "Owner's Equity", "OWNER'S EQUITY", "ownerEquity", "equity")
        total_liabilities = _pick(data, "Liabilities", "Total Liabilities")
        total_debt = _pick(
            data,
            "Long-term borrowings",
            "Short-term borrowings",
            "totalDebt",
            "Long-term Borrowings",
        )
        if total_assets:
            lines.append(f"  Total Assets: {_fmt_vnd(total_assets)}")
        if total_equity:
            lines.append(f"  Equity: {_fmt_vnd(total_equity)}")
        if total_liabilities:
            lines.append(f"  Liabilities: {_fmt_vnd(total_liabilities)}")
        if total_debt:
            lines.append(f"  Long-term Debt: {_fmt_vnd(total_debt)}")
    else:
        lines.append("No balance sheet data available.")

    return "\n".join(lines)


def _format_valuation_prose(ticker: str, ratios: list[dict]) -> str:
    """Format valuation summary with trend."""
    if not ratios:
        return f"No ratio data for {ticker}."

    latest = ratios[0]
    lines = [f"Valuation — {ticker} (latest: {latest['report_period']}):"]
    lines.append(f"  PE: {_fmt(latest['pe'])}  PB: {_fmt(latest['pb'])}")
    lines.append(f"  ROE: {_fmt(latest['roe'], pct=True)}  ROA: {_fmt(latest['roa'], pct=True)}")
    lines.append(
        f"  Net Margin: {_fmt(latest['net_margin'], pct=True)}  Gross Margin: {_fmt(latest['gross_margin'], pct=True)}"
    )
    lines.append(
        f"  D/E: {_fmt(latest['debt_to_equity'])}  Current Ratio: {_fmt(latest['current_ratio'])}"
    )

    if len(ratios) >= 2:
        prev = ratios[1]
        trends = []
        for key, label in [("roe", "ROE"), ("net_margin", "Margin"), ("pe", "PE")]:
            curr_v, prev_v = latest.get(key), prev.get(key)
            if curr_v is not None and prev_v is not None and prev_v != 0:
                change = ((curr_v - prev_v) / abs(prev_v)) * 100
                direction = "up" if change > 0 else "down"
                trends.append(f"{label} {direction} {abs(change):.0f}%")
        if trends:
            lines.append(f"Trend vs {prev['report_period']}: {', '.join(trends)}")

    if len(ratios) >= 4:
        from shared.moat import compute_quantitative_moat_signals

        signals = compute_quantitative_moat_signals(ratios)
        tparts = []
        if signals.get("margin_trend"):
            tparts.append(f"Margin (4Q): {signals['margin_trend']}")
        if signals.get("roe_trend"):
            tparts.append(f"ROE (4Q): {signals['roe_trend']}")
        if signals.get("consistent_high_roe"):
            tparts.append("Consistent high ROE (>15% for 3Q+)")
        if signals.get("stable_margins") is False:
            tparts.append("UNSTABLE margins (>2pp variance)")
        if tparts:
            lines.append("Multi-quarter: " + " | ".join(tparts))

    return "\n".join(lines)


def _format_comparison_prose(comparison: dict[str, dict]) -> str:
    """Format multi-ticker comparison."""
    if not comparison:
        return "No ratio data for comparison."

    lines = ["Financial Comparison:"]
    header = f"{'Ticker':<8} {'PE':>7} {'PB':>7} {'ROE':>8} {'Margin':>8} {'D/E':>7}"
    lines.append(header)
    lines.append("-" * len(header))

    for ticker, r in sorted(comparison.items()):
        pe = _fmt(r.get("pe"), "") if r.get("pe") is not None else "N/A"
        pb = _fmt(r.get("pb"), "") if r.get("pb") is not None else "N/A"
        roe = _fmt(r.get("roe"), "%", pct=True) if r.get("roe") is not None else "N/A"
        margin = (
            _fmt(r.get("net_margin"), "%", pct=True) if r.get("net_margin") is not None else "N/A"
        )
        de = _fmt(r.get("debt_to_equity"), "") if r.get("debt_to_equity") is not None else "N/A"
        lines.append(f"{ticker:<8} {pe:>7} {pb:>7} {roe:>8} {margin:>8} {de:>7}")

    return "\n".join(lines)


def _fmt_vnd(amount) -> str:
    """Format VND amount in billions/millions."""
    return _format_vnd_base(amount, suffix=True)


# ── Internal async functions (return dict) ──────────────────────────────────


@allow_single_ticker_fetcher  # vnstock fundamentals API is single-symbol; no batch HTTP endpoint (Tier 4 deferred)
async def get_financial_health_async(ticker: str) -> dict:
    """Get financial health summary (income + balance sheet).

    Returns dict with structured data and prose.
    """
    try:
        income = await _get_latest_stmt(ticker, "income")
        balance = await _get_latest_stmt(ticker, "balance_sheet")
        prose = _format_health_prose(ticker, income, balance)
        return {"ticker": ticker, "income": income, "balance_sheet": balance, "prose": prose}
    except Exception as e:
        return {"error": str(e), "prose": f"Failed to get financial health for {ticker}: {e}"}


@allow_single_ticker_fetcher  # vnstock fundamentals API is single-symbol; no batch HTTP endpoint (Tier 4 deferred)
async def get_valuation_async(ticker: str, periods: int = 4) -> dict:
    """Get valuation with historical trend.

    Returns dict with ratios list and prose.
    """
    try:
        ratios = await _get_ratios(ticker, periods)
        prose = _format_valuation_prose(ticker, ratios)
        return {"ticker": ticker, "ratios": ratios, "prose": prose}
    except Exception as e:
        return {"error": str(e), "prose": f"Failed to get valuation for {ticker}: {e}"}


async def get_financial_ratios_async(ticker: str, periods: int = 4) -> list[dict]:
    """Get raw ratio data for a ticker."""
    return await _get_ratios(ticker, periods)


# ── Agent tools (return str for LLM) ───────────────────────────────────────


async def tool_get_financial_health(ticker: str) -> str:
    """Get financial health summary for a stock.

    Shows latest income statement and balance sheet highlights.

    Args:
        ticker: Stock symbol (e.g., 'FPT')
    """
    result = await get_financial_health_async(ticker)
    return result.get("prose", str(result))


async def tool_get_valuation(ticker: str) -> str:
    """Get valuation metrics with historical trend.

    Shows PE, PB, ROE, margins, EPS, and period-over-period changes.

    Args:
        ticker: Stock symbol (e.g., 'FPT')
    """
    result = await get_valuation_async(ticker)
    return result.get("prose", str(result))


async def tool_get_financial_comparison(tickers: list[str]) -> str:
    """Compare financial ratios across multiple stocks.

    Shows side-by-side PE, PB, ROE, margins, and debt/equity.

    Args:
        tickers: List of stock symbols (e.g., ['FPT', 'TCB', 'VHM'])
    """
    try:
        batch = await _get_financial_ratios_batch(tickers)
        prose = _format_comparison_prose(batch)
        return prose
    except Exception as e:
        return f"Failed to compare financials: {e}"


async def tool_get_valuation_history(ticker: str) -> str:
    """Get historical valuation percentiles and trajectory for a stock.

    Shows where current PE/PB/ROE/margin sits in its own 8-quarter history,
    including EPS and margin trend direction. Identifies CHEAP/FAIR/EXPENSIVE/EXTREME zones.

    Args:
        ticker: Stock symbol (e.g., 'FPT')
    """
    try:
        data = await compute_valuation_history(ticker, periods=8)
        return _fmt_vh_prose(data)
    except Exception as e:
        return f"Failed to get valuation history for {ticker}: {e}"


async def tool_get_earnings_quality(ticker: str) -> str:
    """Decompose earnings into core operating profit vs non-core items (4 quarters).

    Computes core_ratio (core profit / net income) and grades quality HIGH/MEDIUM/LOW.
    Low ratios signal asset revaluation, financial income, or JV gains driving results —
    common in Vietnamese real estate stocks. Always check before assigning high conviction.

    Args:
        ticker: Stock symbol (e.g., 'DIG')
    """
    try:
        data = await compute_earnings_quality(ticker, periods=4)
        return _fmt_eq_prose(data)
    except Exception as e:
        return f"Failed to get earnings quality for {ticker}: {e}"
