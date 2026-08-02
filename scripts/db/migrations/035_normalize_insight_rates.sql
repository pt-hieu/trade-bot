-- Normalize insight rates from 0-100 scale back to 0-1 scale

UPDATE sector_insights SET win_rate = win_rate / 100.0 WHERE win_rate > 1.0;
UPDATE ticker_insights SET recent_accuracy = recent_accuracy / 100.0 WHERE recent_accuracy > 1.0;
