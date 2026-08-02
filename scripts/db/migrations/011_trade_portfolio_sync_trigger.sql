-- =====================================================
-- MIGRATION 011: Auto-sync trades → portfolio_holdings
-- =====================================================

-- Step 1: Clean up any duplicate (ticker, plan_type) before adding constraint
-- Keep the row with most shares (or most recent if tied)
DELETE FROM portfolio_holdings a
USING portfolio_holdings b
WHERE a.ticker = b.ticker
  AND a.plan_type = b.plan_type
  AND a.id > b.id;

-- Step 2: Add unique constraint for upsert
ALTER TABLE portfolio_holdings
ADD CONSTRAINT uq_portfolio_ticker_plan UNIQUE (ticker, plan_type);

-- Step 3: Create sync function
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
        UPDATE portfolio_holdings
        SET shares = shares - NEW.shares,
            updated_at = NOW()
        WHERE ticker = NEW.ticker
          AND plan_type = COALESCE(NEW.plan_type, 'SWING');

        DELETE FROM portfolio_holdings
        WHERE ticker = NEW.ticker
          AND plan_type = COALESCE(NEW.plan_type, 'SWING')
          AND shares <= 0;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Step 4: Create trigger
DROP TRIGGER IF EXISTS trade_portfolio_sync ON trades_calculated;
CREATE TRIGGER trade_portfolio_sync
AFTER INSERT OR UPDATE ON trades_calculated
FOR EACH ROW EXECUTE FUNCTION sync_portfolio_on_trade();
