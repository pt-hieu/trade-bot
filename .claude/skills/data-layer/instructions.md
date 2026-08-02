# Data Layer

## Three-Tier Access Hierarchy

Always use the correct tier for the data type. Never bypass a tier (e.g., don't call vnstock_client directly when shared/api wraps it with normalization).

| Tier | Module | Use for |
|------|--------|---------|
| **API-first** | `shared.api.prices`, `shared.api.technicals`, `shared.api.statistics`, `shared.api.fundamentals`, `shared.api.enrichment` | Prices, technicals, statistics, financial ratios, statements, foreign flow, insider transactions, corporate events |
| **HTTP client** | `shared.vnstock_client` | Price history, technicals, symbols, news, macro data, sector data |
| **DB queries** | `shared.neon.*` | Portfolio, trades, alerts, watchlist, config, learnings, daily records |

**Rule:** If the data is transactional or user-owned → DB. If it's market/company reference data → API-first.

**Migration 150 (2026-03-01):** `daily_prices`, `daily_technicals`, `daily_levels`, `mv_relative_strength`, `v_daily_returns`, `v_latest_technicals`, `v_portfolio_value_history` all DROPPED. No DB cache for market reference data — always fetch from API.

---

## API-First Pattern (`shared/api/`)

Modules in `shared/api/` wrap `vnstock_client` calls and normalize field names to a stable dict shape. Same function signatures as the old `shared.neon.*` modules — consumers only change the import path.

**Available modules:**
```python
from shared.api.prices import get_prices, compute_daily_return, compute_relative_strength
from shared.api.technicals import get_technicals, get_ticker_technicals
from shared.api.statistics import get_ticker_stats, get_all_stats
from shared.api.fundamentals import get_financial_ratios, get_financial_ratios_batch
from shared.api.enrichment import get_daily_flow, get_recent_insider_transactions
```

**Pattern (migration 142 + 150):**
```python
# Old (DB cache — DROPPED):
from shared.neon.technicals import get_ticker_technicals
from shared.neon.fundamentals import get_financial_ratios

# New (API-first):
from shared.api.technicals import get_ticker_technicals
from shared.api.fundamentals import get_financial_ratios
```

---

## HTTP Client Pattern (`shared/vnstock_client.py`)

Lazy singleton `httpx.AsyncClient` — created on first use, reused across calls within a pipeline run. **Always call `close_client()` at end of a pipeline** to release connections.

**Never instantiate the client directly.** All access goes through the module-level functions (`fetch_history`, `fetch_technicals_batch`, etc.).

Auth via `X-API-Key` header, configured from `VNSTOCK_API_URL` + `VNSTOCK_API_KEY` env vars.

---

## DB Query Pattern (`shared/neon/`)

All queries are async. Import from `shared.neon` (the re-exporting `__init__.py`), not from submodules directly.

```python
from shared.neon import get_portfolio_holdings, get_active_alerts
```

Both async and `_sync` variants exist. **Rule:** `_sync()` wrappers are ONLY for standalone CLI scripts that do not run async pipelines. Never call `_sync()` before `async with Database()` — it destroys the pool.

---

## Sync vs Async Rules

**The fundamental rule:** Never call `asyncio.run()` or `*_sync()` inside an `async def` function or before an async pipeline starts.

| Context | Use |
|---------|-----|
| Standalone CLI script (e.g., `prices.py`) | `*_sync()` wrappers are fine |
| Inside `async def` (agent tools, pipeline steps) | `await async_function()` ONLY |
| Module-level initialization before async pipeline | Move into `_main_async()`, never at module level |

**Recurring bug pattern:** `*_sync()` at module level → calls `asyncio.run()` → creates+destroys pool → later `async with Database()` gets `ConnectionDoesNotExistError`. See: daily_scan.py fix (d796b3a), llm_analysis.py fix (Feb 7 2026).

---

## None-Safe Dict Access (DB Rows)

All DB dict rows can have `None` for any column except PK. The `.get(key, default)` pattern is **wrong** because it only fires when the key is MISSING, not when the value is `None`.

```python
# WRONG — returns None when key exists as NULL:
action = r.get("action", "?")

# CORRECT — guards against both missing and None:
action = r.get("action") or "?"
shares = r.get("shares_registered") or 0
name = (r.get("name") or "Unknown")[:20]
```

Apply this rule everywhere: all `shared.neon.*` query results, `shared.api.*` normalized dicts, and any dict built from DB rows.

---

## Adding a New Data Source

1. **Decide the tier:** Is it transactional user data (DB), market reference from the API server (HTTP client), or a vnstock API direct call (API-first)?
2. **DB:** Add query function to the appropriate `shared/neon/*.py` submodule, re-export from `shared/neon/__init__.py`
3. **HTTP client:** Add `fetch_*` async function to `vnstock_client.py`; if normalization is needed, wrap in a new or existing `shared/api/*.py` module
4. **API-first wrapper:** Follow the interface-preserving pattern — same return shape as any equivalent DB function it replaces
5. **Never** add a DB table for data that the API returns fresh on each request — API-first by default for market reference data

---

## Gotchas

- **`fetch_news_articles()` swallows exceptions.** Returns `{}` on failure → pipeline proceeds with 0 articles silently. Should re-raise so caller can alert.
- **`sys.exit()` in async context raises `SystemExit(BaseException)`.** Not caught by `except Exception`. Use `return` for graceful exits in async pipeline functions — reserve `sys.exit()` for CLI entry points only.
- **`*_sync()` destroys async pools.** `*_sync()` calls `asyncio.run()` which creates+destroys a connection pool. If called at module level before an async pipeline starts, later `async with Database()` gets `ConnectionDoesNotExistError`. Only use `*_sync()` in standalone CLI scripts. Hit in: `daily_scan.py`, `llm_analysis.py`.
- **`.get(key, default)` doesn't guard against None.** DB rows can have `None` for any non-PK column. `r.get("action", "?")` returns `None` when key exists as NULL. Use `r.get("action") or "?"` instead. Hit 3x on `tool_get_insider`.
- **VND unit conventions at the boundary.** vnstock API returns prices in THOUSANDS VND and financial ratios as DECIMAL (roe=0.28 for 28%). `shared/api/` normalizes to: prices as VND integers (`close=30500`), display % as whole numbers (`change_pct=2.15`), rates as decimal 0-1 (`bounce_rate=0.65`). NEVER use magnitude heuristics like `if value > 1000: value /= 1000` — breaks for penny stocks and small percentages.
- **Always `close_client()` at end of pipeline.** The `vnstock_client` httpx singleton holds connections open. Forgetting to close leaks file descriptors across pipeline runs.
- **Import from `shared.neon`, not submodules.** All DB query functions are re-exported from `shared/neon/__init__.py`. Direct submodule imports break when functions are reorganized.
- **Fail-closed defaults for regime/signals.** When nullable DB columns return None for regime or signal values, default to the MOST CONSERVATIVE option (CAUTIOUS, ELEVATED, RISK_OFF), never NEUTRAL/CALM. Missing data = uncertainty = caution. Use `row["signal"] or "CAUTIOUS"` pattern.
- **VND magnitude: reject, never auto-correct.** Rule 18 says "No magnitude heuristics." If a price value is < 1000 VND, reject it with `logger.warning()` and return `None` — do NOT multiply by 1000. Penny stocks and OTC stocks can legitimately trade below 1000 VND.

---

## Related Skills

| Skill | Load when... |
|-------|-------------|
| `pipeline-workflows` | Understanding which pipeline step uses which data function |
| `agent-development` | Adding data access inside agent tools |
| `vnstock-api` | Adding a new API endpoint that `vnstock_client` will call |
| `database` | Adding a new DB table or query for transactional data |
| `mcp-server` | Adding a new MCP tool that exposes a `shared.neon.*` query |
