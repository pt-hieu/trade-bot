# Swing Trading Analysis Pipeline

Short-term swing trading analysis for Vietnamese stocks, feeding a long-term portfolio.
Config lives in the `trading_config` table. All trading data is in PostgreSQL.

**Gotcha maintenance:** Add new pitfalls to the relevant skill's `instructions.md` `## Gotchas` section.

## Git Workflow

- **Develop on `main` directly.** Small team, commit straight to main.
- **Commit subject references the tracker ticket.** For multi-issue commits, list every id (`SWI-42 SWI-51 ...`).

## Production Safety

- Require `SWINGY_ENV=production` for production.
- **Schema changes go through migrations only**. See `database` skill.
- **DDL uses the owner connection** — default `DATABASE_URL` is read-only

## Python

- **Inline script path:** `uv run python -c "..."` needs `sys.path.insert(0, 'scripts')`
- **Async discipline** — `tool_*` = `async def` + `await`. Reserve `*_sync()` for standalone CLI scripts that run to completion before any async pipeline starts (avoids pool destruction).

## Agent Architecture

- **Inject shared data, fetch once** — batch-fetch in Phase 0 and inject as compact text into system prompts. Reserve tools for in-depth queries where an agent needs additional data to decide. Each piece of shared data has exactly one fetcher.
- **Inject-first, native tools, per-agent allowlist** (SWI-180, post-cutover) — all agents get native PydanticAI tools via `Agent(deps_type=AgentDeps, tools=[*build_native_tools(), Tool(unlock_tool)], prepare_tools=...)`. Each YAML carries `allowed_tools: [<dotted-name>, ...]` filtered through `prepare_tools`; tools NOT on the allowlist are admitted at run time only via `unlock_tool(tool_name="<name>")`. Tickers-required tools use `RequiredTickers = Annotated[list[str], Len(min_length=1)]` so empty-list emissions reject at the model boundary. Pass run-time data via `agent.run(prompt, deps=AgentDeps(scan_date=..., tickers_in_scope=..., ...))`.
- **Per-agent autonomy via unlock_tool** — agents do not see all 45 broker tools by default. The default surface is `allowed_tools | {unlock_tool}`. To preserve autonomy when an agent identifies a real data gap, it calls `unlock_tool(tool_name="<dotted-name>")` to admit a non-allowlisted tool for the rest of its run. `unlock_tool` is argument-tolerant (calling with no args returns coaching JSON) and idempotent (re-unlocking is free). Total visible surface is capped at `TOTAL_TOOL_BUDGET = 15`. Update `allowed_tools:` with a `# rationale: SWI-NN — ...` comment when usage justifies it; the `check_yaml_allowed_tools.py` pre-push hook flags drift.
- **Positive-only agent prompts** — LLMs follow the most specific instruction near the data they're looking at, so positive phrasing near the payload wins. Keep injected context aligned with live tool names and reference tools by their dotted name (e.g., `enrichment.get_flow`); the catalog rendered above the system_prompt by `render_catalog(allowed_tools)` shows the available signature.
- **Verbose output = prompting problem** — fix via prompt instructions (output length rules, conciseness constraints, sentence/field/shape caps). Schema caps like `Field(max_length=N)` or `output_tokens_limit` mask the real issue and degrade output quality.
- **Context budgets** — ≤7K tokens injected/agent, ≤2K tokens/sub-agent return, ≤15 tool defs. Critical data at beginning + end, reference tables in middle.
- **Python / LLM split** — Python owns structural invariants, arithmetic, cross-run merge; LLM owns qualitative verdicts (EXIT/HOLD, sentiment, conflict resolution). Never add a Python post-LLM gate that downgrades a qualitative LLM action — fix the prompt instead. Full rule in `agent-development` skill.

### Agent Config

| Setting | Value | Note |
|---------|-------|------|
| max_tokens | 96000 | |
| default model | pinned in all `scripts/agents/configs/*.yaml` (parity enforced by `check_agent_yaml_model_parity`); `shared/config.py::LLM_MODEL` is the Python fallback | |
| request_limit | 30 | Built via `shared.agent_config.build_usage_limits(config)`; override per-agent with `request_limit:` in YAML |
| output_retries | 2 | Structured output parsing retry |
| Pipeline timeout | morning: 7200s, midday+retro: 3600s | Per-phase: 300s |
| GH Actions timeout | daily-scan: 150min, midday/retro: 75min | Must exceed pipeline timeout + setup |

## Code Quality

- **Fail loudly, log with context** — errors include agent name, input, step. `except` blocks returning stubs `logger.warning()` first. Every error path surfaces the failure.
- **Replace directly, delete dead code.** Consumers update atomically with the replacement.
- **None-safe dict access** — `r.get("key") or default` (guards both missing key and NULL column value).
- **Cast numpy types to native Python** in tool returns (prevents `PydanticSerializationError`).
- **VND conventions** — prices as VND integers, display % as whole numbers, rates as 0-1 decimals.
- **Typed signatures** — use specific types, TypedDicts, `Union`, `Protocol`, or `object`. When a function accepts multiple TypedDicts, use a `Union` or protocol. Keep `Any` out so pyright stays effective.

## Pipeline Type Safety

- **Typed intermediates** — inter-phase data uses dataclass/TypedDict in `pipeline/types.py`. New phase boundaries add a type definition.
- **Single derivation path** — when live + resume paths derive the same state, extract a shared function and call it from both paths.

## Pipeline Decision Rules

- **Centralized rules in `shared/rules/`** — Single source of truth for all critical logic.

## Pipeline Resilience

- **Fail-closed defaults** — missing data maps to the MOST CONSERVATIVE value.
- **Dict key contracts via types** — structured dicts use TypedDict/dataclass; producers and consumers agree on key names via the shared type.

## Linear-Backed Observability (MANDATORY)

All stateful tracking — features, decisions, regression-watch, scheduled-work, audit-finding, bug, quality-gap — lives in **Linear team Swingy**. Canonical handle is `SWI-NN`. Load the **`linear` skill** for the protocol, label taxonomy, workflow states, fenced-JSON contract, and ad-hoc filing recipes; it is a mandatory prerequisite for `/pipeline-review` and `/audit` and auto-loads on any non-trivial coding session. Two glue scripts live at the seam: `scripts/export_issues.py` (pre-review export) and `scripts/process_review_findings.py` (post-review write-back). Pair Linear with `git log --grep=SWI-NN` — together they are the only persistent context across sessions.
