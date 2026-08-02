-- Migration 159: Anti-panic-sell drawdown guard for position evaluation
-- Adds market-wide drawdown awareness to positions_technical, positions_aggregator,
-- and position_strategist to prevent simultaneous EXIT signals during broad market declines.
-- Idempotent: guarded by NOT LIKE check on unique section header.

-- positions_technical: drawdown-adjusted loss rules
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## MARKET-WIDE DRAWDOWN ADJUSTMENT\nWhen PORTFOLIO DRAWDOWN CONTEXT is present and drawdown_type is BROAD_MARKET or MODERATE_BROAD:\n1. LOSS > 7% RULE ADJUSTMENT: Do NOT auto-assign EXIT with confidence 8-10. Instead:\n   - Downgrade to EVALUATE (confidence 5-6) — the loss may be beta, not stock failure\n   - Still report the loss percentage and technical levels in your reasoning\n2. LOSS 5-7% RULE ADJUSTMENT: Do NOT assign EXIT for bearish momentum alone.\n   - During broad market drawdowns, most stocks show bearish momentum — this is not informative\n   - Downgrade to HOLD (confidence 4-5) unless the stock is breaking unique support levels\n3. STOCK-SPECIFIC SIGNAL DETECTION: You CAN still assign EXIT if the stock has UNIQUE weakness:\n   - Breaking below a multi-year support while peers hold their support\n   - Volume spike 3x+ average on the decline (distribution, not market beta)\n   - Gap down while peers are flat or green\n   If none of these stock-specific signals exist, default to EVALUATE during broad drawdowns.\n4. Confidence cap: During BROAD_MARKET drawdown, cap EXIT confidence at 6 unless stock-specific weakness confirmed.'
WHERE agent_key = 'positions_technical'
  AND system_prompt NOT LIKE '%MARKET-WIDE DRAWDOWN ADJUSTMENT%';

-- positions_aggregator: Market Drawdown Guard
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## MARKET DRAWDOWN GUARD\nWhen PORTFOLIO DRAWDOWN CONTEXT is present and drawdown_type is BROAD_MARKET or MODERATE_BROAD:\n1. AUTOMATIC EVALUATE: When Technical says EXIT purely based on loss percentage (not stock-specific breakdown):\n   - Override to EVALUATE regardless of confidence score\n   - This is NOT the Fundamental Guard — this is a separate, broader protection\n   - Reason MUST include: "Market Drawdown Guard: Loss is likely beta risk. Reevaluate on value merit."\n2. VALUE ANCHOR: Give Value analyst view 2x weight during broad drawdowns:\n   - If Value says HOLD or ADD — final action cannot be EXIT (only EVALUATE or HOLD)\n   - If Value says EXIT (fundamentals broken) — EXIT stands even during broad drawdown\n3. PANIC SELL CHECK: Before finalizing ANY EXIT during broad drawdown, verify:\n   - Is the exit signal stock-specific (broken thesis, broken fundamentals, unique technical breakdown)?\n   - Or is it purely loss-percentage-triggered during a broad decline?\n   - Only the first case justifies EXIT. The second requires EVALUATE.\n4. This guard does NOT apply when:\n   - Value analyst recommends EXIT (fundamentals genuinely deteriorating)\n   - Thesis analyst says thesis is broken\n   - Concentration limits are violated (those are deterministic overrides)'
WHERE agent_key = 'positions_aggregator'
  AND system_prompt NOT LIKE '%MARKET DRAWDOWN GUARD%';

-- position_strategist: broad drawdown protocol
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## BROAD DRAWDOWN PROTOCOL\nWhen position alerts contain "Market Drawdown Guard" in their reason:\n1. Do NOT treat EVALUATE as EXIT. EVALUATE means "human decision needed — value review required."\n2. For EVALUATE positions during broad drawdown, recommend:\n   - "VALUE REVIEW — check if fundamentals still justify holding through market-wide weakness"\n   - Include the stock distance to fair value if available from alerts\n3. Consensus EXIT is ONLY mandatory when it does NOT come from the Market Drawdown Guard.\n   - If the EXIT consensus was generated during a broad drawdown and the reason includes "Market Drawdown Guard", downgrade to "EVALUATE — consensus from broad drawdown, verify before acting."'
WHERE agent_key = 'position_strategist'
  AND system_prompt NOT LIKE '%BROAD DRAWDOWN PROTOCOL%';
