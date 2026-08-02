-- Delete test alerts (IDs 5-10) created during local testing
DELETE FROM alert_history WHERE alert_id IN (5, 6, 7, 8, 9, 10);
DELETE FROM alerts WHERE id IN (5, 6, 7, 8, 9, 10);
