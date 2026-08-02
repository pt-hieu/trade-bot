-- Migration 235: Remove tool_get_holdings + tool_get_cash from agents (now context-injected)
-- Type: Data
-- Rollback: array_append the tools back to enabled_tools
--
-- These tools fetched static per-run data (portfolio positions, cash balance) that is
-- now pre-loaded in PipelineContext and injected as compact structured text into agent
-- prompts. Agents no longer need to call these tools.

-- Position ensemble analysts (3 agents) — holdings injected via portfolio_context param
UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_holdings'),
    updated_at = NOW()
WHERE agent_key IN ('positions_technical', 'positions_value', 'positions_thesis')
  AND 'tool_get_holdings' = ANY(enabled_tools);

-- Synthesis holdings writer — portfolio data injected via context_parts
UPDATE agent_prompts
SET enabled_tools = array_remove(array_remove(enabled_tools, 'tool_get_holdings'), 'tool_get_cash'),
    updated_at = NOW()
WHERE agent_key = 'synthesis_holdings'
  AND ('tool_get_holdings' = ANY(enabled_tools) OR 'tool_get_cash' = ANY(enabled_tools));

-- Synthesis main agent — portfolio data available in pre-computed context
UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_holdings'),
    updated_at = NOW()
WHERE agent_key = 'synthesis'
  AND 'tool_get_holdings' = ANY(enabled_tools);

-- Strategy director — portfolio data injected
UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_holdings'),
    updated_at = NOW()
WHERE agent_key = 'strategy_director'
  AND 'tool_get_holdings' = ANY(enabled_tools);

-- Position strategist — portfolio data injected
UPDATE agent_prompts
SET enabled_tools = array_remove(array_remove(enabled_tools, 'tool_get_holdings'), 'tool_get_cash'),
    updated_at = NOW()
WHERE agent_key = 'position_strategist'
  AND ('tool_get_holdings' = ANY(enabled_tools) OR 'tool_get_cash' = ANY(enabled_tools));

-- Refiner — portfolio data injected
UPDATE agent_prompts
SET enabled_tools = array_remove(array_remove(enabled_tools, 'tool_get_holdings'), 'tool_get_cash'),
    updated_at = NOW()
WHERE agent_key = 'refiner'
  AND ('tool_get_holdings' = ANY(enabled_tools) OR 'tool_get_cash' = ANY(enabled_tools));

-- Trading mode — portfolio data injected
UPDATE agent_prompts
SET enabled_tools = array_remove(enabled_tools, 'tool_get_holdings'),
    updated_at = NOW()
WHERE agent_key = 'trading_mode'
  AND 'tool_get_holdings' = ANY(enabled_tools);

-- Midday agent — portfolio data injected
UPDATE agent_prompts
SET enabled_tools = array_remove(array_remove(enabled_tools, 'tool_get_holdings'), 'tool_get_cash_balance'),
    updated_at = NOW()
WHERE agent_key = 'midday'
  AND ('tool_get_holdings' = ANY(enabled_tools) OR 'tool_get_cash_balance' = ANY(enabled_tools));
