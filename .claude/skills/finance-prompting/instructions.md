# Finance Prompting Reference

Research synthesis from 20+ papers and industry sources on effective LLM prompting for financial analysis and trading systems.

---

## Quality Checklist (Severity Tiers)

### CRITICAL — block if missing
- **Deterministic split** — Python computes all numbers; LLM interprets only
- **Structured output** — Pydantic schema with `Literal`/`Enum` for constrained fields
- **Abstinence rule** — `INSUFFICIENT DATA` output when data is missing or unverifiable
- **Conflict detection** — explicit protocol to enumerate and resolve contradictory signals

### IMPORTANT — degrades quality without
- **Specific role** — expert role with domain + methodology, not generic "you are helpful"
- **Few-shot examples** — 2-4 `<good_example>` / `<bad_example>` blocks with `<reasoning>`
- **Confidence calibration** — per-dimension confidence, not single vague score
- **Bull/bear balance** — always require counter-argument to prevent systematic bullish bias

### NICE-TO-HAVE — improves polish
- **Data citation** — each claim cites which tool/field it came from
- **Output constraints** — length limits + structured format = fewer speculative statements

---

## Core Architecture Principle

**Separate computation from reasoning.** Single highest-impact technique (MIT thesis: tool learning achieves 100% accuracy in financial queries).

```
Python layer:  All arithmetic, lookups, thresholds, ratios, scores
LLM layer:     Qualitative judgment, narrative, recommendations, synthesis

Flow: Raw Data → Python (compute R:R, ratios, scores, deltas) → Structured Context → LLM (interpret)
```

**Swingy alignment:** Implemented via deterministic pre-computation of trade setup, position sizing, trading mode, and market regime. LLM agents receive pre-computed values — never compute numbers.

### Context Delivery

For context injection implementation, token budgets, what-to-inject tables, and formatter patterns, see the `agent-development` skill (Context Injection vs Tool Calls section).

---

## Template Blocks 1–3

### 1. Expert Role Assignment

```
You are a [specific expertise] specializing in [domain].
Your analysis methodology:
1. [Step 1 — what you assess first]
2. [Step 2 — what you cross-reference]
3. [Step 3 — how you resolve conflicts]
4. [Step 4 — how you form final judgment]

CONSTRAINTS:
- All numerical calculations are pre-computed and provided below. Do NOT perform arithmetic.
- Use ONLY the provided data. Do not reference external knowledge about current prices or events.
- Flag any data that appears inconsistent or anomalous.
```

### 2. Conflict Detection Protocol

```
## CONFLICT DETECTION (MANDATORY)
Before writing any recommendation:
1. LIST all signals per ticker across inputs (technical vs fundamental vs regime vs flow)
2. For each conflict: state it explicitly — "Conflict: sector BUY but regime RISK_OFF"
3. Resolution priority: [define your hierarchy, e.g., regime > guidance > signal > flow]
4. If unresolvable: downgrade conviction and note "conflicting signals"
FORBIDDEN: "on balance" or "taking everything into account" without listing conflicts first
```

### 3. Confidence Calibration Guide

```
## SIGNAL CONFIDENCE
Append confidence tag in the note/analysis field:
- [HIGH]:   All key indicators align (4/4 or domain-specific threshold)
- [MEDIUM]: Most align, one minor conflict noted explicitly
- [LOW]:    Only 2 indicators align — downgrade recommendation automatically

If you cannot cite 3+ data points from the provided context supporting a recommendation,
it must be downgraded one level (BUY → WATCH, WATCH → WAIT).
```

*Full template blocks 4–10 (Bull/Bear, Abstinence, Citation, CoVe, Structured Output, Few-Shot, Objectivity) → `references/template-blocks.md`*

---

## Strict vs. Flexible Declarations

Use this table when designing output schemas:

| Field | Strictness | Rationale |
|-------|-----------|-----------|
| `signal` (BUY/WATCH/WAIT/AVOID) | **STRICT** | Feeds downstream automation |
| `confidence` (HIGH/MEDIUM/LOW) | **STRICT** | Drives position sizing |
| `thesis` | **FLEXIBLE** | Qualitative judgment |
| `key_risk` | **STRICT template** | Must challenge thesis, not footnote |
| `conflicts_identified` | **STRICT list** | Must enumerate, not summarize |

**Rule:** Fields that feed deterministic downstream code → `Literal` type with exact values. Fields that inform human judgment → `str` with descriptive guidance.

---

## Anti-Hallucination Verification Chain

Apply this chain for any agent producing actionable signals (BUY/WATCH/WAIT/AVOID):

1. **DATA FRESHNESS** — check `scan_date` matches today; reject stale data
2. **COMPLETENESS** — fewer than 3 sources → downgrade to WATCH automatically
3. **RED FLAGS** — zero volume, unchanged price 3+ days, missing technicals → flag explicitly
4. **VERIFICATION (CoVe)** — re-read each claim, trace to a specific provided field
5. **ABSTINENCE** — if >30% claims unverifiable → output `INSUFFICIENT DATA`

This chain should appear as mandatory steps in the system prompt for synthesis, sector, and signal agents.

---

## Anti-Patterns to Avoid

| Anti-Pattern | Why It Fails | Fix |
|-------------|-------------|-----|
| LLM performs arithmetic | "Semantically coherent but mathematically flawed" | Pre-compute in Python |
| Single mega-prompt | Context overload, signals buried | Multi-step pipeline |
| No conflict enumeration | LLM papers over contradictions | Force explicit listing |
| Missing bear case | Systematic bullish bias from training data | Always require KEY RISK |
| Stale parametric knowledge | Model's financial knowledge is months old | Always inject fresh data via tools |
| Verbose narrative | More words = more speculation | Constrain output length, use JSON |
| Vague confidence | "fairly confident" tells you nothing | Use calibrated levels: HIGH/MEDIUM/LOW |
| No abstinence path | Agent generates analysis when data is absent | Explicit INSUFFICIENT DATA output |
| Generic role prompt | "You are a helpful assistant" activates wrong patterns | Specific role with methodology |
| No source attribution | Claims cannot be verified or challenged | Require tool/field citation per claim |

---

## Data Formatting Rules

- Round to meaningful precision: `P/E: 18.2x` not `18.23456789`
- Always include units: `1,500B VND` not `1500`
- Include deltas alongside absolutes: `Gross margin: 32.5% (down 2.6pp YoY)`
- Standardize layout across all tickers for consistency

### Three-Layer Context Structure

| Layer | Data Points | Format |
|-------|------------|--------|
| Technical | RSI, MACD, S/R levels, candlestick patterns, volume | Key values only, not raw OHLCV |
| Fundamental | Revenue, margins, P/E, P/B, ROE, debt/equity | Tabular with YoY deltas |
| Context | Market regime, sector rotation, macro, news | Bullet-point summaries |

---

## Personality Archetypes

Apply the right personality to match agent responsibility:

| Personality | Best For | Key Behavior |
|-------------|---------|-------------|
| Thorough Investigator | sector, synthesis, retro_evaluator | Cross-reference multiple angles, show work, cite specifics |
| Skeptical Auditor | critic, positions_aggregator | Assume errors exist, check every number |
| Decisive Minimalist | alert_analyst, news_examiner | 2-3 sentences max, no hedging |
| Precise Clerk | catalysts, alert_registrar | Extract facts only, never infer |

---

## Prompt Change Workflow

Agent configs live in YAML files at `scripts/agents/configs/*.yaml`. The
`agent_prompts` table was dropped in migration `300_drop_agent_prompts_tables.sql`
(2026-04) — there is no DB-side prompt store anymore.

1. Edit the YAML file directly: `scripts/agents/configs/<agent_key>.yaml`
2. Run the negative-instruction pre-commit hook against the touched file:
   `python scripts/hooks/check_no_negative_tool_instructions.py scripts/agents/configs/<agent_key>.yaml`
   (the hook scans `scripts/agents/configs/` and `scripts/agents/tools/broker/`
   for `\bDO NOT call\b`, `\bNEVER call\b`, `\bDo not call\b`, `\bDo not retry\b`,
   `\bNEVER retry\b`, `\bDO NOT SEARCH\b` — keep all tool guidance positively framed)
3. Verify via dry run: `SWINGY_ENV=local uv run python scripts/run_morning_scan.py --dry-run`
4. Commit the YAML change. No migration required.

---

*Research sources with citations → `references/research-sources.md`*

---

## Gotchas

- **Deterministic computation rule** — never let LLMs compute numbers. Pre-compute R:R, position sizing, mode, regime in Python; LLM interprets only. See `trading-context` skill for the full list of deterministic functions.
- **Negative tool instructions are blocked by pre-commit hook** — `scripts/hooks/check_no_negative_tool_instructions.py` rejects `\bDO NOT call\b` / `\bNEVER call\b` / `\bDo not call\b` / `\bDo not retry\b` / `\bNEVER retry\b` / `\bDO NOT SEARCH\b` (case-insensitive) under `scripts/agents/configs/` and `scripts/agents/tools/broker/`. Use positive framing ("synthesize from the pre-injected context"). Computational rules like "DO NOT compute your own R:R" are intentionally allowed (different defect class).
- **Avoid prompt contradictions on tools** — if the prompt says "data is pre-injected, only use tools if needed" AND ALSO "MANDATORY when X: use call_tools with Y", the model picks the more specific MANDATORY block. On Kimi K2.5 this produces empty `{"calls": []}` batches that loop until `request_limit=30` exhausts. Eliminate the contradiction by removing the conditional trigger — a broker-side empty-batch loop breaker is defense-in-depth, not the primary fix.
- **Tight schema on synthesis agents kills narrative quality** — use `Literal` types only for fields that feed downstream code. Free-text fields (thesis, analysis) need flexible `str` types; over-constraining them produces truncated, hollow outputs.
- **Generic role prompt activates wrong behavioral patterns** — "you are a helpful assistant" is not a valid role for a financial agent. Always specify domain + methodology + constraints in the role block.

---

## Related Skills

| Skill | Load when... |
|-------|-------------|
| `agent-development` | Implementing a prompt change (migration workflow, degrees-of-freedom calibration) |
| `database` | Applying a prompt change migration to `agent_prompts` in Neon |
| `trading-context` | Understanding the domain context that prompts reason about |
