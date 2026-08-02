"""Compact structured formatters for context injection into agent prompts.

Each formatter returns a compact, pipe-delimited text block optimized for
token efficiency and LLM scanability. NOT prose — no articles, no filler.

Token budgets documented per function. Total injected context per agent
must stay ≤7K tokens (arXiv:2510.05381).

See: .claude/skills/agent-development/instructions.md § Context Injection
"""

import math
from datetime import datetime

from shared.formatting import format_pct as _pct
from shared.formatting import format_price_k as _price_k
from shared.formatting import format_snapshot_header, format_vnd

# Re-export ticker briefing symbols so existing callers don't break
from .context_blocks_commodity import format_commodity_block  # noqa: F401
from .context_blocks_economy import format_vn_economy_block  # noqa: F401
from .context_blocks_ticker import (  # noqa: F401
    TICKER_DATA_HEADER,
    format_ticker_briefing,
    format_ticker_briefings,
)

# ── Injection Header Constants ───────────────────────────────────────────
PORTFOLIO_HEADER = "## PORTFOLIO DATA (pre-loaded — analyze directly)"
CATALYST_HEADER = "## CATALYST PREVIEW (pre-loaded — analyze directly)"


# ── Portfolio Block ──────────────────────────────────────────────────────
# Budget: ≤500 tokens (header + ~10 positions + total line)


def format_portfolio_block(
    holdings: list[dict],
    cash_balance: float,
    deployable_cash: float,
    *,
    snapshot_at: datetime | None = None,
) -> str:
    """Compact portfolio: holdings + cash as scannable block.

    Emits one line per (ticker, plan_type) slice so dual-listed tickers
    surface both exposures. ``slice_weight_pct`` drives each line;
    ``ticker_weight_pct`` is implicit in the total.

    ``snapshot_at`` (SWI-121): freshest ``updated_at`` across portfolio_holdings;
    rendered via :func:`format_snapshot_header` (single source for the label).
    """
    header = (
        f"## PORTFOLIO | Cash: {format_vnd(cash_balance)} VND"
        f" | Deployable: {format_vnd(deployable_cash)} VND"
    )
    if not holdings:
        return f"{header}\nNo positions currently held."

    lines = [header]
    snapshot_header = format_snapshot_header(snapshot_at)
    if snapshot_header:
        lines.append(snapshot_header)
    total_weight = 0.0
    for data in holdings:
        ticker = data.get("ticker") or "?"
        shares = data.get("shares") or 0
        avg_cost = data.get("avg_cost") or 0
        # Strict pick: Now reads canonical current_price_vnd. When NULL the
        # upstream price fetch failed — render "stale" rather than masking
        # with avg_cost (which would lie about today's mark). Phase 2 §2.2.
        current_price = data.get("current_price_vnd")
        weight = data.get("slice_weight_pct") or 0
        pct_change = data.get("pct_from_entry") or 0
        plan_type = data.get("plan_type") or "SWING"
        # Strict stop precedence: catastrophic floor > trailing > breakeven.
        # Avg_cost fallback removed (Phase 2 §2.2 / FPT 86k stop bug). When
        # all three are NULL, render explicit "none active" so the LLM does
        # not paraphrase avg_cost as a protective stop.
        active_stop = (
            data.get("catastrophic_floor_vnd")
            or data.get("trailing_stop_vnd")
            or data.get("breakeven_stop")
        )

        now_repr = _price_k(current_price) if current_price else "stale"
        stop_repr = _price_k(active_stop) if active_stop else "none active"

        lines.append(
            f"{ticker} | {shares} shares | Entry: {_price_k(avg_cost)}"
            f" | Now: {now_repr} | P/L: {_pct(pct_change)}"
            f" | Weight: {weight:.1f}% | Stop: {stop_repr}"
            f" | {plan_type}"
        )
        total_weight += weight

    lines.append(f"Total: {len(holdings)} slice(s) | {total_weight:.1f}% invested")
    return "\n".join(lines)


# ── Regime Block ─────────────────────────────────────────────────────────
# Budget: ≤200 tokens


def _format_metric(
    metrics: dict, value_key: str, change_key: str, label: str, fmt: str, prefix: str = ""
) -> str | None:
    """Format a single metric with optional change %. Returns None if value is missing/NaN."""

    value = metrics.get(value_key)
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    change = metrics.get(change_key)
    result = f"{label}: {prefix}{value:{fmt}}"
    if change is not None and not (
        isinstance(change, float) and (math.isnan(change) or math.isinf(change))
    ):
        result += f" ({change:+.1f}%)"
    return result


def format_regime_block(
    market_level: dict | None,
    macro_metrics: dict | None,
    market_valuation: dict | None = None,
) -> str:
    """Compact market regime + macro as single block. Budget: ≤200 tokens."""
    regime = "UNKNOWN"
    vnindex_summary = ""
    if market_level:
        regime = market_level.get("regime") or "UNKNOWN"
        vnindex_close = market_level.get("vnindex_close")
        vnindex_rsi = market_level.get("rsi")
        parts = []
        if vnindex_close:
            parts.append(f"VN-Index: {vnindex_close:,.0f}")
        if vnindex_rsi:
            parts.append(f"RSI: {vnindex_rsi:.1f}")
        support = market_level.get("support")
        resistance = market_level.get("resistance")
        if support:
            parts.append(f"S: {support:,.0f}")
        if resistance:
            parts.append(f"R: {resistance:,.0f}")
        vnindex_summary = " | ".join(parts)

    macro_summary = ""
    extended_summary = ""
    breadth_summary = ""
    risk_regime = "UNKNOWN"
    if macro_metrics:
        risk_regime = macro_metrics.get("global_risk_regime") or "UNKNOWN"

        # Core indicators: VIX, DXY, USD/VND
        macro_parts = []
        vix_str = _format_metric(macro_metrics, "vix_value", "vix_change_pct", "VIX", ".1f")
        if vix_str:
            macro_parts.append(vix_str)
        dxy_str = _format_metric(macro_metrics, "dxy_value", "dxy_change_pct", "DXY", ".1f")
        if dxy_str:
            macro_parts.append(dxy_str)
        usd_vnd = macro_metrics.get("usd_vnd_rate")
        if usd_vnd is not None:
            macro_parts.append(f"USD/VND: {usd_vnd:,.0f}")
        macro_summary = " | ".join(macro_parts)

        extended_parts = []
        oil_str = _format_metric(macro_metrics, "oil_price", "oil_change_pct", "Oil", ".0f", "$")
        if oil_str:
            extended_parts.append(oil_str)
        copper_price = macro_metrics.get("copper_price")
        if copper_price is not None:
            extended_parts.append(f"Cu: ${copper_price:.2f}")
        us_10y = macro_metrics.get("us_10y_yield")
        if us_10y is not None:
            extended_parts.append(f"10Y: {us_10y:.2f}%")
        shanghai_str = _format_metric(
            macro_metrics, "shanghai_close", "shanghai_change_pct", "SSEC", ",.0f"
        )
        if shanghai_str:
            extended_parts.append(shanghai_str)
        extended_summary = " | ".join(extended_parts)

        breadth_parts = []
        breadth_advance = macro_metrics.get("breadth_advance")
        breadth_decline = macro_metrics.get("breadth_decline")
        breadth_ratio = macro_metrics.get("breadth_ratio")
        if breadth_advance is not None and breadth_decline is not None:
            breadth_str = f"Breadth: {breadth_advance}A/{breadth_decline}D"
            if breadth_ratio is not None:
                breadth_str += f" ({breadth_ratio:.2f})"
            breadth_parts.append(breadth_str)
        sp_str = _format_metric(macro_metrics, "sp500_close", "sp500_change_pct", "S&P", ",.0f")
        if sp_str:
            breadth_parts.append(sp_str)
        breadth_summary = " | ".join(breadth_parts)

    # Build header with confidence + data quality indicators
    confidence = market_level.get("regime_confidence") if market_level else None
    data_quality = macro_metrics.get("data_quality") if macro_metrics else None

    header = f"## MARKET REGIME: {regime}"
    if confidence is not None:
        header += f" (conf: {confidence:.0%})"
    header += f" | Risk: {risk_regime}"
    if data_quality and data_quality != "OK":
        header += f" | Macro Data: {data_quality}"
    lines = [header]
    if vnindex_summary:
        lines.append(vnindex_summary)
    if macro_summary:
        lines.append(macro_summary)
    if extended_summary:
        lines.append(extended_summary)
    if breadth_summary:
        lines.append(breadth_summary)

    # Valuation line (PE/PB with 5Y percentile)
    if market_valuation:
        valuation_parts = []
        pe_value = market_valuation.get("pe")
        pe_percentile = market_valuation.get("pe_percentile")
        if pe_value is not None:
            pe_str = f"VN-Index PE: {pe_value:.1f}"
            if pe_percentile is not None:
                pe_str += f" ({pe_percentile:.0f}th pctl 5Y)"
            valuation_parts.append(pe_str)
        pb_value = market_valuation.get("pb")
        pb_percentile = market_valuation.get("pb_percentile")
        if pb_value is not None:
            pb_str = f"PB: {pb_value:.2f}"
            if pb_percentile is not None:
                pb_str += f" ({pb_percentile:.0f}th pctl 5Y)"
            valuation_parts.append(pb_str)
        if valuation_parts:
            lines.append(" | ".join(valuation_parts))

    # Regime history if available
    if market_level and market_level.get("history"):
        history_items = market_level["history"][:5]
        history_str = ", ".join(
            f"{item.get('date', '?')}: {item.get('regime', '?')}" for item in history_items
        )
        lines.append(f"History: {history_str}")

    return "\n".join(lines)


# ── Articles Block ───────────────────────────────────────────────────────
# Budget: ≤400 tokens (headlines + 1-line summaries, NOT full text)


def format_articles_block(articles: list[dict]) -> str:
    """Compact article summaries — headlines only, no full text.

    Args:
        articles: List of article dicts with title, source, published_at, summary/short_description
    """
    if not articles:
        return "## ARTICLES\nNo articles available for today."

    lines = [f"## ARTICLES ({len(articles)} available)"]
    for article in articles[:15]:  # Cap at 15 to stay within budget
        title = (article.get("title") or "Untitled")[:80]
        source = article.get("source") or "?"
        article_id = article.get("id") or article.get("uuid") or ""
        summary = (article.get("summary") or article.get("short_description") or "")[:100]

        line = f"- [{source}] {title}"
        if summary:
            line += f" — {summary}"
        if article_id:
            line += f" (id:{article_id})"
        lines.append(line)

    if len(articles) > 15:
        lines.append(
            f"... and {len(articles) - 15} more articles available in the article cache. "
            'Use call_tools([{"name": "article.search", "args": {"queries": ["..."]}}]) '
            "to retrieve additional titles."
        )

    return "\n".join(lines)


# ── Company Profile Block ────────────────────────────────────────────────
# Budget: ≤300 tokens


def format_company_profile_block(profiles: dict[str, dict]) -> str:
    """Compact company profiles for known tickers.

    Args:
        profiles: {ticker: {sector, business_summary, macro_sensitivities, moat, key_risks}}
    """
    if not profiles:
        return ""

    lines = ["## COMPANY PROFILES"]
    for ticker, profile in profiles.items():
        sector = profile.get("sector") or "?"
        summary = (profile.get("business_summary") or "")[:80]
        moat = (profile.get("moat") or "")[:40]
        sensitivities = profile.get("macro_sensitivities") or []

        line = f"{ticker} | {sector}"
        if summary:
            line += f" | {summary}"
        if moat:
            line += f" | Moat: {moat}"
        lines.append(line)

        if sensitivities:
            sensitivity_strs = [
                f"{sensitivity.get('factor', '?')} {sensitivity.get('direction', '?')} ({sensitivity.get('magnitude', '?')})"
                for sensitivity in sensitivities[:3]
            ]
            lines.append(f"  Macro: {', '.join(sensitivity_strs)}")

    return "\n".join(lines)
