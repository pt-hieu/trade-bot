# Data Collection

Script-first data fetching for pipeline analysis. One Bash call replaces 15-20 MCP round-trips.

## Core Principle

**Prefer Python scripts over MCP tool calls.** Scripts are faster (single process), produce deterministic output, and can do joins/aggregations that MCP can't.

| Use script when... | Use MCP when... |
|----|----|
| >3 data points needed | Quick single lookup |
| Multi-table joins | One-off `SELECT 1` check |
| Date range queries | Interactive exploration |
| Reproducible output needed | Uncertain what to query |

---

## Pre-Built Collector: `collect_review_data.py`

Fetches all pipeline review data in ~10s.

```bash
SWINGY_ENV=production uv run python scripts/collect_review_data.py --date 2026-04-02 --scope full
```

**Args:** `--date YYYY-MM-DD` (default: today VN TZ), `--scope {full,morning,midday,retro}`

**Output:** `/tmp/swingy-review-{date}/` with JSON files:

| File | Content |
|------|---------|
| `manifest.json` | Metadata, per-query status, timing |
| `daily_record.json` | Single daily_records row |
| `recommendations.json` | daily_recommendations |
| `alerts.json` | Alerts + conditions by source_date |
| `evaluations.json` | daily_evaluations (retro) |
| `midday.json` | midday_data |
| `agent_config.json` | Active agent_prompts |
| `watchlist_swing.json` | Swing watchlist with RSI |
| `watchlist_longterm.json` | Longterm watchlist |
| `beliefs.json` | agent_beliefs for date |
| `belief_accuracy.json` | v_agent_belief_accuracy view |
| `belief_orphans.json` | Orphaned belief chains |
| `belief_unresolved.json` | Past-horizon unresolved |
| `portfolio.json` | Current holdings |
| `cash.json` | Cash balance |
| `git_fixes.json` | Same-day commits with `is_fix` flag |
| `gh_actions.json` | Workflow run metadata |
| `logfire_traces.json` | Pipeline trace spans (if `LOGFIRE_READ_TOKEN` set) |
| `logfire_spans.json` | All spans with full attributes (if token set) |
| `errors.json` | Non-critical query failures |

**Error handling:**
- Critical queries (`daily_record`, `recommendations`): failure = non-zero exit
- Non-critical: logged to `errors.json`, script continues
- Check `manifest.json` → `failed_queries` count

**Data cleaning:** DB records have null fields and `context_embedding` stripped. Logfire spans kept raw. Missing key = NULL in DB.

---

## Adhoc Script Template

For custom queries not covered by the collector:

```python
#!/usr/bin/env python3
"""Adhoc: <purpose>"""
import sys, asyncio, json
from datetime import date
from pathlib import Path
sys.path.insert(0, "scripts")
from shared.env import load_env
from shared.database import fetch_all, close_db
load_env()

OUTPUT = Path("/tmp/swingy-adhoc-<purpose>")

def write_json(name, data):
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / f"{name}.json").write_text(json.dumps(data, default=str, indent=2))
    print(f"  {name}: {len(data) if isinstance(data, list) else 1} rows")

async def main():
    results = await fetch_all("SELECT ... FROM ... WHERE ... = $1", date(2026, 4, 2))
    write_json("results", [dict(r) for r in results])
    await close_db()
    print(f"Done -> {OUTPUT}")

asyncio.run(main())
```

Run: `SWINGY_ENV=production uv run python /tmp/swingy-adhoc-<purpose>.py`

**Key patterns:**
- Use `shared.database.fetch_all/fetch_one` with `$1` positional params
- Reuse `shared.neon/` functions where they exist (portfolio, watchlist, beliefs, etc.)
- `json.dumps(data, default=str)` handles dates, Decimals, UUIDs
- Always `await close_db()` at the end

---

## Logfire REST API

When `LOGFIRE_READ_TOKEN` is in `.env`, query Logfire directly (no MCP needed):

```python
import httpx

def logfire_query(token: str, sql: str, limit: int = 500) -> list[dict]:
    resp = httpx.get("https://logfire-eu.pydantic.dev/v1/query",
        headers={"Authorization": f"Bearer {token}"},
        params={"sql": sql, "limit": str(limit)}, timeout=30)
    resp.raise_for_status()
    cols = resp.json().get("columns", [])
    if not cols: return []
    names = [c["name"] for c in cols]
    vals = [c["values"] for c in cols]
    return [{names[i]: vals[i][r] for i in range(len(names))} for r in range(len(vals[0]))]
```

**Key Logfire SQL:**
```sql
-- Trace discovery
SELECT trace_id, span_name, start_timestamp, duration
FROM records WHERE span_name IN ('morning_brief_generation', 'midday_check', 'retrospective_generation')
AND service_name = 'swingy' ORDER BY start_timestamp DESC LIMIT 20

-- All spans for a trace (one trace at a time, 100-row limit)
SELECT trace_id, span_id, parent_span_id, span_name, start_timestamp, duration,
       is_exception, attributes
FROM records WHERE trace_id = '{id}' AND service_name = 'swingy'
ORDER BY start_timestamp ASC
```

**Span attribute keys:** `gen_ai.tool.name`, `tool_response`, `gen_ai.response.text` (often empty), `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `agent_name`

**Without token:** Fall back to Logfire MCP calls. Sleep 15s between each. One trace_id per query (100-row limit).

---

## Gotchas

- **`SWINGY_ENV=production` required** — without it, `shared.database` connects to local Docker (empty)
- **Logfire rate limits** — 15s between MCP calls. REST API has no documented rate limit.
- **100-row Logfire limit** — always query one trace_id at a time
- **`gen_ai.response.text` often empty** — infer reasoning from output artifacts vs input data
- **Age param = minutes from NOW** — today: 1440, yesterday: 2880, N days ago: (N+1)*1440
- **DB module is `shared.database`** not `shared.neon.Database`
