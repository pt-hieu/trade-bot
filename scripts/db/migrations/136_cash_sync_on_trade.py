#!/usr/bin/env python3
"""
Migration 136: Auto-adjust cash balance when trades are opened or closed.

Context:
  Cash is stored as a special row in portfolio_holdings (ticker='CASH',
  holding_type='Cash', balance in avg_cost_vnd). Previously, cash was
  manually updated by the user after every trade. This migration updates the
  sync trigger to auto-adjust cash:
    - OPEN trade inserted: decrease cash by buy_total_vnd
    - Trade CLOSED (OPEN→CLOSED update): increase cash by sell_total_vnd

  Partial closes are handled in the web app route directly (they bypass the
  trigger's UPDATE path by inserting a new CLOSED row).

Run:
    SWINGY_ENV=production DATABASE_OWNER_URL=<owner_url> uv run python scripts/db/migrations/136_cash_sync_on_trade.py
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
        -- Upsert stock position
        INSERT INTO portfolio_holdings (ticker, holding_type, shares, avg_cost_vnd, plan_type)
        VALUES (NEW.ticker, 'Stock', NEW.shares, NEW.entry_price_vnd, COALESCE(NEW.plan_type, 'SWING'))
        ON CONFLICT (ticker, plan_type) DO UPDATE SET
            avg_cost_vnd = (
                portfolio_holdings.avg_cost_vnd * portfolio_holdings.shares
                + NEW.entry_price_vnd * NEW.shares
            ) / (portfolio_holdings.shares + NEW.shares),
            shares = portfolio_holdings.shares + NEW.shares,
            updated_at = NOW();

        -- Decrease cash by buy cost
        UPDATE portfolio_holdings
        SET avg_cost_vnd = avg_cost_vnd - NEW.buy_total_vnd,
            updated_at = NOW()
        WHERE ticker = 'CASH' AND holding_type = 'Cash';

    ELSIF TG_OP = 'UPDATE' AND OLD.status = 'OPEN' AND NEW.status = 'CLOSED' THEN
        -- Match by ticker only (not plan_type) to handle reclassified positions
        UPDATE portfolio_holdings
        SET shares = shares - NEW.shares,
            updated_at = NOW()
        WHERE ticker = NEW.ticker;

        DELETE FROM portfolio_holdings
        WHERE ticker = NEW.ticker
          AND shares <= 0;

        -- Increase cash by sell proceeds
        UPDATE portfolio_holdings
        SET avg_cost_vnd = avg_cost_vnd + NEW.sell_total_vnd,
            updated_at = NOW()
        WHERE ticker = 'CASH' AND holding_type = 'Cash';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


async def main():
    owner_url = os.getenv("DATABASE_OWNER_URL")
    if not owner_url:
        print("❌ DATABASE_OWNER_URL not set — cannot apply DDL")
        print("   Set it to the owner connection string from .env and re-run")
        sys.exit(1)

    db = Database(url=owner_url)
    await db.connect()
    await db.execute(TRIGGER_FUNCTION_SQL)
    print("✅ Updated sync_portfolio_on_trade(): cash auto-adjusted on open/close")
    await db.disconnect()

    print("\nMigration 136 complete.")


if __name__ == "__main__":
    asyncio.run(main())
