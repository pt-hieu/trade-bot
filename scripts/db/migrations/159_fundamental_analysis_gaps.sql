-- Migration 159: Close fundamental analysis gaps in agent prompting
--
-- Changes:
-- 1. Add screen_min_core_ratio to trading_config
-- 2. Enable new tools for sector, longterm_review, positions_value agents
-- 3. Append forward earnings + valuation guard + earnings quality prompt sections

-- ── 1. trading_config: add screen_min_core_ratio ─────────────────────────────

ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS screen_min_core_ratio NUMERIC(5,2) DEFAULT 0.40;

UPDATE trading_config SET screen_min_core_ratio = 0.40 WHERE screen_min_core_ratio IS NULL;

-- ── 2. Enable new tools ───────────────────────────────────────────────────────

-- sector: add tool_get_valuation_history for valuation guard before BUY signals
UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_valuation_history')
WHERE agent_key = 'sector'
  AND NOT ('tool_get_valuation_history' = ANY(enabled_tools));

-- Also add flow/insider/relative_strength tools that DB shows are missing from local JSON
UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_flow')
WHERE agent_key = 'sector'
  AND NOT ('tool_get_flow' = ANY(enabled_tools));

UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_insider')
WHERE agent_key = 'sector'
  AND NOT ('tool_get_insider' = ANY(enabled_tools));

UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_relative_strength')
WHERE agent_key = 'sector'
  AND NOT ('tool_get_relative_strength' = ANY(enabled_tools));

-- longterm_review: add valuation history + earnings quality tools
UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_valuation_history')
WHERE agent_key = 'longterm_review'
  AND NOT ('tool_get_valuation_history' = ANY(enabled_tools));

UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_earnings_quality')
WHERE agent_key = 'longterm_review'
  AND NOT ('tool_get_earnings_quality' = ANY(enabled_tools));

-- positions_value: add valuation history + earnings quality tools
UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_valuation_history')
WHERE agent_key = 'positions_value'
  AND NOT ('tool_get_valuation_history' = ANY(enabled_tools));

UPDATE agent_prompts
SET enabled_tools = array_append(enabled_tools, 'tool_get_earnings_quality')
WHERE agent_key = 'positions_value'
  AND NOT ('tool_get_earnings_quality' = ANY(enabled_tools));

-- ── 3. Prompt additions ───────────────────────────────────────────────────────

-- SECTOR AGENT: valuation guard + stock quality awareness
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## VALUATION GUARD (tool_get_valuation_history)\nBefore assigning BUY to any ticker:\n1. Call tool_get_valuation_history(ticker) to check where PE sits in its 8Q history\n2. If PE zone is EXPENSIVE (>75th pctl): require ALL 4 confirmations aligned (RSI + pattern + volume + sector)\n3. If PE zone is EXTREME_HIGH (>90th pctl): signal WATCH regardless of technicals\n   — "Valuation at 8Q extreme, wait for pullback"\n4. If PE zone is CHEAP (<25th pctl) + fundamentals sound: boost confidence to HIGH\n\nFPT pattern: PE at 8Q high (30x on AI hype) → guidance 17% vs 25% expected → -30% correction.\nBuying technically oversold stocks that are also valuation-extended = compounding risk.\n\n## STOCK QUALITY AWARENESS\nVietnamese market has three stock categories:\n- GROWTH: Strong ROE, consistent margins, core earnings from operations\n- VALUE_TRAP: Low PE but weak ROE or declining fundamentals (cheap for a reason)\n- SPECULATIVE: Earnings driven by asset revaluation or one-off items (DIG/CEO pattern)\n\nIf screening output includes stock_category = VALUE_TRAP or SPECULATIVE: default signal is AVOID\nunless you have specific evidence the category classification is wrong.\nBDS (real estate) stocks: always verify if ROE is from land revaluation vs actual sales revenue.'
WHERE agent_key = 'sector';

-- LONGTERM_REVIEW AGENT: forward earnings assessment + earnings quality check
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## FORWARD EARNINGS ASSESSMENT (MANDATORY per stock)\nPrice LEADS earnings by 1-2 quarters. By the time great financials are published, the move may be over.\nFor each stock:\n1. Use tool_get_valuation_history(ticker): identify EPS and margin trajectory over 4-8Q\n2. Project next 2-4Q direction: ACCELERATING / STEADY / DECELERATING / DECLINING\n   - ACCELERATING: growth rate increasing quarter-over-quarter\n   - DECELERATING: still positive but growth rate slowing (most dangerous zone)\n   - DECLINING: negative growth or turning negative\n3. Cross-reference valuation zone with earnings trajectory:\n   - PE EXTREME_HIGH + DECELERATING earnings → EXIT/reduce conviction (DCM/FPT pattern)\n   - PE CHEAP + ACCELERATING earnings → highest conviction BUY signal\n   - PE FAIR + STEADY earnings → hold, wait for better entry\n4. Include forward_earnings_view in research output: 1-2 sentences on projected direction\n\nDCM example: Reported 10x earnings growth in Q1 2022 → stock peaked → buying at peak reported earnings led to -20% loss 3 months later when margins reverted. The signal to buy was BEFORE the good numbers, not after.\n\n## EARNINGS QUALITY CHECK (MANDATORY per stock)\nFor each stock, call tool_get_earnings_quality(ticker):\n- Core ratio > 80%: HIGH quality — earnings from core operations, reliable\n- Core ratio 50-80%: MEDIUM — investigate what comprises the non-core portion\n- Core ratio < 50%: LOW — reduce conviction by 1 level. Flag explicitly: "Earnings quality concern: XX% from non-core sources"\n- Core ratio declining trend: WARNING — increasing reliance on non-recurring items\n\nVietnamese BDS stocks: asset revaluation and land bank writeups are common. A company with ROE 25% driven by revaluation of unsold inventory is NOT a high-ROE business — it is a LOW quality earnings report.\nAlways verify: is the ROE driven by operational cash generation or accounting entries?'
WHERE agent_key = 'longterm_review';

-- POSITIONS_VALUE AGENT: historical valuation context + earnings quality adjustment
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## HISTORICAL VALUATION CONTEXT (tool_get_valuation_history)\nFor each position, call tool_get_valuation_history(ticker):\n- PE EXTREME_HIGH (>90th pctl of 8Q) + EPS DECELERATING → TRIM (confidence 8)\n  "Stock at historical valuation peak with slowing growth — reduce exposure"\n- PE EXTREME_LOW (<10th pctl of 8Q) + EPS IMPROVING + quality HIGH → ADD (confidence 9)\n  "Rare combination: historical cheapness + improving fundamentals"\n- PE FAIR + margins STABLE → no valuation-driven action needed\n\n## EARNINGS QUALITY ADJUSTMENT (tool_get_earnings_quality)\nFor each position, call tool_get_earnings_quality(ticker):\n- Core ratio < 50%: reduce confidence by 2 points (earnings may not be sustainable)\n  Flag in reasoning: "Core earnings only XX% of net income — ROE/PE metrics may be misleading"\n- Core ratio declining (DECLINING trend): reduce confidence by 1 point\n- Banks: interest income is core — standard non-bank thresholds do not apply\n\nKey principle: A stock with PE 12 and ROE 20% looks attractive until you discover 70% of income is from asset revaluation. Adjust all fundamental assessments for earnings quality before making hold/trim/exit calls.'
WHERE agent_key = 'positions_value';

-- ── Verify ────────────────────────────────────────────────────────────────────
SELECT agent_key, enabled_tools
FROM agent_prompts
WHERE agent_key IN ('sector', 'longterm_review', 'positions_value')
ORDER BY agent_key;
