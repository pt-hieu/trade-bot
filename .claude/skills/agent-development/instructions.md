# Agent Development

## Python / LLM split (load-bearing — read before adding any post-LLM gate)

**Python decides** (deterministic, authoritative, may override LLM output):
- Hard structural invariants — max-loss ceiling, position size, R:R, concentration limits.
- Cross-run state merge — rank, coverage, retry-attempt preservation.
- Audit-tag enforcement, schema-migration drift checks, fail-closed defaults.
- Counting / arithmetic / lookup / set membership / threshold comparisons on raw inputs.
- Anything expressible as a closed-form rule over numeric or enum data.

**LLM decides** (qualitative, authoritative, NOT overridden by Python):
- EXIT/HOLD/EVALUATE/TRIM/ADD verdicts, direction, urgency, confidence labels.
- Sentiment, intent, polarity, framing, sarcasm, narrative interpretation.
- Conflict resolution between sub-analyst views.
- Coverage-health *judgment* — how to act given X/N coverage (the count itself is Python).
- Multi-signal weighing — when a numeric trio "looks like" failure but a qualitative veto
  applies (e.g. ADX/insider/RS thresholds met but bullish divergence visible on tape).

**The boundary, restated**: if a fix is tempted to add a Python post-LLM gate that
downgrades an LLM-emitted *qualitative* action, the fix is at the WRONG layer. The right
response to a wrong qualitative call is a prompt fix — vetos, paired exemplars,
confidence calibration, worked examples — not a deterministic override.

This rule binds even when the LLM is observably wrong on a specific historical case.
A naive Python gate calibrated to one incident reliably mis-fires on the next, because
the gate encodes the *symptoms* of one wrong call, not the *judgment* that distinguishes
right from wrong calls.

**Acceptable Python post-LLM operations** (do NOT violate the rule):
- Stamping audit metadata (coverage counts, run IDs, tags) onto LLM output.
- Cross-run merge between two LLM outputs by rank or coverage (structural, not qualitative).
- Refusing to publish output that violates a hard structural invariant (block or downgrade
  with explicit `[STRUCTURAL_GATE]` tag).
- Failing closed when LLM output is malformed or absent.

**Reference incident**: SWI-183 — early plan included `enforce_coverage_cap` and
`enforce_broad_market_exit_gate` Python post-LLM gates calibrated to the 2026-04-28
incident's numeric symptoms. The same gates would have *allowed* attempt 1's wrong
EXIT (all numeric thresholds met) and reliably mis-fire on future borderline cases.
The fix shipped as prompt-level veto-then-confirm structure instead.

## ⚠️ Critical Rules

- **Two-tier tool naming:** `tool_*()` → returns `str` (prose, for LLM agents via registry). `*_async()` → returns `dict` (for Python code needing field access). Never mix.
- **Agent config source of truth: YAML files** at `scripts/agents/configs/{agent_key}.yaml`. Config changes are committed to git — no migration needed. CI syncs files → DB for the web admin read cache.
- **Eval expected values go in `metadata`** — NOT `expected_output`. Pydantic-evals typing constraint.

---

## Agent Config Architecture

All agent config lives in YAML files at `scripts/agents/configs/{agent_key}.yaml`. Each file contains: system prompt, model ID, temperature, max tokens, output retries, model settings. Config is loaded at runtime via `load_agent_config()` — no hardcoded config in agent files.

**Config change flow:** edit the YAML file → commit to git. CI auto-syncs to DB for web admin. No migration needed for prompt/model changes.

**Model resolution priority:**
1. `SWINGY_MODEL_TIER=cheap` → dev override (local cheap model)
2. `EVAL_MODEL_OVERRIDE` → eval A/B comparison runs
3. `config.model_id` → per-agent model from YAML config (source of truth)

To check current model assignments: look at `scripts/agents/configs/*.yaml` or `grep model_id scripts/agents/configs/*.yaml`.

**max_tokens policy:** Keep high (96000) for all agents to avoid early output cutoff. Do NOT right-size per agent — the cost savings are not worth the risk of truncated outputs. Only exception: critic at 20000 (migration 193).

**Model policy (current = `z-ai/glm-5.1`):** Default primary model for ALL non-MiniMax agents is `z-ai/glm-5.1` (verify: `grep model_id scripts/agents/configs/*.yaml` — the live SSOT; `shared/config.py::LLM_MODEL` mirrors it). Fallback model is `minimax/minimax-m2.7`. Two MiniMax-pinned agents (`article_sentiment.yaml`, `news_relevance.yaml`) keep their primary. History: SWI-331 (2026-05-13) swapped fleet `z-ai/glm-5` → `xiaomi/mimo-v2.5` after chronic glm-5 silent-hangs; 2026-05-14 upgraded to the `xiaomi/mimo-v2.5-pro` variant after sector_aggregator silent-hang × 2 on banking_1; then `c5d69301` (2026-05-15) swapped to `z-ai/glm-5.1` — an UNREVIEWED change with no SWI/canary that also re-pinned routing to a single upstream and caused the model-agnostic Signature-B hang cluster (SWI-378). The earlier `2026-04-20 full swap` to glm-5 dropped `zai-org/GLM-4.5-Air-FP8` and `moonshotai/Kimi-K2.5` (Kimi rationale below stays load-bearing for any future model with reasoning-heavy SSE shape). **The model string is NOT the lever for the silent provider hang — that is a routing/retry-layer fix (SWI-369/375/378). Any future fleet swap is a separate, disciplined decision (SWI-370/399) with a canary, not bundled with a routing change.**

---

## Tool Registry (post-SWI-180: native PydanticAI tools + per-agent allowlist)

All agents register **native PydanticAI tools** at `Agent` construction. The broker meta-tools (`call_tools` / `search_tools` / `get_tool_schemas`) and the `ToolBroker` class are **deleted**. Tools follow `{domain}.{verb}_{noun}` naming and live in `scripts/agents/tools/broker/domains/`. Registry is at `scripts/agents/tools/broker/registry.py` (`TOOL_CATALOG`, `register_domain_tool`).

### Core wiring (handled by `agent_factory.create_agent`)

```python
agent = Agent(
    model=...,
    deps_type=AgentDeps,
    output_type=output_type,
    tools=[*build_native_tools(), Tool(unlock_tool, takes_ctx=True)],
    prepare_tools=make_prepare_tools(config.allowed_tools),
    system_prompt=render_catalog(config.allowed_tools) + "\n\n" + config.system_prompt,
)
```

- `build_native_tools()` (cached): one `Tool` per entry in `TOOL_CATALOG`, each wrapped by `_wrap_with_policy` for Logfire telemetry + breakers.
- `make_prepare_tools(allowed)` (cached): per-call `prepare_tools` filter admits `allowed | ctx.deps.unlocked | {"unlock_tool"}`.
- `render_catalog(allowed)` (cached): renders the catalog block prepended to `system_prompt` so the agent sees `tool.name(*REQ: ...; opt: ...)` for every visible tool.

### Run-time contract — `AgentDeps` (NOT `context: dict`)

`AgentDeps` (typed dataclass at `scripts/agents/tools/agent_deps.py`) replaces the legacy `context: dict`. Pass it via `agent.run(prompt, deps=...)`:

```python
deps = AgentDeps(scan_date=scan_date, agent_key=config.agent_key, tickers_in_scope=tickers)
result = await agent.run(prompt, deps=deps)
```

Counters (`iteration_count`, `error_signature_counts`, `unlocked`) live for the lifetime of one `agent.run` and reset at the next `create_agent`.

### Per-agent allowlist (YAML `allowed_tools:`)

Each YAML carries an `allowed_tools:` block. Tools NOT on the allowlist are **invisible** until the agent calls `unlock_tool`. Every entry MUST have an adjacent rationale comment; pre-push hook `check_yaml_allowed_tools.py` enforces both vocabulary parity (each entry ∈ `TOOL_CATALOG`) and rationale presence.

```yaml
allowed_tools:
  - enrichment.get_flow      # rationale: SWI-180 — sector_news depends on flow streaks for catalyst correlation
  - article.search           # rationale: SWI-180 — used >20 calls/week in last-30-day hot-set
```

### `unlock_tool` autonomy escape hatch

Argument-tolerant + idempotent: `unlock_tool(tool_name=None)` returns coaching JSON with `currently_locked` listing. Re-unlocking a tool is free. Visible surface capped at `TOTAL_TOOL_BUDGET = 15` — the budget is `max(1, 15 - len(allowed_tools))` extra unlocks. Exceeding raises `BrokerLoopBreaker(kind="unlock_overuse")`.

### Schema-at-model-boundary (root-cause fix for the 50.4% broker failure rate)

Per-tool JSON Schema reaches the LLM directly — `tickers: list[str]` with `min_length=1` rejects empty-list emissions at the provider boundary instead of crashing inside the dispatcher. **Use the `RequiredTickers` alias** for any ticker-scoped tool:

```python
from agents.tools.types import RequiredTickers  # = Annotated[list[str], Len(min_length=1)]

@register_domain_tool(...)
async def get_valuation(tickers: RequiredTickers, ctx: RunContext[AgentDeps]) -> dict: ...
```

### Two-validator architecture

1. **pydantic-ai (schema-first, model boundary)** — provider rejects malformed emissions; framework retries via `ToolRetryError` / `ModelRetry`.
2. **`pydantic.validate_call(strict=True)`** kept on `register_domain_tool` as defense-in-depth for type-coercion edges (Decimal, datetime). Raises `ValidationError`, observed by `error_hints.classify_validation_error` and surfaced back to the LLM via `ModelRetry`.

### Breakers (all terminal — `RECOVERABLE_BREAKER_KINDS = frozenset()`)

- `iteration_limit` — past `NATIVE_TOOL_INVOCATION_LIMIT = 25` calls in one run.
- `error_signature` — same `{tool_name}:{validation_signature}` repeated past `ERROR_SIGNATURE_RETRY_LIMIT = 2`.
- `unlock_overuse` — exceeds `UNLOCK_BUDGET`.

`BrokerLoopBreaker` subclasses `pydantic_ai.exceptions.UnexpectedModelBehavior`; pipeline call sites that catch it (e.g. `sector_analysts.py`) treat all kinds as terminal.

### Prompt rules (still load-bearing)

1. Primary data MUST be injected into the prompt — reserve tools for in-depth queries.
2. Reference tools by their **dotted name** in prompt prose: `enrichment.get_flow`, `article.search`. The catalog rendered above the system_prompt shows the full signature with REQ markers — do NOT hand-write argument exemplars.
3. Never list bare tool names without the domain prefix (`search`, `get_learnings`) — pre-push T07 regex guards against this.
4. Injected context must reference real, allowlisted tool names (or `unlock_tool` if unlocking is the intent). Stale tool references in injected context were the historical #1 cause of tool-call loops.
5. Verbose output is a **prompting problem** — fix with conciseness rules / `Field(max_length=N)`, never with `output_tokens_limit` caps.

### Telemetry

`broker_tool` Logfire span (preserved name) emits `tool_name`, `agent_key`, `error`, `error_type`, `attempt_index`. `scripts/collect_review_data.py:443-551` `broker_tool_usage` pivot continues to work unchanged.

### Diagnosing tool loops

Always check the model's thinking block in Logfire (`gen_ai.output.messages` → `thinking` part) before concluding "model ignores instructions." Models make reasonable decisions given their inputs; the usual culprit is contradictory context (yaml claims data is pre-loaded but formatter doesn't actually inject it) or a stale tool reference in injected text.

Discover tools: `scripts/agents/tools/broker/domains/`. Re-export entry: `scripts/agents/tools/broker/__init__.py`.

---

## Context Injection vs Tool Calls

**Core principle:** Inject substantial upfront context; reserve tools for interactive deep-dives. LLMs spend reasoning tokens on analysis, not data retrieval.

### Decision Framework

| INJECT into system prompt | KEEP as tool call |
|---------------------------|-------------------|
| Static/shared per-run (holdings, cash, regime, technicals) | Agent decides what/when to query (search, selective reads) |
| Needed on turn 1 — agent can't reason without it | Needed conditionally based on prior reasoning |
| Same data used by 3+ agents | Agent-specific one-off lookups |
| Pre-computed summaries and judgments | Raw data needing filtering |
| ≤5K tokens per data block | Large datasets (>5K tokens) |
| Read-only reference data | Write operations (alerts, DB updates) |

### Quantitative Constraints (Research-Backed)

| Constraint | Target |
|------------|--------|
| Total injected context per agent | **≤7K tokens** (degradation starts at 7K — arXiv:2510.05381) |
| Tool definitions per agent | **≤15** (~500 tokens each; fewer = better accuracy) |
| Sub-agent output size | **≤2K tokens** (Anthropic multi-agent research) |
| Redundant data fetches | **0** (AgentDiet: removing 40-60% redundant tokens *improved* accuracy) |

### Prompt Structure (Attention-Optimized)

Models attend most to beginning and end of context ("Lost in the Middle", TACL 2024). Structure system prompts:

```
[BEGINNING — highest attention]
  Role + methodology + constraints
  Market regime summary (1 paragraph)
  Portfolio state (holdings, cash, trading mode)

[MIDDLE — lower attention, OK for reference lookups]
  Pre-computed data tables (technicals, flow, valuations)
  Upstream agent outputs (condensed summaries)

[END — high attention]
  Current ticker/sector briefing being analyzed
  Specific task instructions + output format
```

**Injected context format:** Use compact structured text (pipe-delimited key-value blocks), not prose. Prose wastes ~3x tokens. Rule of thumb: data consumed as *facts to reference* → structured; data consumed as *reasoning to integrate* → prose.

**Implementation:** Use `RunContext[PipelineContext]` dependency injection. Build context blocks in Python via dedicated formatters, inject via `@agent.system_prompt`.

**Full reference:** what-to-inject tables, what-stays-as-tools list, formatter code examples, token budgets per block, and research citations → `references/context-injection.md`

### Pipeline Constraints (R:R + Entry Count)

Constraint computation is centralized in `shared/rules/constraints.py`. The `PipelineConstraints` TypedDict flows from a single `compute_pipeline_constraints()` call to all enforcement gates (picks, validator, strategy_director, display).

**Key rule:** Never read goal urgency directly in enforcement code — always use the composed constraints dict. Direct reads bypass retro overrides and circuit breakers.

**Full reference:** sources, composition pipeline, urgency tiers, enforcement gates, anti-death-spiral logic, pitfalls → `references/constraint-handbook.md`

---

## Creating New Agents

1. Create `scripts/agents/configs/{agent_key}.yaml` with `system_prompt`, `model_id`, and (if any tools needed) an `allowed_tools:` block — each entry on its own line with a `# rationale: SWI-NN — ...` comment.
2. Create the agent file using `load_agent_config()` + `create_agent()`. Declare a Pydantic output type for structured output validation.
3. At call time, build `AgentDeps(scan_date=..., agent_key=AGENT_KEY, tickers_in_scope=...)` and pass via `agent.run(prompt, deps=deps)`.
4. Commit the YAML file — CI syncs to DB for web admin visibility.

If the agent needs a tool that is not yet on the allowlist for any agent, register it via `register_domain_tool` in `scripts/agents/tools/broker/domains/` first. For ticker-scoped tools use `tickers: RequiredTickers` (from `agents.tools.types`).

Explore existing agents in `scripts/agents/` before creating a new one — reuse patterns.

---

## Degrees of Freedom Calibration

**The core question:** how much creative latitude should this agent have?

| Tight (low freedom) | Loose (high freedom) |
|----------------------|----------------------|
| Numerical extraction | Synthesis narrative |
| Alert registration | Retrospective summary |
| Position sizing decisions | News analysis |
| Structured field parsing | Watchlist commentary |
| Signal classification (BUY/WATCH/WAIT/AVOID) | Thesis narrative |

**Rule:** If agent output feeds deterministic downstream code (parsers, position sizers, alert registrations) → tight prompt with strict schema, `Literal` types, few-shot constraint examples.

If output is human-facing only (narrative brief, commentary, explanation) → loose prompt that values synthesis quality over parseable precision.

**Anti-pattern:** Using tight schema constraints on synthesis agents kills narrative quality. Using loose prompts on parsers produces unparseable output that crashes downstream code.

---

## Eval Framework Design Principles

- Tools are mocked at agent level — return input data directly, no API calls during evals
- Agent config loaded from DB via `load_prompt()` / `load_config()` in `evals/helpers.py`
- Expected values live in `metadata` dict alongside the dataset case (not in `expected_output`)
- `EVAL_MODEL_OVERRIDE` env var for A/B model comparison runs
- Default to cheap models (`SWINGY_MODEL_TIER=cheap`) for all eval runs to minimize cost

Discover directory structure, runner scripts, dataset format, and evaluator patterns by exploring `evals/`.

For ad-hoc scoring without running the full pipeline (`score_tickers.py` replay/fresh modes, hypothetical-weight comparison), see `references/score-tickers.md`.

---

## Belief System

The `agent_beliefs` table records directional conviction from each agent per ticker per run.

**Schema key fields:**
- `ticker`, `scan_date`, `source_agent` — identity
- `direction` — `BULLISH | BEARISH | NEUTRAL`
- `conviction` — `HIGH | MEDIUM | LOW`
- `bull_probability`, `bear_probability`, `base_probability` — decimal (0-1)
- `belief_status` — lifecycle: `ACTIVE → RESOLVED | EXPIRED | SUPERSEDED`
- `horizon_date` — when the belief should be evaluated against reality

**Belief aggregation (weighted scoring):**
- Aggregate across source agents using conviction weights: HIGH=3, MEDIUM=2, LOW=1
- Direction derived deterministically from probabilities: `argmax(bull, bear, base)` → direction
- NEUTRAL tiebreak when bull == bear (never let LLM choose direction — Rule 9)
- Zero-conviction fallback: if no active beliefs for a ticker, output `{"direction": "NEUTRAL", "conviction": "LOW"}` — never omit the `direction` key

**Brier scoring:**
- `brier_score = (predicted_probability - outcome)²` where outcome is 1 (correct) or 0 (wrong)
- Lower is better (0 = perfect, 1 = worst). Stored in `agent_belief_outcomes` after horizon passes.
- Used to calibrate per-agent conviction weights over time.

**Common bugs:**
- **Lazy NEUTRAL:** LLM outputs NEUTRAL when data is thin rather than reasoning through signals. Force explicit bull/bear case in prompt — NEUTRAL requires stated reasoning.
- **Missing `direction` key:** Zero-conviction fallback must always include `"direction": "NEUTRAL"`. Missing key causes KeyError downstream.
- **Orphaned chains:** Beliefs with `belief_status = ACTIVE` past their `horizon_date` create stale signal noise. Retro pipeline resolves these; check for stragglers with `WHERE belief_status = 'ACTIVE' AND horizon_date < NOW()`.
- **Probability/direction mismatch:** LLM labels direction BEARISH but `bull_probability` is highest. `_normalize_belief_probabilities` auto-corrects via `derive_direction_from_probabilities()` — direction must be deterministic (Rule 9).
- **LLM outputs probabilities as percentages:** Aggregator prompt showing `45%` causes LLM to output `bull_probability=45` instead of `0.45`. Show decimals in prompt text; normalizer rescues sum 50-150 inputs by dividing by 100.

---

## Gotchas

- **All `tool_*` functions MUST be `async def` with `await`.** NEVER use `asyncio.run()` inside tool functions — causes `ConnectionDoesNotExistError` in running pipelines. The event loop is already running; nested `asyncio.run()` is illegal.
- **Log before silent returns in except blocks.** `except` blocks that return stubs (`[]`, `""`, `None`) or `continue` MUST `logger.warning(f"context: {e}")` first. Silent swallows hide systematic failures (API down, schema change) that make agents produce garbage with no signal.
- **Numpy types in tool returns cause silent agent death.** Any tool returning data from pandas/numpy MUST cast to native Python types (`float()`, `int()`, `bool()`). Numpy types cause `PydanticSerializationError` that silently kills the agent with no useful error message.
- **Tools are gated by the per-agent `allowed_tools:` allowlist (post-SWI-180).** Agents only see tools on their allowlist plus `unlock_tool`. To admit a non-allowlisted tool at run time, the agent calls `unlock_tool(tool_name="<dotted-name>")`. Hybrid agents (like `catalysts.py`) may still register module-specific inline tools directly via `agent.tool` — those bypass the allowlist by design.
- **OpenRouter session tracking via `extra_body`.** `agent_factory.py` automatically injects `session_id` + `trace` metadata into `ModelSettings.extra_body` via `shared.session.get_extra_body()`. This groups all LLM calls in a pipeline run. If adding a new LLM call path outside the agent factory, call `get_extra_body(agent_name="your_caller")` and pass it as `extra_body`. Session must be initialized with `init_session()` at pipeline entry point.
- **Agent config lives in YAML files.** The source of truth is `scripts/agents/configs/{agent_key}.yaml`. Edit the YAML file and commit. CI syncs to DB for web admin. No migration needed for prompt/model changes.
- **Stale tool references in injected context cause tool-call loops.** Post-SWI-180 the broker meta-tools (`search_tools`/`get_tool_schemas`/`call_tools`) no longer exist, but the loop pattern survives via `unlock_tool` overuse if injected context names a tool that isn't on the allowlist or doesn't exist. Fix: (1) reference tools by their dotted name only (`article.search`, `enrichment.get_flow`) — the rendered catalog above the system_prompt shows the signature; (2) audit injected context for stale tool name references whenever you change the formatter. Never use "DO NOT call X" as the fix — it doesn't work. Check the model's thinking block (`gen_ai.output.messages`) to find what actually triggered the decision.
- **Always set `model_id` explicitly in YAML configs.** NULL `model_id` causes full pipeline failure. Use the current fleet default (`z-ai/glm-5.1` as of 2026-05-30 — see Model policy above). 7 agents with NULL model_id caused synthesis failure (2026-03-13).
- **MiniMax M2.7 fails on nested Pydantic structured output.** Schemas with 3+ nesting levels (e.g., `SectorAnalystReport` → `TickerBelief` 12 fields, `CatalystDiscovery` → 3 nested types) cause retry storms. Keep MiniMax for flat classifiers only (`news_examiner`, `capital_events`). Complex schemas need Kimi-K2.5. Hit 2026-04-06: sector_news 10 retries exhausting request_limit=30. Fixed by migration 289. See also: open-key-dict failure mode below.
- **Open-key dicts in structured output break across providers.** `dict[str, X]` on agent `output_type` fields fails on MiniMax M2.7 (2026-04-06, sector_news) AND z-ai/glm-5 (2026-05-06, synthesis_holdings). Tool-call argument encoders treat `additionalProperties` as ambiguous and default to `{}` even when the model drafts the content correctly in `<thinking>` blocks. Always model agent outputs as `list[NamedItemModel]` with an explicit identity field (`ticker`, `id`, …). Bridge to dict-shape *after* the LLM, in Python (sibling: `SectorAnalystReport.views: list[SectorAnalystView]`).
- **Belief direction is LLM-chosen and can mismatch probabilities.** `_normalize_belief_probabilities` now auto-corrects direction via `derive_direction_from_probabilities()` (argmax + NEUTRAL tiebreak). Hit 2026-03-24: VPB sector_aggregator labeled BEARISH but base_probability (0.43) > bear (0.29). Direction should be deterministic (Rule 9), not LLM-determined.
- **LLM outputs probabilities as percentages, not decimals.** When sub-agent beliefs are formatted as "45%" in aggregator prompt text (via `:.0%` format spec), the aggregator LLM mirrors the format and outputs `bull_probability=45` instead of `0.45`. The Pydantic model_validator normalizer sees sum=100 > 1.5 and silently falls back to base rates. Fix: (1) show decimals in prompt text (`:.2f`), (2) add `Field(description=...)` specifying decimal format, (3) normalizer rescues percentage-scale inputs (sum 50-150 → divide by 100). Hit 2026-03-23: 30/30 aggregator beliefs had identical base rate probabilities.
- **DB enum parity with Python allowlists.** Python-side status allowlists (e.g., `_normalize_action` in `insert_records.py`) must match the DB enum exactly. Adding a new status (like "FAILED") to Python without a DB enum migration causes silent reversion to the default. Always update both. Hit 2026-03-27: evaluator set status="FAILED" but insert_records silently reverted to "PENDING".
- **Pydantic models must match compute output types.** If `compute_day_summary()` returns `entry_hit_rate: None`, the Pydantic model must use `float | None = None`, not `float`. Mismatches cause either validation errors or masked semantic differences (0.0 vs None). Hit 2026-03-27: `DaySummary.entry_hit_rate: float` didn't match nullable compute output.
- **Unbounded string fields on output schemas cause runaway generation.** Any `str` field without `Field(max_length=N)` lets the model write unbounded text. For heterogeneous sector groups (mixed industries, no shared themes), the model can't compress and writes exhaustive per-ticker essays until hitting `max_tokens` ceiling. Always add `max_length` to `str` fields on structured output models. Hit 2026-04-06: sector_aggregator produced 96K output tokens (876s) for mixed sector because `belief_narrative`, `note`, `summary` were unbounded.
- **`max_tokens=96000` is a ceiling, not a guardrail.** Per policy: never right-size per agent, never use `output_tokens_limit` to cap output. Fix unbounded generation at schema level (`Field(max_length=N)`) and prompt level (conciseness constraints), not token caps.
- **`UsageLimits` fields:** `request_limit`, `tool_calls_limit`, `input_tokens_limit`, `output_tokens_limit`, `total_tokens_limit`, `count_tokens_before_request`. There is NO `response_tokens_limit` — using it causes `TypeError` at runtime (dataclass `kw_only=True`).
- **Belief scoring starvation from `max_age_days`.** `resolve_mature_beliefs(max_age_days=15)` permanently excludes beliefs older than 15 days from scoring. If belief `timeframe_days` approaches `max_age_days`, the scoring window is too narrow. This starved the calibration system — no agent reached 30 scored beliefs needed for down-weighting. Hit 2026-04-06: all agents had Brier > 0.5 (worse than random) because only 6 of 162 beliefs were scored.
- **`get_all_belief_accuracy(days_back=30)` has a dead parameter.** The `days_back` arg is accepted but never used in the SQL query. The view `v_agent_belief_accuracy` has its own hardcoded lookback.
- **Base rate anchoring + direction derivation interact.** Halving anchor weight (0.2→0.1, `771a944`) compressed probabilities into the tiebreak zone (0.05, `dd17c50`), causing 46% aggregator disagreement. When modifying one, always re-verify the other. As of 2026-04-06, tiebreak replaced with `MIN_DIRECTIONAL_PROBABILITY=0.40` gate.
- **Display-side injection ≠ aggregation/sizing path.** `context_blocks_ticker.py` only affects what agents SEE in "YOUR PRIOR". `weighted_aggregate_beliefs()` and `extract_top_picks()` read conviction from DB. Staleness decay or accuracy metadata must be applied in BOTH display AND aggregation/sizing to have full effect.
- **Injection drift: the yaml lies about what's pre-injected.** Second-biggest cause of tool-call loops after stale tool names. Symptom: agent's system prompt says "per-ticker briefings include catalysts, articles, sector context" but `context_blocks_ticker.format_ticker_briefing()` only renders technicals/flow/insider/RS/beliefs/profile. Agent reads the promise, can't find the data, and compensates with `call_tools` fan-out. Fix: when editing an agent yaml's "data available" section, grep `context_blocks_ticker.py` / `context_blocks*.py` to verify every claim matches an actual injected field. Never add prose saying "X is pre-loaded" without also wiring X into the formatter. (2026-04-12 positions_thesis fix added articles/narratives/longterm injection + switched `_fetch_articles` to `list_articles_range` for the richer payload.)
- **Kimi-K2.5 reasoning streams stall under concurrency.** Kimi emits 1000-1500 reasoning chunks + 200-275 content chunks per response (80-95% reasoning). Under `asyncio.gather` of 2+ Kimi streams, PydanticAI's per-chunk `_map_thinking_delta` → `parts_manager.handle_thinking_delta` saturates the event loop; one stream's httpx reader starves, gaps spike to 10-15s (never tripping httpx's per-chunk 60s read timeout), and the outer `asyncio.wait_for(180s)` wall hits. `FallbackModel` cannot save it — stalls are not exceptions at stream-open time. Local repro: `scripts/debug/reproduce_positions_hang.py` shows 30-60% hang rate on parallel Kimi, 0% hang on serial Kimi, 0% hang on parallel GLM-5. Symptom in prod: `positions_value`/`positions_thesis` or any concurrent sector analyst pair hits the 180/240s outer wall with no fallback rollover. Fix: use GLM-5 primary for concurrent hot-path agents (see Model policy exception above). (2026-04-20 GH run 24647108805 → root cause + fix.) **CAVEAT (SWI-378, 2026-05-30):** "0% hang on parallel GLM-5" is one narrow Signature-A (concurrency stream-stall) datapoint, NOT evidence that any model is hang-immune. GLM-5.1 went on to hang in production via Signature-B (first-byte/mid-stream upstream hang), which is model-agnostic — it hit glm, kimi, AND xiaomi alike. The lever for Signature-B is the OpenRouter routing/retry layer (unpin + throughput-sort + client `max_retries=0`, SWI-369/375/378), not the model string. Do not cite this line to justify a fleet model choice.
- **Composite + atomic tool directives in the same YAML provoke tool-call loops.** Hit 2026-04-24: `positions_value.yaml` said "prefer fundamental.get_full_analysis" AND "Batch-call fundamental.get_valuation_history / fundamental.get_earnings_quality". GLM-5 oscillated → 30 batches → `UsageLimitExceeded` → empty `AnalystReport` → hard-failed run. Rule: when a composite tool exists (annotated via `register_domain_tool(..., supersedes=(...))`), rewrite atomic directives to "read the `=== SECTION ===` of the composite response" instead. Pre-commit hook `check_agent_yaml_composite_vs_atomic.py` enforces this. Companion hook `check_agent_yaml_injection_coherence.py` blocks the related "data is pre-loaded" + imperative "Start from tool" contradiction. Every `model_id:` change should run `uv run pytest scripts/agents/evals/test_request_count_ceiling.py` first — a loop under a new model surfaces there instead of in production.
- **Tool params: use `Literal`, `TypedDict`, and `RequiredTickers`, not `str` with docstring enums.** `_resolve_type_schema` in `scripts/agents/tools/broker/registry.py` understands `Literal[...]`, `TypedDict`, nested `list[TypedDict]`, and `Annotated[list[str], Len(min_length=1)]`, producing JSON Schema `enum` + `minItems` constraints the LLM sees at the model boundary. Writing `query: str  # "summary" | "winning_patterns" | ...` loses both compile-time and schema-time enforcement. Prefer a module-level `Query = Literal["summary", "winning_patterns", ...]` alias. For ticker-scoped tools use the project alias `from agents.tools.types import RequiredTickers` — empty-list emissions then reject at the provider boundary instead of crashing inside the dispatcher (root-cause fix for the SWI-180 50.4% broker failure rate).
- **`BrokerLoopBreaker` kinds are all terminal.** `RECOVERABLE_BREAKER_KINDS = frozenset()` — when `iteration_limit`, `error_signature`, or `unlock_overuse` fires, the agent run is over. Pipeline call sites (e.g. `sector_analysts.py`) catch and surface as terminal failures. Don't add a "retry kind" without auditing every call site.
- **`AgentDeps` field set is the source of truth for run-time data.** Adding a new piece of data the tools/agents need = add a field to `agent_deps.py:AgentDeps`. The legacy `from_legacy_context` + `deps_to_ctx_dict` shim still bridges to `domains/*.py` impls that read `_ctx.get(...)`. Remove that bridge only after migrating signatures to `RunContext[AgentDeps]` directly.

---

## Related Skills

| Skill | Load when... |
|-------|-------------|
| `database` | Schema changes to non-agent tables (agent config is in YAML files, not DB) |
| `finance-prompting` | Writing or improving an agent's system prompt for financial analysis tasks |
| `pipeline-workflows` | Understanding where and when a specific agent runs in the pipeline |
| `unit-test` | Writing tests for agent tools or parsing agent output types |
| `data-layer` | Understanding which data tier an agent tool reads from |
