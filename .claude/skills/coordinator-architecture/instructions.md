# Coordinator Architecture

## 3-Layer Query Routing

The coordinator uses three modes to handle queries, chosen by complexity:

| Layer | Tools | When | Cost |
|-------|-------|------|------|
| **Direct** | `call_tool` | Single data lookup: "show portfolio", "cash balance?" | 1 tool call |
| **Skilled** | `load_skill` + `call_tool` chain | Domain analysis needing interpretation: "how's the market?" | 2-4 tool calls |
| **Delegation** | `ask_*` sub-agents | Complex multi-tool synthesis: "should I enter FPT?" | Sub-agent LLM call |

### Decision rule
- Single tool call answers the question → `call_tool` directly
- Need domain expertise to interpret data → `load_skill` then `call_tool` chain
- Multi-tool synthesis, R:R calculation, deep research → delegate to sub-agent

## Tool Broker Pattern

3 meta-tools that abstract 34+ leaf tools behind a registry:

- `list_tools(category?)` — discover tools by domain (portfolio, market, watchlist, research, strategy, pipeline)
- `get_tool_schema(name)` — get JSON schema for a tool's input parameters
- `call_tool(name, args)` — execute any leaf tool, handles `render:true` → data part push

**Why not expose all tools directly?** Too many tools (34+) confuses the model, degrading tool selection quality. Broker keeps coordinator at 6 tools total.

## Skills System

Domain expertise delivered as **tool output text** (not system prompt injection).

### Why tool output, not prepareStep system injection?
**Prompt caching.** Together.ai uses automatic prefix caching. Cache hierarchy: `tools → system → messages`. Changing system prompt between steps invalidates the prefix cache. Delivering skills as tool output keeps system prompt static = full cache hits across all steps.

| Approach | Cache impact |
|----------|-------------|
| Static system prompt (current) | Best — full prefix cache hits |
| `load_skill` as tool output | Same as static — system prompt unchanged |
| `prepareStep` system injection | Breaks cache every time system changes |
| Auto-inject heuristic | Worst — system changes every step |

### Skill structure
Skills live in `web/src/lib/chat/skills/`. Each is a `.ts` file exporting a string constant with domain expertise text extracted from sub-agent system prompts.

Registry in `web/src/lib/chat/skills/index.ts` maps skill names to content strings.

## Delegation (Sub-Agents)

Only keep sub-agents for tasks that:
1. Need their own context window (long tool chains would pollute coordinator context)
2. Need their own step budget (coordinator step limit is shared)
3. Have complex mandatory tool chains (e.g., strategy's get_technicals → compute_trade_setup)

### Current sub-agents kept
- **Research Analyst** — 109-line prompt, dual-source routing (VN DB vs web search), valuation history, earnings quality, BDS-specific rules
- **Strategy Advisor** — mandatory tool chain, R:R calculation, pattern matching, rule-based conflict resolution

### Converted to skills (no longer sub-agents)
- Portfolio Analyst → `portfolio` skill
- Market Analyst → `market` skill
- Watchlist Scout → `watchlist` skill
- Pipeline Reporter → `pipeline` skill

## AI SDK Mechanisms Reference

For future reference, AI SDK provides these dynamic configuration options:

| Mechanism | What it does | Cache impact |
|-----------|-------------|--------------|
| `prepareCall` | Modify settings once before agent loop starts | No cache impact (runs once) |
| `prepareStep` | Override system/activeTools/model per step based on prior tool results | Breaks cache if system changes |
| `wrapLanguageModel` middleware | Stateless transform of every LLM call | Depends on what's transformed |
| Tool output | Return text as tool result | No cache impact |

## Key Files

- `web/src/lib/chat/tools/broker.ts` — tool broker (list_tools, get_tool_schema, call_tool, load_skill)
- `web/src/lib/chat/skills/` — domain expertise text files
- `web/src/lib/chat/agents/coordinator.ts` — coordinator tool wiring
- `web/src/lib/chat/agents/sub-agents.ts` — sub-agent factories (research, strategy only)
- `web/src/lib/chat/agents/system-prompts.ts` — coordinator + sub-agent prompts
- `web/src/routes/api/chat.ts` — streamText config, step limits

## Constraints

- **Step limit:** `stopWhen: stepCountIs(8)` — coordinator gets 8 steps for skilled queries (load_skill + multiple call_tool + synthesis)
- **Tool count:** Keep coordinator at ≤7 tools. More tools = worse selection quality.
- **Skill size:** Keep each skill under ~50 lines. Longer skills should stay as sub-agents (own context window).

---

## Gotchas

- **Routing layer debugging**: when a query lands in the wrong layer (e.g., Direct when it should be Skilled), check coordinator system prompt's routing heuristics first — the model uses prompt guidance, not hardcoded rules
- **Skill not loading**: if `load_skill` returns empty, check the registry in `web/src/lib/chat/skills/index.ts` — skill name must match exactly (case-sensitive)
- **Sub-agent step budget bleed**: sub-agents share nothing with coordinator's step counter, but each sub-agent call counts as 1 coordinator step — avoid chains of sub-agent calls
- **Cache invalidation**: any change to `tools` array in `streamText` config breaks prefix cache for ALL downstream calls — minimize tool list churn

---

## Related Skills

| Skill | Load when... |
|-------|-------------|
| `web-development` | Web app lives in `web/` directory — modify chat routes, server functions, or app structure |
| `agent-development` | Tool count constraints (≤15 tools per agent), tool schema design, tool calling accuracy |
