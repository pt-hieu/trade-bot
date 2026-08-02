#!/usr/bin/env python3
"""
Migration 135: Harden the trade/portfolio sync trigger.

Context:
  An earlier migration reclassified a holding's plan_type in portfolio_holdings
  but left the matching rows in trades_calculated on the old value. The trigger
  matched on ticker AND plan_type, so closing those trades matched nothing and
  the portfolio was never decremented — the position lingered after full exit.

  Matching on ticker alone makes the CLOSE branch immune to any future
  reclassification.

  The original migration also deleted one stale row. That one-time data
  correction is omitted here; it applied to a specific production row and does
  nothing on a fresh database.

Run:
    SWINGY_ENV=production uv run python scripts/db/migrations/135_fix_portfolio_and_trigger.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.database import Database

TRIGGER_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION sync_portfolio_on_trade()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' AND NEW.status = 'OPEN' THEN
        INSERT INTO portfolio_holdings (ticker, holding_type, shares, avg_cost_vnd, plan_type)
        VALUES (NEW.ticker, 'Stock', NEW.shares, NEW.entry_price_vnd, COALESCE(NEW.plan_type, 'SWING'))
        ON CONFLICT (ticker, plan_type) DO UPDATE SET
            avg_cost_vnd = (
                portfolio_holdings.avg_cost_vnd * portfolio_holdings.shares
                + NEW.entry_price_vnd * NEW.shares
            ) / (portfolio_holdings.shares + NEW.shares),
            shares = portfolio_holdings.shares + NEW.shares,
            updated_at = NOW();

    ELSIF TG_OP = 'UPDATE' AND OLD.status = 'OPEN' AND NEW.status = 'CLOSED' THEN
        -- Match by ticker only (not plan_type) to handle reclassified positions
        UPDATE portfolio_holdings
        SET shares = shares - NEW.shares,
            updated_at = NOW()
        WHERE ticker = NEW.ticker;

        DELETE FROM portfolio_holdings
        WHERE ticker = NEW.ticker
          AND shares <= 0;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


async def main():
    # Update trigger — needs owner URL (DDL: CREATE OR REPLACE FUNCTION)
    owner_url = os.getenv("DATABASE_OWNER_URL")
    if not owner_url:
        print("❌ DATABASE_OWNER_URL not set — cannot apply DDL")
        print("   Set it to the owner connection string from .env and re-run")
        sys.exit(1)

    db_owner = Database(url=owner_url)
    await db_owner.connect()
    await db_owner.execute(TRIGGER_FUNCTION_SQL)
    print("✅ Updated sync_portfolio_on_trade(): CLOSE branch now ticker-only")
    await db_owner.disconnect()

    print("\nMigration 135 complete.")


if __name__ == "__main__":
    asyncio.run(main())
