-- Deactivate agent configs with dangling tool references.
-- watchlist_update: replaced by watchlist_ensemble (6 dead tools)
-- positions: replaced by positions_ensemble (tool_get_holdings removed)
UPDATE agent_prompts SET is_active = FALSE
WHERE agent_key IN ('watchlist_update', 'positions')
  AND is_active = TRUE;
