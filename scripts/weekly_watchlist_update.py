#!/usr/bin/env python3
"""
Weekly Watchlist Update Script (Agentic)

Runs Saturdays after market week ends.
Uses a PydanticAI agent with tools to:
1. Get current watchlist from database
2. Fetch technicals for all stocks
3. Search news for sentiment
4. Score stocks for add/remove decisions
5. Generate market summary and outlook

Updates Swing Watchlist in database.
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path

from agents import (
    apply_updates as agent_apply_updates,
)
from agents import (
    run_watchlist_update_ensemble,
)
from agents import (
    save_report as agent_save_report,
)
from shared.database import Database
from shared.neon import get_swing_watchlist
from shared.observability import configure_observability, span
from shared.session import init_session

# Configuration
RESEARCH_DIR = Path(__file__).parent.parent / "research"
OUTPUT_DIR = RESEARCH_DIR / "weekly-updates"


async def main():
    """Main entry point."""
    configure_observability()
    init_session("watchlist")
    today = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'=' * 60}")
    print(f"Weekly Watchlist Update (Agentic) - {today}")
    print(f"{'=' * 60}\n")

    # Check for required API key
    from shared.env import is_dry_run

    if not os.environ.get("OPENROUTER_API_KEY") and not is_dry_run():
        print("CRITICAL: OPENROUTER_API_KEY not set.")
        return

    removed_count = 0
    added_count = 0
    pinned_skips = 0

    async with Database():
        # 1. Load current watchlist from database (for reference)
        print("Step 0: Loading current watchlist from database...")
        try:
            sectors = await get_swing_watchlist()
            current_tickers = [t for tickers in sectors.values() for t in tickers]
            print(f"  Current watchlist: {len(current_tickers)} stocks")
        except Exception as e:
            print(f"  Failed to load watchlist: {e}")
            return

        # 2. Run watchlist update agent
        print("\nStep 1: Running watchlist update agent...")
        print("  Agent will:")
        print("    - Fetch technicals for all stocks")
        print("    - Search news for sentiment")
        print("    - Check upcoming catalysts")
        print("    - Score stocks for add/remove")
        print()

        with span("weekly_watchlist_update"):
            result = await run_watchlist_update_ensemble()

        if "error" in result:
            print(f"  Error: {result['error']}")
            return

        print(f"  Market summary: {(result.get('market_summary') or 'N/A')[:100]}...")
        print(f"  Hot sectors: {result.get('hot_sectors', [])}")
        print(f"  Cold sectors: {result.get('cold_sectors', [])}")
        print(f"  Removals: {len(result.get('removals', []))}")
        print(f"  Additions: {len(result.get('additions', []))}")

        # 3. Apply updates to database
        print("\nStep 2: Applying updates to database...")
        # SWI-304: feed pre-removal guardrail with rally / holdings / HIGH-positive catalysts.
        guard_technicals = result.get("_technicals", {}) or {}
        guard_holdings: set[str] = set()
        guard_catalyst_tickers: set[str] = set()
        try:
            from shared.neon.portfolio import get_portfolio_holdings

            holdings_rows = await get_portfolio_holdings()
            guard_holdings = {(row.get("ticker") or "").upper() for row in holdings_rows}
        except Exception as exc:
            print(f"  Pre-removal guard: holdings lookup failed: {exc}")
        try:
            from shared.neon.catalyst_filters import filter_high_positive_catalyst_tickers
            from shared.neon.catalyst_summaries import get_active_catalysts

            guard_catalyst_tickers = set(
                filter_high_positive_catalyst_tickers(await get_active_catalysts()).keys()
            )
        except Exception as exc:
            print(f"  Pre-removal guard: catalyst lookup failed: {exc}")

        removed_count, added_count, pinned_skips = await agent_apply_updates(
            result,
            technicals=guard_technicals,
            holdings=guard_holdings,
            catalyst_tickers=guard_catalyst_tickers,
        )
        print(f"  Removed: {removed_count} stocks")
        print(f"  Added: {added_count} stocks")
        if pinned_skips:
            print(f"  Pinned (skipped removal): {len(pinned_skips)}")
            for skip in pinned_skips:
                print(f"    - {skip}")

        # 4. Sync DB RSI with live technicals used by this pipeline run
        technicals = result.pop("_technicals", {})
        if technicals:
            from shared.neon import update_swing_rsi_batch

            rsi_data = {}
            for ticker, technical_data in technicals.items():
                if isinstance(technical_data, dict) and technical_data.get("rsi") is not None:
                    rsi_data[ticker] = float(technical_data["rsi"])
            if rsi_data:
                updated = await update_swing_rsi_batch(rsi_data)
                print(f"  RSI synced to DB for {updated} tickers")

    # 5. Save report
    print("\nStep 3: Saving report...")
    output_file = agent_save_report(result, today)
    print(f"  Report saved to {output_file}")

    # 6. Summary
    print(f"\n{'=' * 60}")
    print("Weekly Update Complete!")
    print(f"  Removed: {removed_count} stocks")
    print(f"  Added: {added_count} stocks")
    print(f"  New total: {len(current_tickers) - removed_count + added_count}")
    print(f"{'=' * 60}\n")

    # Print report summary for Telegram
    print("\n--- REPORT SUMMARY ---")
    print(f"Market: {result.get('market_summary', 'N/A')}")
    print(f"Outlook: {result.get('weekly_outlook', 'N/A')}")


if __name__ == "__main__":
    asyncio.run(main())
