---
name: audit
description: Audit a specific pipeline component's output quality and its downstream influence on LLM agent reasoning. Answers "is this component helping or poisoning downstream agents?" Persists findings as a Linear audit-finding issue (team Swingy, category label=audit-finding) with auto-promoted regression-watch and scheduled-work children linked via blockedBy.
---

# Component Audit

Targeted investigation of a pipeline component — its output quality AND how downstream LLM agents absorb, amplify, or get poisoned by it.

## When to Use

Activate when the user:
- Says "audit [component]" (e.g., "audit narrative", "audit regime", "audit beliefs")
- Asks "is [component] working well?" or "how does [component] affect the agents?"
- Wants to trace reasoning quality from a specific upstream source
- Asks "why are recommendations bad?" and suspects a specific component

## Output Format

- Component quality scorecard (6 dimensions, 1-10 scores)
- Downstream impact matrix (per consumer: absorption, amplification, contradictions, error propagation, fidelity)
- Best/worst examples with date + excerpts
- Actionable recommendations
- Interactive drill-down offered after report

## Key Architecture

**Five-phase execution:**
1. **Data Collection** — Neon MCP (DB outputs) + Logfire (traces) + codebase grep (current consumers), all in parallel
2. **2 Parallel Opus Subagents** — Component Quality Auditor (skeptical auditor) + Downstream Impact Auditor (thorough investigator)
3. **Aggregation** — structured report + interactive drill-down
4. **Persist via `linear` skill** — orchestrator runs `scripts/process_review_findings.py --source-kind audit` against the aggregated report. The fenced JSON block follows the `linear` skill's contract (Pydantic `extra="forbid"`); the audit-specific section structure (`## Audit summary`, `## Scorecard`, `## Downstream impact`, `## Findings`, `## Recommendations`, `## Examples`) is documented in Step 5 of `instructions.md`.
5. **Promote children + link via `blockedBy`** — see Step 5 of `instructions.md` for the audit-specific child-promotion rules. The `linear` skill owns the underlying category/severity/state semantics.

**Prerequisite skills:** `linear`, `pipeline-workflows`, `agent-development`, `logfire-traces`, `pipeline-review`

## Instructions
See `instructions.md` for full methodology.
