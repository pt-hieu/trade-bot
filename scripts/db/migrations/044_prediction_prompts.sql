-- 044: Add prediction guidance to synthesis/critic/refiner prompts
-- Predictions are early-stage (~40% accuracy) — agents should treat with skepticism

-- 1. Synthesis: Add prediction usage guidance (experimental, grain of salt)
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n## PREDICTION SIGNALS (Experimental — ~40% Accuracy)\nPre-computed picks may include ML prediction data (LightGBM + LLM + Quant ensemble).\nThis is EARLY-STAGE — treat as supplementary signal, not primary driver.\n\nHow to use:\n- Predictions are ONE input among many — technicals and regime remain primary\n- High confidence (>70%) + 3/3 sources agree → mention as supporting signal\n- Low confidence (<55%) or source disagreement → note uncertainty in pick\n- Prediction conflicts with technical setup → flag conflict, defer to technicals\n- NEVER override bad R:R, weak support, or regime rules based on prediction alone\n\nIn TOP PICKS notes (5-10 words max):\n- Agreement: "ML signal supports"\n- Conflict: "ML signal disagrees — deferring to technicals"\n- Low confidence: "ML signal inconclusive"',
    updated_at = NOW()
WHERE agent_key = 'synthesis' AND is_active = TRUE;

-- 2. Critic: Add prediction validation (informational, non-blocking)
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n### 12. Prediction Handling (INFORMATIONAL)\nIf TOP PICKS mentions predictions, check for:\n- Over-reliance: Pick recommended primarily due to high prediction confidence → flag as [prediction_override]\n- Missing conflict note: Prediction disagrees with technical setup but not flagged (informational, not blocking)\nThese are INFORMATIONAL only — do not block or escalate severity for prediction issues.',
    updated_at = NOW()
WHERE agent_key = 'critic' AND is_active = TRUE;

-- 3. Refiner: Add prediction over-reliance fix rules
UPDATE agent_prompts
SET system_prompt = system_prompt || E'\n\n### Fixing Prediction Over-Reliance\nIf critic flags [prediction_override]:\n- Re-evaluate the pick using ONLY technical setup (R:R, support, RSI, pattern)\n- If technical setup is weak (R:R < 3.5, no clear support) → REMOVE the pick\n- If technical setup is strong → keep the pick but rewrite note to emphasize technicals\n- Format: "Strong bounce setup at support (ML signal supports)"\n\nIf prediction conflicts with technicals but not noted:\n- Add brief conflict note: "ML signal disagrees — deferring to technicals"',
    updated_at = NOW()
WHERE agent_key = 'refiner' AND is_active = TRUE;
