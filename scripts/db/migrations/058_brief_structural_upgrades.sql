-- Migration 058: Morning brief structural upgrades
-- Adds: dual R:R targets, exit plans, volume confirmation, portfolio correlation
-- Updates synthesis and critic prompts

-- 1. Synthesis: Update TOP PICKS format for dual targets + exit plan + volume + correlation
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    E'TOP PICKS (max 5)\n- Each with Entry, Stop, Target, R:R ratio\n- All must have R:R >= 3.0',
    E'TOP PICKS (max 5)\n- Each with Entry, Stop, dual targets (conservative + aggressive), and verdict\n- Format per pick:\n  TICKER: Entry Xk | Stop Yk\n    Conservative (R1): Zk -> R:R N.N\n    Aggressive (swing_high): Wk -> R:R M.M\n    Verdict: full_size or partial_size\n    Pattern: name on N.Nx avg volume [OK/LOW conviction]\n    Leg 1: Take 50% at Zk, move stop to breakeven\n    Leg 2: Runner to Wk, trailing at 20d low\n    Time stop: Exit if flat after 10 sessions\n- All must have best R:R >= 3.0 (conservative OR aggressive)'
)
WHERE agent_key = 'synthesis';

-- 2. Synthesis: Add portfolio correlation advice to WHAT TO DO TODAY
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    E'WHAT TO DO TODAY\n- 3-6 short actions (under 10 words each)',
    E'WHAT TO DO TODAY\n- 3-6 short actions (under 10 words each)\n- If PORTFOLIO CORRELATION is HIGH, include diversification advice here'
)
WHERE agent_key = 'synthesis';

-- 3. Critic: Add dual targets and exit plan check (insert before prediction handling)
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    E'### 12. Prediction Handling (INFORMATIONAL)',
    E'### 12. Dual Targets and Exit Plan (MAJOR)\nFor each BUY in TOP PICKS:\n- Must show conservative (R1) AND aggressive (swing_high) targets when aggressive exists\n- Must include exit plan with legs (Leg 1: take profit, Leg 2: runner) and time stop\n- If only conservative target exists, single-leg exit is acceptable\n- Volume confirmation must be noted when pattern is present\n- Flag missing as [missing_exit_plan] or [missing_dual_targets]\n\n### 13. Prediction Handling (INFORMATIONAL)'
)
WHERE agent_key = 'critic';

-- 4. Critic: Fix numbering for invented picks (13 -> 14)
UPDATE agent_prompts
SET system_prompt = REPLACE(
    system_prompt,
    E'### 13. Invented Picks Detection (CRITICAL)',
    E'### 14. Invented Picks Detection (CRITICAL)'
)
WHERE agent_key = 'critic';
