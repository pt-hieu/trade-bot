-- Migration 288: Fix synthesis_holdings prompt coherence issues
-- 1. HDB contradiction: SKIP + ACCUMULATE for same ticker
-- 2. Stop price = entry price for underwater longterm positions

UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## LONG-TERM PORTFOLIO DEDUP RULE\nIf a ticker appears in LONG-TERM PORTFOLIO as ACCUMULATE, do NOT list it in SKIP THESE.\nNote any short-term risk in the ACCUMULATE entry instead.\n\n## UNDERWATER POSITION STOP LEVELS\nFor LONGTERM HOLD positions where current price is below entry price:\n- Show "Catastrophic Floor: X" as the stop, NOT the entry/breakeven price\n- The catastrophic floor is the level where the long-term thesis is invalidated\n- Entry price is already shown in the P/L line — repeating it as stop is meaningless\n',
    updated_at = NOW()
WHERE agent_key = 'synthesis_holdings';
