"""Context formatters + zone/heat pre-computation + previous-report loader."""

from __future__ import annotations

import json
from pathlib import Path

from ..watchlist_update import CRYPTO_EXPOSED, SECTOR_MAP


def _load_previous_report() -> dict | None:
    """Load most recent weekly report from research/weekly-updates/."""
    report_dir = Path(__file__).parent.parent.parent.parent / "research" / "weekly-updates"
    if not report_dir.exists():
        return None
    reports = sorted(report_dir.glob("*.json"), reverse=True)
    if not reports:
        return None
    try:
        with open(reports[0]) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [watchlist_ensemble] Could not load previous report {reports[0]}: {e}")
        return None


def _format_articles(articles: list[dict]) -> str:
    """Format DB articles (with summaries) into context block."""
    if not articles:
        return "No articles available for this period."
    lines = ["## NEWS ARTICLES (last 7 days)"]
    for a in articles:
        summary = (a.get("summary") or "").strip()
        if not summary:
            continue
        title = (a.get("title") or a.get("query") or "Untitled").strip()
        source = (a.get("source") or "").strip()
        lines.append(f"\n### {title} [{source}]")
        lines.append(summary)
    return "\n".join(lines)


def _compute_zone_tag(rsi: float | None) -> str:
    """Pre-compute RSI zone tag — deterministic, no LLM."""
    if rsi is None:
        return "UNKNOWN"
    if rsi > 70:
        return "OVERBOUGHT"
    if rsi <= 30:
        return "OVERSOLD"
    if 30 < rsi <= 50:
        return "BUY_ZONE"
    return "NEUTRAL"


def _compute_sector_heat(technicals: dict) -> dict[str, str]:
    """Pre-compute sector heat from avg RSI per sector — deterministic."""
    sector_rsi: dict[str, list[float]] = {}
    for ticker, data in technicals.items():
        if isinstance(data, dict) and "error" not in data:
            rsi = data.get("rsi")
            sector = SECTOR_MAP.get(ticker, "Other")
            if rsi is not None:
                sector_rsi.setdefault(sector, []).append(float(rsi))
    heat: dict[str, str] = {}
    for sector, values in sector_rsi.items():
        avg = sum(values) / len(values)
        if avg > 55:
            heat[sector] = "HOT"
        elif avg < 40:
            heat[sector] = "COLD"
        else:
            heat[sector] = "NEUTRAL"
    return heat


def _format_technicals(technicals: dict, tickers: list[str], sector_heat: dict[str, str]) -> str:
    """Format technicals as tagged context text — all computation done in Python."""
    if not technicals or "error" in technicals:
        return "Technicals unavailable."
    lines = ["## TECHNICALS (pre-computed, do not recalculate)"]
    lines.append(
        "Format: TICKER | RSI | Zone | MACD | MA20 flag | MA50 flag | Supertrend | ADX | Sector | Sector Heat | Crypto"
    )
    lines.append("")
    for ticker in tickers:
        data = technicals.get(ticker)
        if not data or isinstance(data, dict) and "error" in data:
            lines.append(f"{ticker} | INSUFFICIENT DATA")
            continue

        rsi = data.get("rsi")
        zone = _compute_zone_tag(rsi)
        rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"

        macd_data = data.get("macd") or {}
        macd_val = macd_data.get("MACD") if isinstance(macd_data, dict) else None
        macd_flag = "MACD:POSITIVE" if (macd_val or 0) > 0 else "MACD:NEGATIVE"

        close = data.get("close") or data.get("price")
        sma20 = data.get("sma20")
        sma50 = data.get("sma50")
        ma20_flag = (
            "MA20:ABOVE"
            if close and sma20 and close > sma20
            else ("MA20:BELOW" if close and sma20 else "MA20:N/A")
        )
        ma50_flag = (
            "MA50:ABOVE"
            if close and sma50 and close > sma50
            else ("MA50:BELOW" if close and sma50 else "MA50:N/A")
        )

        st_data = data.get("supertrend") or {}
        st_dir = (st_data.get("direction") or "N/A") if isinstance(st_data, dict) else "N/A"

        adx_data = data.get("adx") or {}
        adx_val = adx_data.get("adx") if isinstance(adx_data, dict) else None
        adx_str = f"ADX:{adx_val:.0f}" if adx_val is not None else "ADX:N/A"

        sector = SECTOR_MAP.get(ticker, "Other")
        heat = sector_heat.get(sector, "NEUTRAL")
        crypto = CRYPTO_EXPOSED.get(ticker, "NONE")

        lines.append(
            f"{ticker} | RSI:{rsi_str} | {zone} | {macd_flag} | {ma20_flag} | {ma50_flag} | ST:{st_dir} | {adx_str} | {sector} | {heat} | CRYPTO:{crypto}"
        )
    return "\n".join(lines)


def _format_catalysts(catalysts: list[dict], capital_events: list[dict]) -> str:
    """Format catalysts and capital events as context text."""
    lines = ["## UPCOMING CATALYSTS & CAPITAL EVENTS"]
    if catalysts:
        lines.append("\n### Regulatory Catalysts")
        for c in catalysts[:10]:
            affected = ", ".join(c.get("affected_tickers") or []) or "all"
            lines.append(
                f"- {c.get('event', 'N/A')} | Expected: {c.get('expected', 'N/A')} | Affects: {affected} | Confidence: {c.get('confidence', 'N/A')}"
            )
    if capital_events:
        lines.append("\n### Capital Events")
        for e in capital_events[:10]:
            lines.append(
                f"- {e.get('ticker', 'N/A')}: {e.get('event_type', 'N/A')} on {e.get('ex_date', 'N/A')}"
            )
    if not catalysts and not capital_events:
        lines.append("None scheduled.")
    return "\n".join(lines)


def _format_watchlist_status(
    current_watchlist: set[str], tickers: list[str], pinned_tickers: set[str] | None = None
) -> str:
    """Show which tickers are on/off the watchlist so evaluators know what to score."""
    on_wl = [t for t in tickers if t in current_watchlist]
    off_wl = [t for t in tickers if t not in current_watchlist]
    pinned_in_scope = [t for t in tickers if t in (pinned_tickers or set())]
    lines = ["## CURRENT WATCHLIST STATUS"]
    lines.append(
        f"ON watchlist (score for REMOVAL if setup degraded): {', '.join(on_wl) if on_wl else 'None'}"
    )
    lines.append(
        f"OFF watchlist (score for ADDITION if setup qualifies): {', '.join(off_wl) if off_wl else 'None'}"
    )
    if pinned_in_scope:
        lines.append(f"PINNED (cannot be removed by pipeline): {', '.join(pinned_in_scope)}")
    return "\n".join(lines)


def _format_portfolio_context(portfolio: list[dict]) -> str:
    """Format current holdings so coordinator can skip already-held stocks."""
    if not portfolio:
        return "No current holdings."
    lines = ["## CURRENT PORTFOLIO HOLDINGS (do NOT propose adding these to watchlist)"]
    for slice_row in portfolio:
        ticker = slice_row.get("ticker") or "?"
        plan = slice_row.get("plan_type") or "?"
        weight = slice_row.get("slice_weight_pct") or 0
        lines.append(f"- {ticker}: {plan}, weight={weight:.1f}%")
    return "\n".join(lines)


def _format_previous_decisions(prev_report: dict | None, tickers: list[str]) -> str:
    """Extract prior week add/remove for anti-churn context."""
    if not prev_report:
        return "No previous report available."
    added = [r["ticker"] for r in prev_report.get("additions", []) if r["ticker"] in tickers]
    removed = [r["ticker"] for r in prev_report.get("removals", []) if r["ticker"] in tickers]
    lines = ["## PREVIOUS WEEK DECISIONS (anti-churn reference)"]
    lines.append(f"Added last week: {', '.join(added) if added else 'None'}")
    lines.append(f"Removed last week: {', '.join(removed) if removed else 'None'}")
    lines.append(
        "ANTI-CHURN: Do not flip these decisions without material change (RSI shift >15, Supertrend reversal, or new catalyst)."
    )
    return "\n".join(lines)
