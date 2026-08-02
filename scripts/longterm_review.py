#!/usr/bin/env python3
"""Long-Term Watchlist Review Orchestration.

Monthly automation:
  1. Deterministic pass: calculate entry zones, score conviction, compute review flags
  2. Candidate screening: find VN30 tickers that pass financial thresholds
  3. LLM pass: refresh research, adjust entry zones/conviction, recommend additions/removals
  4. Apply results to DB
  5. Telegram summary

Schedule: 1st of each month (financials fetched live from vnstock API).
Usage: uv run python scripts/longterm_review.py
"""

import asyncio
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from longterm.apply_results import apply_llm_results, screen_vn30_candidates
from longterm.deterministic import run_deterministic_pass
from shared.database import Database
from shared.env import load_env
from shared.neon.longterm import get_longterm_watchlist_full
from shared.neon.portfolio import get_sector_allocations
from shared.observability import configure_observability
from shared.session import init_session
from shared.telegram import send_telegram
from shared.trading_config import get_trading_config

configure_observability()
init_session("longterm")

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_sector_summary(stocks: list[dict], allocations: list[dict]) -> str:
    """Build sector summary string from watchlist + allocation data."""
    sector_counts: dict[str, list[str]] = {}
    for s in stocks:
        sector = s.get("sector") or "Unknown"
        sector_counts.setdefault(sector, []).append(s["ticker"])

    sector_lines = [
        f"  {sector}: {', '.join(tickers)} ({len(tickers)} stocks)"
        for sector, tickers in sorted(sector_counts.items())
    ]
    alloc_lines = [
        f"  {a['sector_name'].replace('_', ' ').title()}: {a['target_pct']}%" for a in allocations
    ]
    return (
        "Target sector allocations:\n"
        + "\n".join(alloc_lines)
        + "\n\nCurrent longterm watchlist by sector:\n"
        + "\n".join(sector_lines)
    )


def _build_telegram_summary(
    changes: dict,
    llm_result,
    candidates: list[dict],
) -> str:
    lines = ["\U0001f4ca *Monthly Long-Term Review Complete*\n"]

    lines.append(f"Research updated: {len(changes['research_updated'])} stocks")

    if changes["entry_adjusted"]:
        lines.append(f"\n*Entry zone adjustments ({len(changes['entry_adjusted'])}):*")
        for c in changes["entry_adjusted"]:
            lines.append(f"  \u2022 {c}")

    if changes["conviction_adjusted"]:
        lines.append(f"\n*Conviction adjustments ({len(changes['conviction_adjusted'])}):*")
        for c in changes["conviction_adjusted"]:
            lines.append(f"  \u2022 {c}")

    if changes["added"]:
        lines.append(f"\n*\u2795 New additions ({len(changes['added'])}):*")
        for c in changes["added"]:
            lines.append(f"  \u2022 {c}")

    if changes["deactivated"]:
        lines.append(f"\n*\u2796 Deactivated ({len(changes['deactivated'])}):*")
        for c in changes["deactivated"]:
            lines.append(f"  \u2022 {c}")

    if llm_result.market_outlook:
        lines.append(f"\n*Market Outlook:*\n{llm_result.market_outlook}")

    if candidates:
        top = candidates[:3]
        top_str = ", ".join(f"{c['ticker']} (ROE={c['roe']:.0f}%, PE={c['pe']:.1f})" for c in top)
        lines.append(f"\n*Top VN30 screened (not added):* {top_str}")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────


async def _main_async():
    print("[longterm_review] Starting monthly review...")

    async with Database():
        # 1. Load active watchlist
        stocks = await get_longterm_watchlist_full()
        print(f"  {len(stocks)} active stocks: {[s['ticker'] for s in stocks]}")

        existing_tickers = {s["ticker"] for s in stocks}

        # 2. Deterministic pass
        print("\n[longterm_review] Running deterministic pass...")
        deterministic, det_summary = await run_deterministic_pass(stocks)
        print(det_summary)

        # 3. Candidate screening + sector allocations (concurrent)
        print("\n[longterm_review] Screening VN30 candidates...")
        candidates, allocations = await asyncio.gather(
            screen_vn30_candidates(existing_tickers),
            get_sector_allocations(),
        )
        print(f"  {len(candidates)} candidates pass thresholds")
        for c in candidates[:5]:
            print(f"    {c['ticker']}: score={c['score']}, ROE={c['roe']:.1f}%, PE={c['pe']:.1f}")

        # 4. LLM pass
        print("\n[longterm_review] Running LLM review agent...")
        from agents.longterm_review import run_longterm_review

        sector_summary = _build_sector_summary(stocks, allocations)
        stock_sectors = {s["ticker"]: s.get("sector") or "Unknown" for s in stocks}

        llm_result = await run_longterm_review(
            watchlist_tickers=[s["ticker"] for s in stocks],
            candidates=candidates,
            deterministic_summary=det_summary,
            sector_summary=sector_summary,
            stock_sectors=stock_sectors,
        )
        print(f"  LLM reviewed {len(llm_result.stocks)} stocks")
        print(f"  Additions recommended: {len(llm_result.additions)}")
        print(f"  Removals flagged: {len(llm_result.removals)}")

        # Sanity check: flag additions with unrealistically low entry zones
        candidate_prices = {c["ticker"]: c.get("current_price") for c in candidates}
        for addition in llm_result.additions:
            price = candidate_prices.get(addition.ticker.upper())
            if price and addition.suggested_entry_zone_vnd < price * 0.60:
                print(
                    f"  [WARN] {addition.ticker}: entry zone {addition.suggested_entry_zone_vnd:,} VND "
                    f"is <60% of current price {price:,} VND — may be unrealistic"
                )

        # 4b. Removal validation guard — reject removals where ROE > 12%
        valid_removals = []
        for removal in llm_result.removals:
            det_data = deterministic.get(removal.ticker, {})
            roe = det_data.get("roe")
            if roe and roe > 12:
                print(
                    f"  [REJECTED] Removal of {removal.ticker} — ROE {roe:.1f}% > 12%, "
                    f"no thesis break. Reason given: {removal.reason[:80]}"
                )
            else:
                valid_removals.append(removal)
        llm_result.removals = valid_removals

        # 4c. Concentration guard — block additions in over-concentrated sectors
        trading_config = get_trading_config()
        max_sector_pct = trading_config.sector_concentration_med_pct / 100
        sector_counts = Counter(stock_sectors.get(s["ticker"], "Unknown") for s in stocks)
        total_stocks = len(stocks)
        valid_additions = []
        for addition in llm_result.additions:
            sector = addition.sector
            current_pct = sector_counts.get(sector, 0) / total_stocks if total_stocks else 0
            if current_pct >= max_sector_pct:
                print(
                    f"  [REJECTED] Addition of {addition.ticker} — sector {sector} "
                    f"at {current_pct:.0%} >= {max_sector_pct:.0%} concentration limit"
                )
            else:
                valid_additions.append(addition)
        llm_result.additions = valid_additions

        # 5. Apply results
        print("\n[longterm_review] Applying results to DB...")
        changes = await apply_llm_results(llm_result, deterministic)

        # 6. Telegram summary
        summary = _build_telegram_summary(changes, llm_result, candidates)
        print("\n" + summary)
        try:
            send_telegram(summary)
        except Exception:
            logger.warning("Telegram summary failed", exc_info=True)

    print("\n[longterm_review] Done.")


def main():
    load_env()
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
