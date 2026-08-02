-- Natural key for portfolio_holdings is (ticker, plan_type) — a ticker can
-- carry both a SWING slice and a LONGTERM slice. The constraint is gated on
-- an inline pre-check so a stray NULL or duplicate aborts loudly rather than
-- ignoring the condition it was meant to enforce.

BEGIN;

DO $$
DECLARE
    null_count integer;
    dup_count integer;
BEGIN
    SELECT COUNT(*) INTO null_count
    FROM portfolio_holdings WHERE plan_type IS NULL;
    IF null_count > 0 THEN
        RAISE EXCEPTION 'Aborting: % rows have plan_type IS NULL. Backfill before retrying.', null_count;
    END IF;

    SELECT COUNT(*) INTO dup_count FROM (
        SELECT ticker, plan_type FROM portfolio_holdings
        GROUP BY ticker, plan_type HAVING COUNT(*) > 1
    ) dups;
    IF dup_count > 0 THEN
        RAISE EXCEPTION 'Aborting: % (ticker, plan_type) pairs are duplicated.', dup_count;
    END IF;
END $$;

ALTER TABLE portfolio_holdings
    ADD CONSTRAINT uc_portfolio_holdings_ticker_plan_type UNIQUE (ticker, plan_type);

COMMIT;
