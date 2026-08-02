-- Migration 269: Backfill mislabeled belief statuses
-- 155 beliefs where LLM claimed REAFFIRMED/UPDATED but direction actually changed.
-- Also caps conviction to 0.6 for newly-REVERSED beliefs (reversal penalty).

UPDATE agent_beliefs ab
SET belief_status = 'REVERSED',
    conviction = LEAST(ab.conviction, 0.6)
FROM agent_beliefs prior
WHERE ab.prior_belief_id = prior.id
  AND ab.belief_status IN ('REAFFIRMED', 'UPDATED')
  AND ab.direction != prior.direction;
