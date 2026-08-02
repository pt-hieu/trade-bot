-- Resolve duplicate FTSE catalysts. Keep ftse_upgrade as canonical (28 tickers, 3 phases).
-- The duplicates were auto-created by the catalyst discovery agent from news articles.

UPDATE catalysts
SET status = 'resolved',
    outcome_detail = 'Duplicate — merged into ftse_upgrade',
    updated_at = NOW()
WHERE catalyst_key IN ('ftse_russell_upgrade_of_vietna', 'ftse_russell_mid-term_review_f')
  AND status NOT IN ('resolved', 'expired');
