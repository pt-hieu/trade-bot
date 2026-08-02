# Pipeline Workflows

## Pipeline Schedules

| Pipeline | UTC | Vietnam | Cron |
|----------|-----|---------|------|
| Morning brief | 00:00 | 07:00 | daily |
| Midday check | ~04:00 | ~11:00 | daily |
| Retrospective | 08:00 | 15:00 | daily |
| Weekly watchlist | Sat 00:00 | Sat 07:00 | weekly |

---

## ⚠️ Critical Rules

- **Trading mode restrictions** — `determine_mode()` in `trading_mode.py` (deterministic):
  - `LOW_CASH` (0–5M VND deployable) → only TRIM/EXIT actions valid
  - `REALLOCATION` (0 VND) → only EXIT stagnant positions
  - **Never recommend BUY** when mode is not NORMAL
- **Alert dedup:** always call `tool_list_active_alerts` before registering a new alert to prevent duplicates
- **Alert expiry:**
  - Morning brief / midday alerts → expire at 14:45 VN (end of ATC)
  - Long-term / stop-loss alerts → expire after 5 trading days

---

## LLM Analysis Pipeline (`llm_analysis.py`)

Sequential pipeline, 9 steps:
1. **Market Level** — VN regime: RISK_ON / RISK_OFF / NEUTRAL
2. **Global Macro** — DXY, VIX, USD/VND → CALM / CAUTIOUS / ELEVATED / CRISIS
3. **Sector Rotation** — hot/cold sectors
4. **Sector Analysis** — 6 sectors sequentially
5. **Long-Term Watchlist** — compare to entry zones
6. **Position Monitor** — exit/trim signals
7. **Trading Mode** — NORMAL / LOW_CASH / REALLOCATION
8. **Foreign Flow** — foreign investor activity
9. **Synthesis** — final brief (Synthesis → 1-pass narrative critic)
10. **Write Recommendations** — structured recs from picks/alerts/signals → DB (no LLM parsing)

**Structural correctness** (R:R, mode compliance, position sizing, cross-section dedup) is enforced deterministically by `recommendation_builder.py` + `recommendation_validator.py`. The critic validates narrative quality only (regime context, psychological awareness, coherence). Refiner has been removed — critic findings are appended as warnings, not rewritten by LLM.

---

## Retrospective Pipeline (`retrospective.py`)

Sequential, 9 steps:
1. Parse morning brief recommendations
2. Parse midday adjustments (if exists)
3. Fetch EOD prices
4. Evaluate sector rotation + macro regime accuracy
5. Evaluate morning recs vs EOD + midday adjustments vs EOD
6. Check trading mode compliance
7. Extract patterns (winning, losing, midday, macro)
8. Update previous day's `next_day_change`
9. Generate retrospective + update learnings in DB

---

## Weekly Watchlist Pipeline (`weekly_watchlist_update.py`)

Schedule: Saturday 00:00 UTC (07:00 Vietnam). Entry: `scripts/weekly_watchlist_update.py`.

Architecture: Fan-out / Fan-in (4 sector evaluators + 1 coordinator).

1. **Pre-fetch** — Python gathers technicals (live API), articles, catalysts, portfolio, geopolitical context
2. **Fan-out** — 4 `watchlist_sector_evaluator` agents run in parallel (tool-free, context-injected):
   - Banking
   - Securities
   - Real Estate + Infrastructure
   - Consumer + State-Owned + Technology
3. **Fan-in** — `watchlist_coordinator` merges evaluations into additions/removals
4. **Post-hoc** — Python validates: confidence downgrade, churn detection, portfolio conflict auto-removal, 2-per-sector cap, score threshold, pinned tickers
5. **Apply** — Writes to `swing_watchlist` (add/remove/update), syncs RSI

**Key files:** `scripts/agents/watchlist_ensemble/` (orchestrator package), `scripts/agents/watchlist_validators.py` (post-hoc validators), `scripts/agents/watchlist_update.py` (models, SECTOR_MAP)

---

## Monthly Longterm Review (`longterm_review.py`)

Schedule: 1st of month 01:00 UTC (08:00 Vietnam). Entry: `scripts/longterm_review.py`.

5-step pipeline:
1. **Deterministic pass** — fetches 8 quarters of financials, calculates entry zones, conviction scores, review flags
2. **VN30 screening** — screens VN30 tickers not on watchlist (ROE > 10%, PE < 30)
3. **LLM pass** — batched Kimi-K2.5 calls for research updates, entry zone adjustments, additions/removals
4. **Apply** — writes to `longterm_watchlist`, `company_research`, `moat_assessments`, `thesis_pillars`, `kill_criteria`
5. **Notify** — Telegram summary

**Key files:** `scripts/longterm_review.py`, `scripts/longterm/deterministic.py`, `scripts/longterm/apply_results.py`, `scripts/agents/longterm_review.py`

---

## Alert Monitoring Architecture

```
Morning Brief / Midday Check
    → Alert Registrar Agent → registers in `alerts` table
    → Alert Monitor Daemon (Lightsail, 5-min polls)
        → Checks conditions vs live prices
        → Telegram notification on trigger
        → Optionally dispatches GH Actions for LLM analysis
    → Alert Analyst Agent (GH Actions)
        → Returns BUY_NOW / WAIT / SKIP / EXIT_NOW
```

**Alert condition types:**
| Type | Trigger |
|------|---------|
| `price_below` | Intraday low ≤ value (BUY entries) |
| `price_above` | Intraday high ≥ value (TRIM/EXIT) |
| `rsi_below` | RSI drops below value (oversold) |
| `rsi_above` | RSI rises above value (overbought) |
| `volume_spike` | Volume/avg ≥ value (breakout confirmation) |

---

## GH Actions Trigger Patterns

Two trigger types:
- **Cron** (`schedule:`) — daily-scan, midday-check, market-close-retro, weekly-* all use cron. Skipped on market holidays (checked via `shared.market_calendar`).
- **repository_dispatch** — `alert-analysis.yml` is triggered by the alert monitor daemon when an alert fires. Event type: `alert-analysis`. The alert_monitor script posts to GH API which dispatches the workflow.

When adding a new pipeline: use cron for time-based, repository_dispatch for event-based. Always add a `workflow_dispatch` trigger for manual testing.

GH Actions passes secrets as env vars. Required secrets: `NEON_DATABASE_URL`, `VNSTOCK_API_KEY`, `VNSTOCK_API_URL`, `OPENROUTER_API_KEY`, `LOGFIRE_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

---

## Data Access Rule (API-First)

Never add a DB table for data available via API. Market/company reference data (prices, technicals, financials, flow, events) comes from the API. Only transactional/user-owned data (portfolio, alerts, watchlist, records) lives in the DB.

Full data source rules: see `data-layer` skill.

---

## Notification Pattern

Each pipeline ends with a `*_notify.py` script that formats the pipeline's research file for Telegram and sends two messages (action-first split):
- **Message 1:** Action sections (STANCE, WHAT TO DO TODAY, MY HOLDINGS, TOP PICKS)
- **Message 2:** Context sections (THEME, GLOBAL CONTEXT, MARKET MOOD, etc.)
- **Skipped sections:** Verbose sections (GOAL PROGRESS, MINDSET, etc.) appear only in the web app / research file

Pattern: read from `research/` markdown file → parse section headers → filter by message group → send via `shared.telegram.send_telegram()`.

When adding a new pipeline with Telegram output, follow this two-message split pattern. Always import `send_telegram` (not `send_telegram_message` — wrong function name).

---

## Discovering the Codebase

- **Which DB tables exist, which script writes them** → explore `scripts/shared/neon/` and `scripts/`
- **Pipeline schedules** → explore `.github/workflows/` for exact cron schedules
- **Script purposes** → explore `scripts/*.py` — each has a module docstring
- **DB schema** → explore `scripts/db/migrations/` in order

---

## News Pipeline (`news_pipeline.py`)

Runs between `daily_scan.py` and `llm_analysis.py`. 10-step lifecycle:
```
RSS fetch → dedup → blocklist pre-filter → LLM relevance score → score threshold (≥6)
→ LLM summarize → DB insert → ticker tag + sentiment → keyword filter → examiner → discovery
```

**Silent failure modes (audited 2026-03-23):**
- LLM scoring failure defaults to score=0 → entire batch silently excluded (no alert)
- RSS fetch failure returns empty dict → pipeline proceeds with 0 articles (no alert)
- News examiner failure returns empty classifications → catalyst discovery skipped (no alert)
- Per-site RSS failure at API level not reported in response

**Keyword filter** (`news_filter.py`): Only 67 hardcoded keywords gate catalyst/event discovery. Missing terms: `thâu tóm`, `trái phiếu`, `lạm phát`, `thuế quan`, `thoái vốn`, `cổ phần hóa`, `gdp`, `fed`, `tái cơ cấu`.

**Content fallback chain** (`articles_vn.py:_summarize_articles()`): Checks `markdown_content > content > short_description`. Vietstock puts content in `description` field which is not checked → empty summaries.

---

## Gotchas

- **News content fallback chain misses Vietstock.** `articles_vn.py:_summarize_articles()` checks `markdown_content > content > short_description` but skips `description`. Vietstock RSS puts article body in `description` field → empty summaries. Fix: add `description` to the fallback chain before `short_description`.
- **`init_session()` required in every pipeline entry point.** Call `init_session("pipeline_name")` right after `configure_observability()`. Groups all LLM calls in a single OpenRouter session for tracing. Module: `shared.session`. If missing, `get_extra_body()` logs a warning and session tracking is silently disabled.
- **`send_telegram`, not `send_telegram_message`.** Wrong function name is a common import error. Always `from shared.telegram import send_telegram`.
- **Market holidays skip pipelines silently.** Cron still triggers GH Actions, but `shared.market_calendar` gate exits early. If no traces for a date, check if it was a holiday before debugging further.
- **Alert dedup is caller's responsibility.** Always call `tool_list_active_alerts` before registering a new alert. The DB has no unique constraint — duplicate alerts produce duplicate Telegram notifications.
- **`workflow_dispatch` traces have no cron schedule.** Manual runs show up in Logfire but don't match any pipeline schedule window. Don't flag them as anomalies during pipeline review.
- **Trading mode restrictions are deterministic.** `determine_mode()` in `trading_mode.py` is pure Python — never computed by LLM. LOW_CASH and REALLOCATION modes hard-block BUY recommendations regardless of agent output.
- **`recommendation_overrides` iteration requires `isinstance(o, dict)` guard.** Strings can appear from malformed JSONB. Retro crashed 2026-03-24 on `commentary.py:123` calling `.get()` on a string. Guard pattern: `for o in recommendation_overrides: if isinstance(o, dict): ...`. Example exists in `midday_check.py:271`.
- **`trading_mode` DB enum only accepts `NORMAL`, `LOW_CASH`, `REALLOCATION`.** Never use `"N/A"`, `"UNKNOWN"`, or other strings. Safety net: `_normalize_trading_mode()` in `insert_records.py` defaults invalid values to `"NORMAL"`.
- **LONGTERM positions get no trailing_stop alerts by default.** `compute_trailing_stop()` returns `stop: None` for LONGTERM (thesis-based). Only SWING stops persist to `trailing_stops` table. Fixed 2026-03-24: catastrophic_stop now also persisted for LONGTERM positions.
- **`fetch_eod_prices()` only queries swing_watchlist + holdings.** Longterm-only tickers (on `longterm_watchlist` but not on `swing_watchlist` or held) get no EOD prices in retro → `eod=None`, `status=MISSED`. Fixed 2026-03-24: added longterm watchlist tickers as pseudo-sector before price fetch.
- **MISSED tickers inflate `compute_day_summary()` win_rate.** MISSED evals have `won=NULL` but passed the `has_entry_data is not False` filter, inflating the denominator. Fixed 2026-03-25: added `won is not None` to `countable` filter.
- **`update_learnings()` had duplicate `won` logic.** Used `pnl_percent >= 0` for HOLD instead of canonical `day_change >= -1.0` from `compute_won()`, and scored MISSED as losses. Fixed 2026-03-25: now uses pre-computed `won` field with `compute_won()` fallback.
- **Alert cancellation must handle multi-day gaps.** `cancel_stale_alerts(scan_date)` cancels ALL active alerts where `source_date < scan_date`, not just yesterday. Weekends/holidays create 2-3 day gaps — single-day subtraction misses Friday's alerts on Monday.
- **News re-runs destroy enrichment.** `insert_articles` used DELETE+INSERT per `search_id`, wiping `narrative_id` and `content_embedding` set by later pipeline stages. Fixed 2026-03-27: UPSERT preserves enrichment columns; `articles_exist_in_db` now skips insert entirely.
- **Resume path is a second-class citizen.** `phase_resume.py` reconstructs state from DB but misses fields only available in-memory during the live path (commodity_prices, market_valuation, vn_economy, geopolitical_shock). Every new context source added to the normal path must also be loaded in the resume path. Tech debt: should be refactored into a single checkpoint-aware path.
- **Longterm entry zone alerts removed (2026-03-29).** `register_longterm_entry_zone_alerts()` was 77% of alert volume, 0% actionable. Prices sat chronically below the configured entry zones, so alerts were recreated daily as duplicates. Longterm watchlist page shows same info. Do NOT re-add without solving: (1) stale entry zones, (2) "already in zone" detection, (3) once-only triggering.
- **Anti-instant-trigger requires live prices for ALL tickers.** `phase_alerts.py:run_phase5_alert_pipeline()` now fetches prices for non-held tickers via `get_prices()`. Previously only holdings had prices, so non-held ticker alerts bypassed the guard and triggered within minutes of creation.
- **Trailing stop max-distance filter (10%).** Catastrophic stops >10% below current price are skipped — they're safety nets, not intraday alerts. Only near-price stops (trailing_50pct, breakeven, etc.) generate alerts.
- **Scoring threshold must match market volatility.** `DIRECTION_THRESHOLD_PCT` in `belief_scoring.py` defines BULLISH/NEUTRAL/BEARISH outcome classification. At 3.0%, VN 5-day moves were 71% NEUTRAL, 0.7% BEARISH — making accuracy measurement meaningless. Lowered to 1.5% (2026-04-06). When adjusting, verify via `SELECT actual_direction, COUNT(*) FROM agent_beliefs WHERE brier_score IS NOT NULL GROUP BY actual_direction`.
- **`derive_direction_from_probabilities()` applies at every belief layer.** Individual beliefs, LLM aggregators, AND deterministic aggregator all call this function. Changing direction-derivation logic (e.g., tiebreak → min-probability gate) cascades through the entire belief pipeline.

---

## Related Skills

| Skill | Load when... |
|-------|-------------|
| `agent-development` | Modifying or adding agents that run inside pipeline steps |
| `database` | Understanding which tables a pipeline writes to, or adding a new one |
| `infra-ops` | Understanding where pipelines run (GH Actions) and which deploy to Lightsail |
| `logfire-traces` | Debugging a pipeline run by inspecting agent traces |
| `data-layer` | Changing where a pipeline reads data from (API vs DB) |
