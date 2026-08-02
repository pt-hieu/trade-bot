-- Migration 070: Fix 3 morning brief logical contradictions
--
-- Fix 1: entry_strategist KEY RISK rules — no "execution paralysis" when max_entries=0
-- Fix 2: synthesis SWING TRIM + LONG-TERM dedup rules — no ticker in two sections
-- Fix 3: critic check #15 — cross-section dedup + key_risk_contradiction detection

-- entry_strategist: add KEY RISK rules
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## KEY RISK Rules\n- If ENTRY CRITERIA shows max_entries = 0: KEY RISK MUST focus on POSITION MANAGEMENT risks\n  (stop discipline, premature trimming, emotional holding, concentration).\n  Do NOT warn about ''missed entries'', ''failure to act'', or ''execution paralysis''\n  -- new entries are explicitly prohibited today. A no-entry day IS the correct action.\n- If max_entries > 0: KEY RISK should focus on the biggest risk to new entry quality\n  (e.g., false breakout, illiquidity, regime deterioration).'
WHERE agent_key = 'entry_strategist'
  AND system_prompt NOT LIKE '%KEY RISK Rules%';

-- synthesis: add SWING TRIM + LONG-TERM coexistence rules
UPDATE agent_prompts
SET system_prompt = replace(
    system_prompt,
    E'## GLOBAL TICKER DEDUP RULE\nEach ticker in EXACTLY ONE section. Priority:\n1. MY HOLDINGS (highest)\n2. TOP PICKS\n3. LONG-TERM PORTFOLIO\n4. SKIP THESE\n5. WHAT TO DO TODAY (reference only)',
    E'## GLOBAL TICKER DEDUP RULE\nEach ticker in EXACTLY ONE section. Priority:\n1. MY HOLDINGS (highest)\n2. TOP PICKS\n3. LONG-TERM PORTFOLIO\n4. SKIP THESE\n5. WHAT TO DO TODAY (reference only)\n\n## SWING TRIM + LONG-TERM THESIS\nWhen a SWING position is being TRIMMED on a stock that also appears on the long-term watchlist:\n- In MY HOLDINGS: note the TRIM action (e.g., ''TRIM 50% at resistance'')\n- Do NOT add that ticker to LONG-TERM PORTFOLIO -- it is already covered in MY HOLDINGS\n- The SWING trim action and the long-term thesis are separate concerns handled in MY HOLDINGS\n\nIf the pre-computed long-term analysis shows a [DEDUP] note, respect it:\n- Those tickers are already in MY HOLDINGS and MUST NOT appear in LONG-TERM PORTFOLIO'
)
WHERE agent_key = 'synthesis'
  AND system_prompt NOT LIKE '%SWING TRIM + LONG-TERM THESIS%';

-- critic: add check #15 cross-section dedup
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n### 15. Cross-Section Ticker Dedup (CRITICAL)\nNo ticker may appear as a recommendation in more than one section:\n- If a ticker is in MY HOLDINGS AND also has a BUY/STRONG BUY recommendation in LONG-TERM PORTFOLIO:\n  Flag as [dedup_violation]: "TICKER appears in both MY HOLDINGS and LONG-TERM PORTFOLIO."\n- If ENTRY CRITERIA shows max_entries = 0 AND KEY RISK warns about ''execution paralysis'' or ''missed entries'':\n  Flag as [key_risk_contradiction]: "KEY RISK warns about missed entries but max_entries = 0 prohibits entries."\n  Fix: KEY RISK should focus on position management risks when no entries are allowed.\n- Severity: critical for dedup_violation, major for key_risk_contradiction.'
WHERE agent_key = 'critic'
  AND system_prompt NOT LIKE '%Cross-Section Ticker Dedup%';
