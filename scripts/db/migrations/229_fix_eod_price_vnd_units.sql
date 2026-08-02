-- Migration 229: Fix eod_price_vnd unit corruption pre-2026-03-11
--
-- Before 2026-03-11, insert path did int(eod_price * 1000) where eod_price was
-- already k-VND → stored as full VND (e.g., 79,500,000 instead of 79,500).
-- Guard: > 1000000 prevents double-correction (no VN stock trades above 1M k-VND).

UPDATE daily_evaluations de
SET eod_price_vnd = eod_price_vnd / 1000
FROM daily_records dr
WHERE dr.id = de.record_id
  AND dr.record_date < '2026-03-11'
  AND de.eod_price_vnd > 1000000;
