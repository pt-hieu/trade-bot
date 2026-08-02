-- Migration 227: Recompute daily_records.win_rate excluding MISSED/EXCLUDED
--
-- Bug: MISSED tickers (won IS NULL) were counted in denominator, deflating win_rate.
-- Example: 2026-03-24 reported 42.86% (3/7) instead of 100% (3/3) because
-- 4 WATCH/MISSED tickers inflated the denominator.
--
-- Fix: recompute from daily_evaluations.won, excluding NULL won rows.

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
