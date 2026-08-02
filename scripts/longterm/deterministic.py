"""Deterministic pass for long-term watchlist review.

Fetches financial ratios concurrently, scores conviction, calculates entry zones,
and persists results to DB. No LLM calls — pure arithmetic.
"""

import asyncio

from shared.api.fundamentals import get_financial_ratios
from shared.longterm_calculations import (
    calculate_entry_zone,
    compute_review_flags,
    score_conviction,
)
from shared.moat import compute_quantitative_moat_signals
from shared.neon.longterm import (
    update_longterm_conviction,
    update_longterm_entry_zone,
    update_longterm_ratios,
    update_longterm_review_flags,
)


async def _fetch_ratios_for_ticker(ticker: str) -> tuple[str, list[dict]]:
    """Fetch 8Q ratios for a single ticker. Returns (ticker, ratios)."""
    ratios = await get_financial_ratios(ticker, periods=8)
    return ticker, ratios


async def _persist_ticker_results(
    ticker: str,
    entry_vnd: int | None,
    entry_method: str,
    conviction: str,
    score: int,
    flags: list[str],
    latest_ratios: dict,
) -> None:
    """Write deterministic results for one ticker to DB."""
    await update_longterm_ratios(
        ticker,
        pe=latest_ratios.get("pe"),
        roe=latest_ratios.get("roe"),
        div_yield=None,
    )
    if entry_vnd:
        await update_longterm_entry_zone(ticker, entry_vnd, entry_method)
    await update_longterm_conviction(ticker, conviction, score, "calculated")
    await update_longterm_review_flags(ticker, flags)


async def run_deterministic_pass(
    stocks: list[dict],
) -> tuple[dict[str, dict], str]:
    """Run deterministic calculations for all active watchlist stocks.

    Fetches all ratios concurrently (single batch), then processes each ticker.

    Returns:
        (results_by_ticker, summary_string)
        results_by_ticker: {ticker: {entry_zone_vnd, conviction, score, flags, method_entry, method_conv}}
    """
    # Fetch all ratios concurrently instead of N sequential calls
    tickers = [s["ticker"] for s in stocks]
    fetch_results = await asyncio.gather(
        *[_fetch_ratios_for_ticker(t) for t in tickers],
        return_exceptions=True,
    )
    ratios_by_ticker: dict[str, list[dict]] = {}
    for result in fetch_results:
        if isinstance(result, BaseException):
            continue
        ticker, ratios = result
        ratios_by_ticker[ticker] = ratios

    results = {}
    summary_lines = ["=== Deterministic Calculations ==="]
    persist_tasks = []

    for stock in stocks:
        ticker = stock["ticker"]
        current_entry = stock.get("entry_zone_vnd")
        current_conviction = stock.get("conviction") or "Medium"
        ratios = ratios_by_ticker.get(ticker, [])

        if not ratios:
            results[ticker] = {
                "entry_zone_vnd": current_entry,
                "conviction": current_conviction,
                "score": 30,
                "flags": ["NO_FINANCIAL_DATA"],
                "method_entry": "manual_fallback",
                "method_conv": "manual_fallback",
            }
            summary_lines.append(f"{ticker}: NO_FINANCIAL_DATA — keeping manual values")
            continue

        latest = ratios[0]
        entry_vnd, entry_method = calculate_entry_zone(ratios, None, current_entry)
        conviction, score = score_conviction(ticker, ratios)
        flags = compute_review_flags(ticker, ratios, conviction, current_conviction)

        if entry_vnd and current_entry and entry_vnd > 0:
            diff_pct = abs(entry_vnd - current_entry) / current_entry * 100
            if diff_pct > 30:
                flags.append("ENTRY_ZONE_DIVERGENCE_30PCT")

        persist_tasks.append(
            _persist_ticker_results(
                ticker, entry_vnd, entry_method, conviction, score, flags, latest
            )
        )

        results[ticker] = {
            "ticker": ticker,
            "entry_zone_vnd": entry_vnd or current_entry,
            "conviction": conviction,
            "score": score,
            "flags": flags,
            "method_entry": entry_method,
            "method_conv": "calculated",
            "roe": latest.get("roe"),
        }

        moat_signals = compute_quantitative_moat_signals(ratios)
        flag_str = ", ".join(flags) if flags else "none"
        entry_k = f"{entry_vnd // 1000}k" if entry_vnd else "N/A"
        moat_str = (
            (
                f"roe_trend={moat_signals.get('roe_trend')}, "
                f"margin_trend={moat_signals.get('margin_trend')}, "
                f"consistent_high_roe={moat_signals.get('consistent_high_roe')}, "
                f"stable_margins={moat_signals.get('stable_margins')}"
            )
            if moat_signals
            else ""
        )
        summary_lines.append(
            f"{ticker}: entry={entry_k} ({entry_method}), conviction={conviction} (score={score}), "
            f"flags=[{flag_str}]" + (f", moat_signals=[{moat_str}]" if moat_str else "")
        )

    # Persist all DB writes concurrently
    if persist_tasks:
        await asyncio.gather(*persist_tasks)

    return results, "\n".join(summary_lines)
