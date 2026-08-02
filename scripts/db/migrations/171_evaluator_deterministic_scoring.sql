-- Migration 171: Deterministic scoring for watchlist evaluator
--
-- Kimi K2.5 consistently fails to sum +N/-N points (8 mismatches in one run).
-- Python model_validator computes the correct total from reason tags.
-- Remove arithmetic pressure so LLM focuses on qualitative rubric application.

UPDATE agent_prompts
SET system_prompt = replace(
    replace(
        replace(
            system_prompt,
            'SCORING RULES (MUST FOLLOW EXACTLY)',
            'SCORING RULES'
        ),
        'Sum the points. The score MUST EXACTLY match the sum.',
        'Score is auto-computed from your point tags -- do not calculate the total yourself.'
    ),
    'Example: reasons=["RSI 35, zone BUY_ZONE (+30)", "Banking HOT sector (+15)", "Liquidity ok (+10)"] -> score=55',
    'Focus on correctly identifying which rubric items apply, not arithmetic.'
)
WHERE agent_key = 'watchlist_sector_evaluator';
