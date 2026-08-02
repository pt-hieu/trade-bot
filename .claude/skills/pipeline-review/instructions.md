# Pipeline Review

Systematic review of agent pipeline runs. Data fetch → 3 parallel subagents → severity-ranked report.

## Prerequisites

Load these skills first:
1. `linear` — issue protocol, label taxonomy, workflow states, fenced-JSON contract, write-back script
2. `data-collection` — script-first data fetching, collector CLI, Logfire REST API
3. `pipeline-workflows` — phase ordering, DB table mappings, schedules
4. `agent-development` — agent config, tool registry

---

## Step 1: Target Resolution

- **target_date** — defaults to today. Accepts "yesterday", specific dates.
- **scope** — `full` (default), `morning`, `midday`, `retro`

---

## Step 2: Data Fetch

Run the collector (see `data-collection` skill for full reference):

```bash
SWINGY_ENV=production uv run python scripts/collect_review_data.py --date [date] --scope [scope]
```

Check `manifest.json` for failures. Read JSON files from `/tmp/swingy-review-{date}/`.

The collector also ships two Linear-backed markdown files into the bundle: `monitoring_items.md` (active regression-watch) and `resolved_items.md` (Resolved ≤90 days regression cross-check). Both inject into every subagent prompt. Source of truth, outage behavior, and the export-script details live in the **`linear` skill**; see `references/monitoring_items.md` for the bundle-side update protocol.

### Step 2a: Active-issues cross-check (MANDATORY)

Subagents consume the regression-watch slice only. The orchestrator lists all Linear OPEN/ESCALATED issues via `mcp__claude_ai_Linear__list_issues`, scoped to team Swingy. See the `linear` skill for category/severity/state semantics. The pipeline-review-specific routing — every new finding maps to one row in this table — stays here:

| Matches | Action |
|---------|--------|
| OPEN/ESCALATED `category:regression-watch` (or `category:bug`) | record under `bumps[]` in the subagent's fenced JSON, cite the Linear id |
| OPEN `category:scheduled-work` | record as `[INFO] (deferred as <Linear-id>)` in prose; no JSON write (work already queued) |
| OPEN `category:audit-finding` | cite parent Linear id; if materially worse, record under `new[]` with `category: regression-watch` so the orchestrator files a child issue and links via `blockedBy` |
| No match | record under `new[]` per the fenced JSON contract (see `linear` skill) |

Add one line to the aggregated report header: `Active issues cross-check: N regression-watch / N scheduled-work / N audit-finding / N bug`.

---

## Step 3: Launch 3 Parallel Subagents

All 3 as **background Opus** agents. Data delivered **inline** — read JSON files and embed into each prompt. Subagents make zero tool calls.

See `references/subagent-prompts.md` for full prompts, the auditor role (Skeptical Auditor + CoVe + abstinence), the mandatory finding-line format (severity, confidence tag, citation, counter-argument, tracked-id), severity rules, and the data routing table. Every subagent prompt MUST embed the Shared Rules + Auditor role + Finding line format blocks verbatim — do not paraphrase them away when building per-subagent prompts.

| # | Subagent | Focus |
|---|----------|-------|
| 1 | Inputs & Config | Tool call results (stale/empty/errors) + model assignments, token usage, tool availability |
| 2 | Reasoning & Output | LLM outputs (hallucinations, contradictions, belief continuity) + recommendation coherence, R:R, belief validation, published-brief checks |
| 3 | Resilience & Integration | Failures, silent swallows, missing outputs + cross-pipeline data flow and belief-system integration |

---

## Step 4: Aggregate Report

```markdown
# Pipeline Review: [scope] [date]

## Overview
- Pipelines reviewed: [list]
- Duration: Xs | Tokens: N | Cost: $X.XX  *(tokens/cost sourced from Subagent 1 Inputs & Config)*
- Trace IDs + Logfire links
- Monitoring items carried in: N open, N escalated

## Findings by Dimension (3)
### [Dimension] [OK/WARNING/CRITICAL]
- [finding with evidence] (cite SWI-NN if tracked)

## Severity-Ranked Issues
1. [CRITICAL] dimension: description
2. [WARNING] dimension: description

## Linear Updates (regression-watch)
- Opened: [SWI-NN ids]
- Bumped (reproduction comment): [SWI-NN ids]
- Resolved-candidate: [SWI-NN ids]
- Confirm-regression flipped: [SWI-NN ids]

## Recommendations
- Actionable fixes ranked by impact
```

**Ranking:** CRITICAL first. Within severity: resilience/integration > reasoning/output > inputs/config. Include file paths.

### Cross-subagent conflict reconciliation (mandatory)

Before ranking, scan the three subagent reports for contradictions:

- **Same evidence → different severity** — if two subagents cite the same span/row/file and disagree on severity, pick the higher, note the disagreement explicitly in the report ("Reasoning auditor: WARNING; Integration auditor: INFO — both cited `recommendations.json:108`"), and include the weaker auditor's `counter:` line so the reader sees both sides.
- **Confidence disagreement** — a HIGH-confidence finding from one auditor and a LOW-confidence related finding from another should be merged into a single entry, not double-counted.
- **UNVERIFIABLE vs CRITICAL** — if one auditor flagged a finding as UNVERIFIABLE and another as CRITICAL on the same evidence, the CRITICAL auditor must have cited additional data not available to the first — quote the extra evidence in the aggregated finding. If no extra evidence exists, downgrade to WARNING and add a note.
- **Never silently drop** a finding to resolve a conflict. All three subagent reports' raw findings must be accounted for in the aggregated report, even if only as "downgraded to INFO after cross-check".
- **Plan-type suspect × basis-consistency conflict.** If one subagent reports "P/L math is consistent with the cited basis" as OK/INFO AND another subagent flags "plan_type is suspect" (e.g. plan-type-rule coherence, watchlist-ground-truth cross-check, or any OPEN MON item whose watch-for names plan_type), escalate the aggregated finding to CRITICAL. Rationale: basis-consistency proves internal arithmetic, not that the correct rule was applied. This conflict pattern is the exact failure mode that lets a SWING max-loss ceiling be applied to a LONGTERM slice while the P/L math internally reconciles.
- **Thinking-grounded vs. artifact-only on the same span.** When two subagents
  cite the same span and one quotes thinking while the other cites only JSON
  artifacts, the thinking-grounded finding's severity wins — the quote answers
  "why" and routes the fix to the right layer; artifact-only frequently mis-routes.
  Exception: when the FPT-class plan-type-suspect × basis-consistency rule already
  escalated the artifact-only finding to CRITICAL, that escalation takes precedence.

### Step 4a: Write findings back to Linear (mandatory)

After aggregation but **before** presenting the report, concatenate the three subagent reports and invoke:

```bash
SWINGY_ENV=production uv run python scripts/process_review_findings.py \
    --source-kind pipeline-review \
    --report /tmp/swingy-review-<date>/aggregated-report.md
```

The `linear` skill documents the script's behavior (parse last fenced JSON block, content-hash sentinel dedup, four tag actions, parse-failure fallback). Include the "Linear Updates" section in the final report so the user sees which issues moved.

**Cross-category bumping (pipeline-review-specific):** when a subagent finding matches an existing OPEN issue in ANY category (not just regression-watch), record it under `bumps[]` with the Linear id. A reproducing finding on a `category:bug` or `category:audit-finding` issue is a regression signal just like one on a `category:regression-watch` issue.

---

## Gotchas

- **Thinking-first is mandatory for any agent-behavior claim.** Before flagging an
  agent as having hallucinated, ignored an instruction, looped, drafted-then-
  discarded, or echoed stale injection, open `logfire_spans.json` for that span
  and read the model's thinking. Path: `attributes."pydantic_ai.all_messages"` on
  `agent run` spans; `attributes."gen_ai.output.messages"` on `chat` spans.
  Thinking is what distinguishes a model bug from a prompt bug from an injection
  bug — the same artifact symptom routes to different fix layers depending on
  what the model was responding to. When `all_messages` is missing (FallbackModel
  post-failover, `is_exception=true` early timeout), report `[UNVERIFIABLE:
  all_messages_absent]` and move on — do not fabricate a quote. Read thinking
  only for spans you flag; quote ≤30 words.
- **Opus for all 3 subagents.** Sonnet misses subtle cross-pipeline inconsistencies.
- **`recommendation_overrides`** needs `isinstance(o, dict)` guard — strings from malformed JSONB.
- **Duplicate beliefs** possible until migration 222 unique constraint.
- **`won` field** was NULL before 2026-03-24 fix in `won.py`.
- **Logfire `gen_ai.usage.input_tokens` is CUMULATIVE across rounds**, not per-call. An agent run showing 75K input tokens may only peak at 13K per individual LLM call. Always drill into child `chat` spans to see per-round growth before flagging context bloat.
- **`reconcile_regimes()` overrides market_level output.** When `global_risk_regime=ELEVATED/CRISIS`, market_regime is floored to RISK_OFF regardless of agent output. Check both `market_regimes` table (raw) and `daily_records` (reconciled) to spot this.
- **`win_rate` has mixed DB conventions.** `daily_records.win_rate` is 0-100 scale; `learning_patterns.win_rate` is 0-1 scale. The `:.0%` format is correct for 0-1 values only. Hit 2026-04-06: 10000% win rate from double-conversion.
- **Unbounded string fields cause runaway generation.** Sector aggregator hit 96K output tokens because `belief_narrative`, `note`, `summary` had no `max_length`. Mixed/heterogeneous sectors can't compress like industry-themed ones — model writes exhaustive per-ticker essays.
- **Belief-aggregation down-weighting (current as of 2026-05-13).** Brier-based agent weighting uses a smooth saturator anchored at the uninformed-forecaster Brier (~0.47), graduating to a **0.15 weight floor** — agents are NEVER fully muted. Hard exclusion was attempted (commit `de964704`) and reverted (commit `73058107`, then re-landed as graduated formula in SWI-262 `6bad165f`) because complete muting starved `synthesis_picks` of sector beliefs. SWI-122 (`239e0247`) tightened the slope and added the curve-pinning regression test `tests/unit/test_belief_aggregation_smooth.py` to prevent silent re-revert. Source: `scripts/agents/belief_aggregation/_core.py:57-92`. Do not describe the system as "auto-excluding poor agents" — the floor is the load-bearing invariant.
- **Midday "DEFENSIVE stance" vs NORMAL mode is expected.** `trading_mode` (NORMAL/LOW_CASH) = capital availability (deterministic from cash). Strategy stance (DEFENSIVE/AGGRESSIVE) = market posture (from strategy directive). These are orthogonal by design — not a contradiction.
- **MiniMax M2.7 structured output limitation.** Can't reliably produce nested Pydantic schemas (3+ levels). Triggers retry storms via inverted FallbackModel. Only use for flat classifiers (news_examiner, capital_events). Hit 2026-04-06: sector_news 10 retries, 651s, 30% coverage gap.
- **MiniMax-primary agents (capital_events, news_examiner, watchlist_*) don't run in morning scan.** They're separate pipelines (news_pipeline.py, the watchlist_ensemble package). Don't flag their absence from morning Logfire traces.
- **Agent config is in YAML files** (`scripts/agents/configs/*.yaml`), not DB. `agent_prompts` table dropped in migration 300.
- **Always check `markdown_briefs.json` for EMBED placeholder leakage, R:R drift, and verb mismatch.** JSON artifacts (`recommendations`, `beliefs`) do not capture what actually ships in the user-facing `research/{date}/morning-brief.md`. The 2026-04-15 review caught EMBED leakage, R:R 3.0↔3.5 drift, and a TRIM↔HOLD mismatch only because those files were read manually. Subagent 2 (Reasoning & Output) receives `markdown_briefs.json` per the data routing table.
- **Midday cascading failure requires reading `gh_failed_step_logs`.** Logfire traces for midday may be just the root span (e.g. 4.49s, 0 agents) if the script died in the notify step, not the check step. The collector now embeds `gh run view --log-failed` output on any failed workflow run — read `gh_actions.runs[i].failed_step_log` before concluding the trace is sparse.
- **Silent provider hangs emit a `silent_provider_hang` span.** As of 2026-04-16 the sector_aggregator and positions_aggregator TimeoutError handlers open a dedicated span with `hang_type=silent_provider`, `agent=<name>`, `wall_s=120`. Query by `span_name = 'silent_provider_hang'` instead of the old `tokens=None/None` heuristic.
- **T+2 settlement suppresses stop alerts on fresh buys.** `scripts/agents/alert_registrar/conflict_resolution.py:43-51` applies `is_sellable()` from `shared/rules/settlement.py`. SWING positions bought within 2 trading days have `sellable_shares=0` and intentionally carry no stop-alert row. Before flagging "no stop alert on held position", cross-check `portfolio_plan_check.per_plan[ticker].days_since_entry` (or `portfolio_holdings.entry_date` vs `settlement_date()`) — any position with `days_since_entry < 2` is pre-settlement by design.
- **Stop price may be NULL on HOLD/EVALUATE recs pre-Fix-1 (2026-04-25).** Before flagging "midday stop-breach semantic drift" or "retro `stop_hit=false` mismatch", query `daily_recommendations.stop_price_vnd` for the subject ticker. If NULL, the retro `stop_hit = bool(stop_price) and eod_low <= stop_price` evaluates to `false` trivially via `bool(None)` and the real root cause is persistence, not semantics. Post the stop-resolution contract landing, this shortcut is closed; keep the gotcha until 3 consecutive clean scans have passed.
- **Off-universe manual buys have intentionally-thin coverage.** Tickers in `portfolio_holdings` but absent from `watchlist_swing ∪ watchlist_longterm` are manual/discretionary buys (precedent: SWI-157 → SWI-49, resolved-by-deferral 2026-04-22). Sparse belief/signal data is by design, not a defect. Before flagging "Value analyst unavailable" or "sub-agent coverage gap" on a held ticker, check `portfolio_plan_check.per_plan[ticker].in_watchlist` — if `false`, treat coverage findings as INFO (not WARNING/CRITICAL).
- **`streak_alert` two-phase write divergence is expected.** A single `daily_records` row carries `streak_alert_json` (today's retro, post-EOD) and `gate_decision_json.inputs_digest.streak_alert` (yesterday's retro snapshot frozen at gate-decision time). Cross-column `length` / `start_date` divergence is the EXPECTED signature of this two-phase write — by design per commit `da47dc62`. ONLY flag this pair when `gate_profile` differs between the two snapshots; that's the real regression signal. Backstory: the 2026-05-13 pipeline-review misclassified this as a CRITICAL split-brain bug after a transient false-BUY rec was deleted post-retro.

---

## Related Skills

| Skill | When |
|-------|------|
| `data-collection` | Always (prerequisite — data fetch) |
| `pipeline-workflows` | Always (prerequisite — phase ordering) |
| `agent-development` | Always (prerequisite — agent config) |
| `finance-prompting` | Reasoning quality issues trace to prompt quality |
| `trading-context` | Validate recommendations against strategy rules |
