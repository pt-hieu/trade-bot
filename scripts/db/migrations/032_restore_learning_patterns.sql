-- Restore learning patterns wiped by LLM returning empty results
-- Root cause: update_learnings() unconditionally replaced patterns with LLM output
-- Fix: retrospective.py now guards against empty pattern replacement

DELETE FROM learning_patterns;

INSERT INTO learning_patterns (pattern_type, pattern_description, win_rate, loss_rate, sample_size, actionable_rule, avoid_rule) VALUES
('winning', 'AVOID on weak-momentum and downtrend stocks', 0.84, 0.16, 32, 'Avoid stocks with downtrend/overbought conditions or lack of momentum confirmation', 'Do not enter stocks showing weak momentum, flat price action, or downtrend technicals'),
('winning', 'AVOID under elevated macro risk regime', 0.84, 0.16, 15, 'During ELEVATED or CAUTIOUS global macro regimes, avoid new entries entirely', 'Never enter new positions when DXY/VIX signals elevated risk'),
('winning', 'SKIP when macro regime prohibits entries', 1.0, 0.0, 2, 'SKIP all new entry setups when macro regime is not favorable', 'Do not force entries during regime uncertainty'),
('winning', 'WAIT for momentum confirmation', 0.57, 0.43, 7, 'Wait for clear momentum confirmation before entering positions', 'Entering without confirmed momentum leads to losses'),
('losing', 'BUY entry at hammer/support patterns', 0.0, 1.0, 2, 'DO NOT BUY based solely on hammer patterns at support - wait for confirmation', 'Hammer patterns alone are insufficient entry signals; require volume and momentum confirmation'),
('losing', 'HOLD on losing positions without stops', 0.0, 1.0, 17, 'Exit positions showing -5% or greater drawdowns rather than holding indefinitely', 'Holding positions in drawdown hoping for recovery leads to larger losses'),
('losing', 'ADD to positions without momentum', 0.0, 1.0, 1, 'Do not ADD to positions without strong momentum and trend confirmation', 'Adding to positions showing bearish engulfing patterns or at support without bounce confirmation'),
('losing', 'EXIT recommendations not executed', 0.0, 1.0, 5, 'EXIT recommendations must be executed promptly when triggered', 'Delayed exit execution led to larger realized losses'),
('losing', 'WAIT on strong momentum stocks', 0.57, 0.43, 1, 'When strong momentum confirms breakout, act quickly rather than waiting', 'Waiting for a perfect entry on a confirmed breakout misses strong moves');

-- Restore sector insights
DELETE FROM sector_insights;

INSERT INTO sector_insights (sector_id, bias, win_rate) VALUES
(1, 'neutral', 0.45),   -- Banking
(2, 'neutral', 0.50),   -- Real Estate
(6, 'neutral', 0.50),   -- Infrastructure
(5, 'cold', 0.35),      -- Consumer
(3, 'cold', 0.40),      -- Technology
(4, 'cold', 0.33);      -- State-Owned

-- Restore ticker insights
DELETE FROM ticker_insights;

INSERT INTO ticker_insights (ticker, recent_accuracy) VALUES
('AAA', 0.30),
('BBB', 0.40),
('CCC', 0.20),
('DDD', 0.70),
('EEE', 0.80),
('FFF', 0.75),
('GGG', 0.70),
('HHH', 0.60);
