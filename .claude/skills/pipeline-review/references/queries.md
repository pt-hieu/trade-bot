# Pipeline Review — SQL & Data Fetch Queries

## Logfire Queries

### Trace Discovery (Step 2a)

```sql
SELECT trace_id, span_name, start_timestamp, end_timestamp, duration
FROM records
WHERE span_name IN ('morning_brief_generation', 'midday_check', 'retrospective_generation', 'weekly_watchlist_update')
  AND service_name = 'swingy'
ORDER BY start_timestamp DESC
LIMIT 10
```

**Age parameter:** Calculate minutes from now to start of target_date (00:00 UTC).
- Today → `age = 1440`
- Yesterday → `age = 2880`
- N days ago → `age = (N+1) * 1440`

### All Spans for a Trace (Step 2b)

```sql
-- Query ONE trace at a time to avoid hitting the 100-row limit
SELECT trace_id, span_id, parent_span_id, span_name, start_timestamp, duration,
       is_exception, exception_type, exception_message, exception_stacktrace,
       attributes, otel_status_code
FROM records
WHERE trace_id = '[trace_id_1]'
  AND service_name = 'swingy'
ORDER BY start_timestamp ASC
```

**Attribute key reference** (verified 2026-03-17):
- Tool call name: `attributes->>'gen_ai.tool.name'`
- Tool response: `attributes->'tool_response'`
- LLM response text: `attributes->>'gen_ai.response.text'` (NOTE: often EMPTY — text not always captured by instrumentation)
- LLM tokens: `attributes->>'gen_ai.usage.input_tokens'`, `attributes->>'gen_ai.usage.output_tokens'`
- Agent name: `attributes->>'agent_name'`

**When result exceeds token limit**, the output is saved to a file. Use Python/jq to extract structured summaries:
```python
cat output.txt | python3 -c "
import json, sys
data = json.load(sys.stdin)
rows = data['result']
for r in rows:
    attrs = r.get('attributes', {}) or {}
    if r['span_name'] == 'running tool':
        print(f'{attrs.get(\"gen_ai.tool.name\",\"?\")} dur={r[\"duration\"]:.1f}s resp_len={len(json.dumps(attrs.get(\"tool_response\",\"\")))}')
"
```

---

## DB State Queries (Step 2c)

**Use Neon MCP** (`mcp__plugin_neon_neon__run_sql`) for all read queries below. No rate limiting, read-only, direct access. Availability confirmed in Step 1.5.

**Python script template** (reference only — for local debugging, not used in normal flow):

```bash
SWINGY_ENV=production uv run python -c "
import sys, asyncio, json
sys.path.insert(0, 'scripts')
from shared.database import fetch_all, close_db

async def main():
    results = {}
    # ... queries below ...
    await close_db()
    print(json.dumps(results, default=str, indent=2))

asyncio.run(main())
"
```

Use `shared.database.fetch_all(query, *args)` with positional `$1` parameters (NOT f-strings).
The module is `shared.database`, NOT `shared.neon.Database`.

```sql
-- Schema reference (verified 2026-03-22):
--   daily_evaluations: id, record_id, ticker, recommendation, entry_hit, stop_hit, target_hit, eod_price_vnd, pnl_percent, status, analysis, won, created_at, section
--   midday_data: id, record_id, trading_mode, entries_hit, afternoon_plan, created_at (NO check_date — join via record_id)
--   daily_recommendations: ticker, action, section, entry_price_vnd, stop_price_vnd, target_price_vnd, strategy, strategy_confidence, rationale
--   agent_beliefs: id, record_date, ticker, agent_key, ensemble_type, belief_narrative, direction, bull_probability, base_probability, bear_probability, price_target_vnd, timeframe_days, conviction, belief_status, prior_belief_id, days_held, update_reason, actual_direction, actual_price_vnd, outcome_date, brier_score, direction_correct, price_error_pct, created_at
--   v_agent_belief_accuracy (VIEW): agent_key, ensemble_type, scored_beliefs, avg_brier, brier_30d, direction_accuracy, avg_conviction, avg_streak_length, reversals, accuracy_streak_3plus, accuracy_fresh_beliefs

-- Daily record
SELECT * FROM daily_records WHERE record_date = '[target_date]';

-- Recommendations
SELECT ticker, action, section, entry_price_vnd, stop_price_vnd, target_price_vnd,
       strategy, strategy_confidence, rationale
FROM daily_recommendations
WHERE record_id = (SELECT id FROM daily_records WHERE record_date = '[target_date]');

-- Alerts registered
SELECT a.ticker, a.action_type, a.status, a.condition_logic, a.source_date,
       ac.condition_type, ac.condition_value
FROM alerts a
LEFT JOIN alert_conditions ac ON ac.alert_id = a.id
WHERE a.source_date = '[target_date]';

-- Evaluations (if retro ran)
SELECT ticker, recommendation, entry_hit, stop_hit, target_hit, eod_price_vnd,
       pnl_percent, status, won, analysis, section
FROM daily_evaluations
WHERE record_id = (SELECT id FROM daily_records WHERE record_date = '[target_date]');

-- Midday data (if midday ran) — linked via record_id, no check_date column
SELECT md.id, md.trading_mode, md.entries_hit, md.afternoon_plan, md.created_at
FROM midday_data md
JOIN daily_records dr ON md.record_id = dr.id
WHERE dr.record_date = '[target_date]';

-- Active agent configs
SELECT agent_key, model_id, temperature, max_tokens, enabled_tools
FROM agent_prompts WHERE is_active = true;

-- Swing watchlist (for weekly_watchlist_update review)
-- NOTE: uses sector_id FK, need JOIN for sector name
SELECT sw.ticker, s.name as sector, sw.stock_type, sw.rsi,
       sw.is_active, sw.is_pinned, sw.pin_reason, sw.created_at, sw.updated_at
FROM swing_watchlist sw
LEFT JOIN sectors s ON sw.sector_id = s.id
ORDER BY s.name, sw.ticker;

-- Longterm watchlist (for monthly_longterm_review)
SELECT lw.ticker, s.name as sector, lw.entry_zone_vnd, lw.conviction,
       lw.is_active, lw.created_at, lw.updated_at, lw.last_reviewed_at
FROM longterm_watchlist lw
LEFT JOIN sectors s ON lw.sector_id = s.id
ORDER BY s.name, lw.ticker;

-- Agent beliefs for target_date (belief system audit)
SELECT id, record_date, ticker, agent_key, ensemble_type, direction,
       bull_probability, base_probability, bear_probability, price_target_vnd,
       timeframe_days, conviction, belief_status, prior_belief_id, days_held,
       update_reason
FROM agent_beliefs
WHERE record_date = '[target_date]'
ORDER BY ensemble_type, ticker, agent_key;

-- Belief accuracy stats (rolling 30d, from view)
SELECT agent_key, ensemble_type, scored_beliefs, avg_brier, brier_30d,
       direction_accuracy, avg_conviction, avg_streak_length, reversals,
       accuracy_streak_3plus, accuracy_fresh_beliefs
FROM v_agent_belief_accuracy;

-- Orphaned belief chains (prior_belief_id points to non-existent row)
SELECT ab.id, ab.ticker, ab.agent_key, ab.prior_belief_id
FROM agent_beliefs ab
LEFT JOIN agent_beliefs prior ON ab.prior_belief_id = prior.id
WHERE ab.prior_belief_id IS NOT NULL AND prior.id IS NULL
  AND ab.record_date >= '[target_date]'::date - 7;

-- Unresolved beliefs past horizon (retro should have scored these)
SELECT id, record_date, ticker, agent_key, direction, timeframe_days
FROM agent_beliefs
WHERE outcome_date IS NULL
  AND record_date + timeframe_days * INTERVAL '1 day' <= '[target_date]'::date
ORDER BY record_date;
```
