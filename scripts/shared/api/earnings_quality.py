"""Earnings quality analysis — core vs non-core income decomposition.

VCI income statements include line items for financial income, other income,
JV profit share — the main non-recurring sources in Vietnamese stocks.

All computations are deterministic Python (rule 9 — no LLM math).
"""

from .fundamentals import get_financial_statements

# Tickers classified as banks — different income structure (interest income IS core)
BANK_TICKERS = frozenset(
    {
        "TCB",
        "VCB",
        "BID",
        "ACB",
        "MBB",
        "VPB",
        "HDB",
        "STB",
        "CTG",
        "TPB",
        "SHB",
        "VIB",
        "OCB",
        "KLB",
        "SSB",
        "LPB",
        "MSB",
        "EIB",
        "ABB",
        "NAB",
    }
)


def _pick(data: dict, *keys) -> float | None:
    """First non-None, non-zero value from multiple possible field names."""
    for k in keys:
        val = data.get(k)
        if val is not None and val != 0:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
    return None


def _decompose_income(data: dict, is_bank: bool) -> dict:
    """Extract core vs non-core income from a VCI income statement record.

    VCI field names observed across company types:
    - Revenue: 'Net sales', 'Net Revenue', 'Revenue', 'Sales', 'Interest income' (banks)
    - Operating profit: 'Operating Profit', 'Profit from operating activities'
    - Gross profit: 'Gross Profit'
    - Non-core: 'Financial income', 'Other income', 'Share of profit of associates'
                'Gain on disposal of investments', 'Gains from revaluation'
    - Net income: 'Net profit/(loss) after tax', 'Attributable to parent company'
    """
    if is_bank:
        # Banks: interest income and trading income are core
        revenue = _pick(data, "Interest income", "Net interest income", "Net sales", "Revenue")
        core_profit = _pick(data, "Operating Profit", "Profit from operating activities")
        non_core = _pick(
            data, "Other income", "Gains from revaluation", "Gain on disposal of investments"
        )
    else:
        revenue = _pick(data, "Net sales", "Net Revenue", "Revenue", "Sales")
        core_profit = _pick(
            data,
            "Operating Profit",
            "Profit from operating activities",
            "Gross Profit",  # fallback if no operating profit line
        )
        non_core = (
            (_pick(data, "Financial income") or 0)
            + (_pick(data, "Other income") or 0)
            + (
                _pick(data, "Share of profit of associates", "Share of profit of joint ventures")
                or 0
            )
            + (_pick(data, "Gain on disposal of investments", "Gains from revaluation") or 0)
        )
        non_core = non_core if non_core != 0 else None

    net_income = _pick(
        data,
        "Net profit/(loss) after tax",
        "Attributable to parent company",
        "Net income",
        "net_income",
    )

    return {
        "revenue": revenue,
        "core_profit": core_profit,
        "non_core": non_core,
        "net_income": net_income,
    }


def _core_ratio(core_profit, net_income) -> float | None:
    """core_profit / net_income. None if inputs invalid."""
    if core_profit is None or net_income is None or net_income == 0:
        return None
    ratio = core_profit / net_income
    # Clamp to [-1, 2] for edge cases (loss periods, negative non-core)
    return max(-1.0, min(2.0, ratio))


def _quality_grade(ratio: float) -> str:
    if ratio >= 0.8:
        return "HIGH"
    if ratio >= 0.5:
        return "MEDIUM"
    return "LOW"


def _ratio_trend(ratios: list[float]) -> str:
    """IMPROVING | STABLE | DECLINING from newest-first list."""
    if len(ratios) < 3:
        return "STABLE"
    newest_avg = sum(ratios[:2]) / 2
    oldest_avg = sum(ratios[-2:]) / 2
    delta = newest_avg - oldest_avg
    if delta > 0.1:
        return "IMPROVING"
    if delta < -0.1:
        return "DECLINING"
    return "STABLE"


async def compute_earnings_quality(ticker: str, periods: int = 4) -> dict:
    """Decompose earnings into core vs non-core income over N quarters.

    Returns core_ratio (core operating profit / total net income), quality grade,
    and 4Q trend. Low core_ratio means earnings driven by non-recurring items.

    Args:
        ticker: Stock symbol.
        periods: Number of quarters (default 4).
    """
    ticker = ticker.upper()
    is_bank = ticker in BANK_TICKERS
    statements = await get_financial_statements(ticker, "income", periods=periods)

    if not statements:
        return {"ticker": ticker, "error": "no income statement data"}

    quarterly: list[dict] = []
    core_ratios: list[float] = []

    for stmt in statements:
        data = stmt.get("data", {})
        period = stmt.get("report_period", "?")
        decomp = _decompose_income(data, is_bank)
        ratio = _core_ratio(decomp["core_profit"], decomp["net_income"])

        entry: dict = {
            "period": period,
            "revenue": decomp["revenue"],
            "core_profit": decomp["core_profit"],
            "non_core": decomp["non_core"],
            "net_income": decomp["net_income"],
            "core_ratio": round(ratio, 3) if ratio is not None else None,
        }
        quarterly.append(entry)
        if ratio is not None:
            core_ratios.append(ratio)

    latest = quarterly[0] if quarterly else {}
    latest_ratio = latest.get("core_ratio")

    return {
        "ticker": ticker,
        "is_bank": is_bank,
        "periods": len(quarterly),
        "latest": latest,
        "core_ratios": core_ratios,
        "core_ratio_trend": _ratio_trend(core_ratios) if core_ratios else "STABLE",
        "quality_grade": _quality_grade(latest_ratio) if latest_ratio is not None else "UNKNOWN",
        "quarterly": quarterly,
    }


def format_earnings_quality_prose(data: dict) -> str:
    """Format compute_earnings_quality output as agent-readable prose."""
    if data.get("error"):
        return f"No earnings quality data for {data.get('ticker', '?')}: {data['error']}"

    ticker = data.get("ticker", "?")
    grade = data.get("quality_grade", "UNKNOWN")
    trend = data.get("core_ratio_trend", "STABLE")
    latest = data.get("latest", {})
    is_bank = data.get("is_bank", False)
    periods = data.get("periods", "?")

    lines = [f"Earnings Quality — {ticker} ({periods}Q):"]
    if is_bank:
        lines.append("  [Bank] Interest/trading income counted as core.")

    period = latest.get("period", "?")
    lines.append(f"  Latest ({period}):")

    def _fmt_b(v) -> str:
        if v is None:
            return "N/A"
        return f"{v / 1e9:.1f}B"

    revenue = latest.get("revenue")
    core = latest.get("core_profit")
    non_core = latest.get("non_core")
    net = latest.get("net_income")
    ratio = latest.get("core_ratio")

    if revenue:
        lines.append(f"    Revenue: {_fmt_b(revenue)}")
    if core:
        lines.append(f"    Core Operating Profit: {_fmt_b(core)}")
    if non_core and abs(non_core) > 1e8:
        lines.append(f"    Non-core Income: {_fmt_b(non_core)}")
    if net:
        lines.append(f"    Net Income: {_fmt_b(net)}")

    if ratio is not None:
        lines.append(f"  Core Ratio: {ratio:.0%} [{grade}] | Trend (4Q): {trend}")
    else:
        lines.append("  Core Ratio: N/A (insufficient data)")

    # Show 4Q core ratio series
    quarterly = data.get("quarterly", [])
    if len(quarterly) >= 2:
        series = " → ".join(
            f"{q['core_ratio']:.0%}" if q.get("core_ratio") is not None else "N/A"
            for q in quarterly
        )
        lines.append(f"  4Q series: {series}")

    # Warning for low/declining quality
    if ratio is not None and ratio < 0.5:
        pct = (1 - ratio) * 100
        lines.append(
            f"  WARNING: {pct:.0f}% of earnings from non-core sources. "
            "May not be recurring — verify core business growth independently."
        )
    if trend == "DECLINING" and ratio is not None and ratio < 0.7:
        lines.append(
            "  WARNING: Core earnings ratio declining — increasing reliance on non-recurring items."
        )

    return "\n".join(lines)
