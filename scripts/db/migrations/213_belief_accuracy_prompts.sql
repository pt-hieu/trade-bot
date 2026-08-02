-- Migration 213: Add accuracy track record context to aggregator prompts
-- Type: Data (agent_prompts update, default DATABASE_URL works)
--
-- Purpose: Aggregator agents now see their track record (Brier score, direction accuracy)
-- injected via tool_get_belief_accuracy. This migration adds explicit instructions
-- to USE the accuracy data for self-calibration, creating a feedback loop.
--
-- Usage: SWINGY_ENV=production uv run python scripts/db/run_migration.py scripts/db/migrations/213_belief_accuracy_prompts.sql

-- sector_aggregator: add accuracy-aware aggregation instructions
UPDATE agent_prompts
SET system_prompt = system_prompt || '

## ACCURACY-WEIGHTED BELIEF AGGREGATION

Before finalizing beliefs, call tool_get_belief_accuracy(perspective="all") to see all agents'' track records.

Use this data to weight your aggregation:
- Agents with Brier < 0.35: high weight (better than base rates)
- Agents with Brier 0.35-0.50: normal weight
- Agents with Brier > 0.50: low weight (worse than base rates — anchor their beliefs toward 35/40/25)

When an agent with strong track record (Brier < 0.35) disagrees with majority:
- Give their view extra weight in your disagreement_note
- Do NOT dismiss it just because they are outnumbered

A deterministic aggregation layer also runs after you. Your job is qualitative reconciliation
and narrative — the math layer handles the probability weighting.
'
WHERE agent_key = 'sector_aggregator'
  AND system_prompt NOT LIKE '%ACCURACY-WEIGHTED BELIEF AGGREGATION%';

-- positions_aggregator: same accuracy-aware instructions
UPDATE agent_prompts
SET system_prompt = system_prompt || '

## ACCURACY-WEIGHTED BELIEF AGGREGATION

Before finalizing beliefs, call tool_get_belief_accuracy(perspective="all") to see all agents'' track records.

Use this data to weight your aggregation:
- Agents with Brier < 0.35: high weight (better than base rates)
- Agents with Brier 0.35-0.50: normal weight
- Agents with Brier > 0.50: low weight (worse than base rates — anchor toward 35/40/25)

When an agent with strong track record disagrees with majority:
- Give their view extra weight in your disagreement_note
- The best predictor on the desk gets more say, not the loudest

A deterministic aggregation layer also runs after you. Your job is qualitative reconciliation.
'
WHERE agent_key = 'positions_aggregator'
  AND system_prompt NOT LIKE '%ACCURACY-WEIGHTED BELIEF AGGREGATION%';
