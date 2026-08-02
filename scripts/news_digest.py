#!/usr/bin/env python3
"""
Holiday Analysis — runs global-scope phases when VN market is closed.

The market stops on holidays, but the world keeps moving. This script:
1. Fetches macro metrics (DXY, VIX, USD/VND, oil)
2. Fetches commodity prices (oil, gold, steel)
3. Fetches VN economic snapshot (GDP, CPI, exchange rate)
4. Detects geopolitical phase changes
5. Persists all data to DB (continuity when trading resumes)
6. Generates a macro-focused holiday brief

Replaces the old simple news_digest that just formatted articles.
"""

import asyncio
from datetime import date

from shared.config import get_research_dir, get_scan_date
from shared.database import Database, close_db
from shared.observability import configure_observability
from shared.session import init_session
from shared.telegram import send_telegram_error

TODAY = get_scan_date()
RESEARCH_DIR = get_research_dir()


def _format_holiday_brief(
    scan_date: str,
    macro_metrics: dict | None,
    commodity_prices: dict | None,
    vn_economy: dict | None,
    geopolitical_context: str,
    articles: list[dict],
) -> str:
    """Format a macro-focused holiday brief."""
    lines = [
        f"# Morning Brief — {scan_date} (Holiday)",
        "",
        "---",
        "",
    ]

    lines.append("## GLOBAL MACRO")
    lines.append("")
    if macro_metrics and not macro_metrics.get("error"):
        risk_regime = macro_metrics.get("global_risk_regime") or "CAUTIOUS"
        lines.append(f"**Risk Regime: {risk_regime}**")
        lines.append("")

        dxy = macro_metrics.get("dxy_value")
        dxy_change = macro_metrics.get("dxy_change_pct")
        vix = macro_metrics.get("vix_value")
        vix_change = macro_metrics.get("vix_change_pct")
        usd_vnd = macro_metrics.get("usd_vnd_rate")

        if dxy:
            change_str = f" ({dxy_change:+.2f}%)" if dxy_change else ""
            lines.append(f"- DXY: {dxy:.2f}{change_str} — {macro_metrics.get('dxy_signal', '')}")
        if vix:
            change_str = f" ({vix_change:+.2f}%)" if vix_change else ""
            lines.append(f"- VIX: {vix:.2f}{change_str} — {macro_metrics.get('vix_signal', '')}")
        if usd_vnd:
            lines.append(f"- USD/VND: {usd_vnd:,.0f} — {macro_metrics.get('usd_vnd_signal', '')}")

        oil = macro_metrics.get("oil_price")
        if oil:
            oil_change = macro_metrics.get("oil_change_pct")
            change_str = f" ({oil_change:+.2f}%)" if oil_change else ""
            lines.append(f"- Oil: ${oil:.2f}{change_str} — {macro_metrics.get('oil_signal', '')}")

        interpretation = macro_metrics.get("interpretation")
        if interpretation:
            lines.append("")
            lines.append(interpretation)
    else:
        lines.append("Macro data unavailable.")
    lines.append("")

    if commodity_prices:
        lines.append("## COMMODITIES")
        lines.append("")
        for commodity_key, commodity_data in commodity_prices.items():
            if not isinstance(commodity_data, dict):
                continue
            price = commodity_data.get("price")
            unit = commodity_data.get("unit", "")
            change_5d = commodity_data.get("change_5d_pct")
            change_str = f" ({change_5d:+.1f}% 5d)" if change_5d else ""
            if price:
                lines.append(f"- {commodity_key}: {price:,.2f} {unit}{change_str}")
        lines.append("")

    if vn_economy:
        lines.append("## VN ECONOMY")
        lines.append("")
        for indicator_key, indicator_value in vn_economy.items():
            if isinstance(indicator_value, dict):
                value = indicator_value.get("value")
                if value is not None:
                    lines.append(f"- {indicator_key}: {value}")
            elif indicator_value is not None:
                lines.append(f"- {indicator_key}: {indicator_value}")
        lines.append("")

    if geopolitical_context:
        lines.append("## GEOPOLITICAL")
        lines.append("")
        lines.append(geopolitical_context)
        lines.append("")

    lines.append("## NEWS THAT MATTERS")
    lines.append("")
    if articles:
        for article in articles[:20]:
            source = article.get("source", "")
            title = article.get("title", "").strip()
            summary = article.get("summary", "").strip()
            if title:
                lines.append(f"**[{source}] {title}**")
                if summary:
                    lines.append(f"  {summary}")
                lines.append("")
    else:
        lines.append("No articles found for today.")
        lines.append("")

    lines.append("---")
    lines.append("*Market closed for holiday. Full analysis resumes when trading opens.*")
    return "\n".join(lines)


async def _run_holiday_analysis(scan_date: date) -> None:
    """Run global-scope analysis phases for holidays.

    Uses the same Phase 1 infrastructure as the main pipeline
    (run_phase1_parallel + post_process_phase1) with skip_market_agents=True.
    """
    from pipeline import post_process_phase1, run_phase1_parallel
    from shared.neon.articles import list_articles_range

    phase1 = await run_phase1_parallel(scan_date, skip_market_agents=True)
    _market_regime, _global_risk_regime, geopolitical_context = await post_process_phase1(
        scan_date, phase1
    )

    articles = await list_articles_range(scan_date, scan_date)
    print(f"  Articles: {len(articles)} found")

    brief = _format_holiday_brief(
        str(scan_date),
        phase1.macro_metrics,
        phase1.commodity_prices,
        phase1.vn_economy,
        geopolitical_context,
        articles,
    )

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    brief_path = RESEARCH_DIR / "morning-brief.md"
    brief_path.write_text(brief, encoding="utf-8")

    print(f"\n{'=' * 60}")
    print("Holiday Analysis Complete!")
    print(f"  Brief: {brief_path}")
    print(f"  Length: {len(brief):,} characters")
    print(f"{'=' * 60}\n")


async def _main_async() -> None:
    """Async entry point."""
    scan_date = date.fromisoformat(TODAY)

    try:
        async with Database():
            from shared.trading_config import init_trading_config

            await init_trading_config()
            await _run_holiday_analysis(scan_date)
    except Exception as e:
        error_msg = f"Holiday analysis failed: {e}"
        print(f"CRITICAL: {error_msg}")
        send_telegram_error(error_msg)
        raise
    finally:
        from shared.vnstock_client import close_client

        await close_client()
        await close_db()


def main() -> None:
    """Sync entry point."""
    configure_observability()
    init_session("news_digest")
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
