-- Fix double-converted prices: divide by 1000 to get correct VND integers.
-- insert_morning_recommendations() was applying * 1000 to prices already in VND.
-- Only affects rows where prices are implausibly high (> 1M VND = clearly double-converted).
-- Vietnamese stock prices range 1,000-500,000 VND. Anything above 1M is certainly wrong.

UPDATE daily_recommendations
SET entry_price_vnd = entry_price_vnd / 1000
WHERE entry_price_vnd > 1000000;

UPDATE daily_recommendations
SET stop_price_vnd = stop_price_vnd / 1000
WHERE stop_price_vnd > 1000000;

UPDATE daily_recommendations
SET target_price_vnd = target_price_vnd / 1000
WHERE target_price_vnd > 1000000;
