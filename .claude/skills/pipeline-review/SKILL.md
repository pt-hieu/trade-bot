---
name: pipeline-review
description: Review PydanticAI agent pipeline runs for inputs/config, reasoning/output, and resilience/integration. Uses shared data fetch layer + 3 parallel review subagents.
---

# Pipeline Review

Systematic review of agent pipeline runs using Logfire traces and Neon DB. Fetches all trace data upfront, then fires 3 parallel subagents to analyze merged quality dimensions.

## When to Use

Activate when the user:
- Says "review pipelines" or "review today's runs"
- Asks "how did the morning brief go?" or "check pipeline health"
- Wants to audit agent quality, reasoning, or data integration
- Says "pipeline review" or "review agent runs"
- Reports unexpected recommendations or pipeline failures
- Asks to check cross-pipeline consistency (morning vs midday vs retro)

## Output Format

- Overview: pipelines reviewed, duration, tokens, trace links
- 3 dimension findings (Inputs & Config, Reasoning & Output, Resilience & Integration)
- Severity-ranked issues (CRITICAL / WARNING / INFO)
- Actionable recommendations

## Key Architecture

**Three-phase execution:**
1. **Shared Data Fetch** — Claude Code queries Logfire (3-5 queries max) + Neon DB to build dataset
2. **3 Parallel Subagents** — each analyzes pre-fetched data for two merged quality dimensions (zero additional Logfire queries)
3. **Aggregation** — combine findings into severity-ranked report

**Thinking-first when judging agent behavior.** Reasoning, output, and tool-loop
findings must read the agent's thinking from `logfire_spans.json` before assigning
severity. Artifact-only findings describe symptoms; thinking-grounded findings
explain the cause and route the fix to the right layer (prompt, injected context,
persistence schema, or model). Path: `attributes."pydantic_ai.all_messages"` on
`agent run` spans; `attributes."gen_ai.output.messages"` on `chat` spans.
`gen_ai.response.text` is empty — do not rely on it.

**Prerequisite skills:** `linear`, `logfire-traces`, `agent-development`, `pipeline-workflows`

## Instructions
See `instructions.md` for full methodology.
