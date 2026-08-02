-- Migration 231: Recompute daily_records.win_rate after data quality fixes
--
-- Re-runs same logic as migration 227 to pick up corrections from:
-- 228 (bogus SKIP/AVOID wins), 229 (eod_price_vnd units), 230 (won backfill)

UPDATE daily_records dr
SET win_rate = sub.corrected_win_rate
FROM (
    SELECT
        record_id,
        CASE
            WHEN COUNT(*) FILTER (WHERE won IS NOT NULL) = 0 THEN 0
            ELSE ROUND(
                COUNT(*) FILTER (WHERE won = true)::numeric
                / COUNT(*) FILTER (WHERE won IS NOT NULL)
                * 100, 2
            )
        END AS corrected_win_rate
    FROM daily_evaluations
    GROUP BY record_id
) sub
WHERE dr.id = sub.record_id;
