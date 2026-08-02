# Component Audit

Targeted investigation: is this component producing good output, and are downstream agents reasoning well from it — or is it poisoning them?

## Prerequisites

Load these skills first:
1. `linear` — issue protocol, label taxonomy, workflow states, fenced-JSON contract, write-back script
2. `data-collection` — script-first data fetching, adhoc templates, Logfire REST API
3. `pipeline-workflows` — phase ordering, DB table mappings
4. `agent-development` — agent config, prompt structure
5. `pipeline-review` — Step 5 dedup pattern overlaps with Step 1a in `pipeline-review/instructions.md`

---

## Step 1: Identify Audit Target

Parse `/audit <component>` — resolve using `references/component-hints.md`.

**Always explore** (hints are starting points, not exhaustive):
1. Grep for producer function/module → confirm current output shape
2. Grep for consumers → output variable names, DB reads, context formatters
3. Trace: producer → DB/memory → context formatter → agent prompt

**Date range:** Last 5 trading days (default). Override: `--days 10` or `--date 2026-03-28`

### Step 1a: Active-issues sweep for the component (MANDATORY)

Before data collection, query Linear team Swingy for OPEN + In Progress issues via `mcp__claude_ai_Linear__list_issues`. Shortlist items matching any of:

- title keyword overlap with `<component>` and hints from `references/component-hints.md`
- `area:*` label matches the component's area (e.g. `area:news`, `area:catalyst`, `area:agent-prompts`)
- `pipeline:*` label overlaps pipelines consuming the component

Read each shortlisted Linear issue and route it by its `category:*` label:

| Category label | Step 3 prompt injection | Step 5 dedup |
|----------------|------------------------|--------------|
| `audit-finding` | header context: prior audit Linear id + verdict | drives **reuse-vs-new** decision below |
| `bug` or `regression-watch` (prior evidence lives in KNOWN ACTIVE ISSUES block) | "KNOWN OPEN SYMPTOMS — cite Linear id if observed" | reuse existing Linear id, record under `bumps[]` |
| `scheduled-work` | "KNOWN QUEUED WORK — reference this Linear id instead of raising as new" | reuse existing Linear id, append reproduction comment |
| `regression-watch` OPEN | "KNOWN WATCH — downgrade matches to INFO and cite the Linear id" | record under `bumps[]` on match |

**Reuse-vs-new audit-finding decision** — pick one:

- Prior `category:audit-finding` OPEN on same component, opened ≤7 days ago, date range overlaps → append a comment to the existing issue with new evidence and re-promote unresolved CRITICAL findings. No new audit issue.
- Prior `category:audit-finding` OPEN but >7 days old or non-overlapping range → file a new audit issue via `process_review_findings.py` with the previous Linear id set as `blockedBy` (the previous audit blocks full resolution until this one confirms the pattern). When this audit conclusively replaces the prior, mark the prior as Canceled with `duplicateOf` pointing to the new audit.
- No prior audit-finding → file a fresh one.

Report header line: `Prior active issues on <component>: N audit-finding / N bug / N scheduled-work / N regression-watch` with Linear ids inline.

---

## Step 2: Data Collection

See `data-collection` skill for full reference (templates, Logfire helper, gotchas).

**For baseline data** (daily_records, recommendations, beliefs, portfolio):
```bash
SWINGY_ENV=production uv run python scripts/collect_review_data.py --date [end_date]
```

**For component-specific data**, write an adhoc script (see `data-collection` skill template):
1. Create `/tmp/swingy-audit-{component}.py`
2. Query component's DB table(s) per `references/component-hints.md`
3. Query downstream consumer outputs for same date range
4. Add Logfire queries if `LOGFIRE_READ_TOKEN` set
5. Run: `SWINGY_ENV=production uv run python /tmp/swingy-audit-{component}.py`

**Also:** Explore codebase (producer + consumer code) and GH Actions logs for the date range.

---

## Step 3: Launch 2 Parallel Subagents

Both: **background Opus**, zero tool calls, all data **inline**.

**Inject Step 1a shortlist into both prompts** as `## Known Active Issues on <component>` — list each shortlisted id with title + `watch_for` (or `summary`). Append this directive verbatim:

```
For any finding that matches a listed id's watch-for/symptom: tag `tracked: <id>` and downgrade to INFO. The orchestrator bumps `last_seen` on that item in Step 5 — do not draft a duplicate. New findings must stake a scope that no listed id covers.
```

### Subagent 1: Component Quality Auditor

**Personality: Skeptical Auditor** — assume errors exist.

```
You are a skeptical auditor evaluating [COMPONENT] in a Vietnamese stock trading pipeline.

METHODOLOGY: Examine each output for factual grounding → compare across days for staleness → check internal consistency → assess downstream actionability.

Analyze ONLY the data below. No tool calls.

## CONFLICT DETECTION (MANDATORY)
List all contradictory signals within the component's own output before scoring.
"Conflict: [field A] says X but [field B] says Y" — unresolved = automatic downgrade.

## EVALUATION DIMENSIONS (1-10, quoted evidence)
1. Factual Grounding — cites actual data? [HIGH]: 4+ data points | [LOW]: vague
2. Specificity — concrete numbers, dates, levels? Red flag: generic phrases
3. Internal Consistency — parts contradict? (bearish narrative + bullish signal)
4. Freshness — verbatim repetition across days = staleness. Red flag: 3+ days same phrasing
5. Calibration — confidence matches evidence strength?
6. Actionability — downstream agent gets clear, usable signal?

## VERIFICATION (MANDATORY)
Re-read each claim → trace to specific output sample → remove unattributable claims.
If >30% unattributable → note this.

## INSUFFICIENT DATA
Missing/unverifiable dimension → "INSUFFICIENT DATA — [what's missing]". Do NOT guess.

OUTPUT: Per dimension: score + evidence. Overall: STRONG / ADEQUATE / DEGRADING / FAILING.
2-3 improvement recommendations with file paths.
```

### Subagent 2: Downstream Impact Auditor

**Personality: Thorough Investigator** — cross-reference, cite specifics.

```
You are investigating how downstream agents consume [COMPONENT] output in a Vietnamese stock trading pipeline. Goal: does this component help or hurt downstream reasoning?

METHODOLOGY: For each consumer — compare component input vs agent output → look for absorption, amplification, distortion, error propagation → find best/worst date+ticker examples.

Analyze ONLY the data below. No tool calls.

## CONFLICT DETECTION (MANDATORY)
List cases where component signal conflicts with consumer's other inputs.
"Conflict: [component] says X, but [other input] says Y → agent chose Z"
Silent contradiction (agent ignores conflict) = automatic red flag.

## PER-CONSUMER EVALUATION
1. Absorption — agent demonstrably used component data? Red flag: ignored entirely
2. Amplification vs Parroting — added new analysis or just copied? Red flag: circular reasoning
3. Contradiction Handling — reconciles conflicting signals or picks one silently?
4. Error Propagation — catches bad component output or blindly propagates?
5. Signal Fidelity — structured signals (BUY/SELL, direction) faithfully carried?

## PRO/CON BALANCE (MANDATORY)
Strongest case FOR the component being useful, then strongest case AGAINST.

## VERIFICATION
Re-read each claim → trace to (date, component excerpt, downstream excerpt). Remove unattributable.

OUTPUT: Per consumer: absorption, amplification (1-10), contradictions, error propagation, fidelity %.
Verdict: BENEFICIAL / NEUTRAL / DEGRADING / POISONING.
2-3 (date, component → downstream) examples: best and worst.
```

---

## Step 4: Report

```markdown
# Audit: [Component]
**Date range:** [start] to [end] | **Samples:** N runs

## Component Quality
| Dimension | Score | Key Evidence |
|-----------|-------|-------------|
| ... | X/10 | ... |
| **Overall** | **X/10** | **STRONG/ADEQUATE/DEGRADING/FAILING** |

## Downstream Impact
| Consumer | Absorption | Amplification | Contradictions | Error Prop | Fidelity |
|----------|-----------|--------------|----------------|-----------|----------|
**Verdict: BENEFICIAL / NEUTRAL / DEGRADING / POISONING**

## Best / Worst Examples
## Recommendations (with file paths)
```

After report, offer: drill into consumer, see all instances of worst pattern, compare good vs bad days.

---

## Step 5: Persist as Linear audit-finding + Promote Children

The `linear` skill owns the protocol (categories, severity, fenced-JSON contract, write-back script behavior). The audit-specific child-promotion rules stay here:

1. **Build the fenced JSON findings block** at the end of the audit report. The four buckets the orchestrator consumes are: `regressions[]` (Resolved → Confirm Regression), `bumps[]` (reproduction comment on existing OPEN SWI), `resolved_candidates[]` (cautious + auto-promote — see step 6), and `new[]` (creates the audit-finding parent + promoted children). The audit emits a single `new[]` entry for the audit-finding itself plus one entry per promoted child:
   - `category: audit-finding` for the parent — title is the audit component, severity is the overall verdict.
   - `category: regression-watch` per `findings[].severity: CRITICAL` — dimension required.
   - `category: scheduled-work` per `recommendations[].priority: P0|P1` — priority required (P0–P3).
   - Add `bumps[]` entries for shortlisted matches from Step 1a (reuse beats duplicate).
2. **Description markdown for the parent audit** follows the audit-specific shape: `## Audit summary`, `## Scorecard`, `## Downstream impact`, `## Findings`, `## Recommendations`, `## Examples — best|worst`. The orchestrator writes this directly into the `new[].evidence` field.
3. **Invoke the write-back**:
   ```bash
   SWINGY_ENV=production uv run python scripts/process_review_findings.py \
       --source-kind audit \
       --report /tmp/swingy-audit-<component>-<date>/audit-report.md \
       --parse-failure-issue SWI-<sentinel>
   ```
4. **Link children to parent**: after the write-back, the orchestrator fetches the newly-created `category:audit-finding` issue and adds a `blockedBy` relation from each child to the parent via Linear MCP `save_issue` — the audit is the child's blocker.
5. **Dedup against Step 1a shortlist**: when a finding or recommendation matches a shortlisted OPEN Linear issue, the fenced JSON uses `bumps[]` with the existing Linear id — no new issue is filed.

6. **`resolved_candidates[]` — cautious lane vs auto-promote lane.** When the audit confirms a shortlisted OPEN regression-watch SWI's watch-for stayed absent on the audited slice, emit:
   - **Cautious lane (default):** `{ "linear_id": "SWI-NN", "clean_runs": 1|2 }` — no citations, no closing commit. The orchestrator parks the SWI at `Resolved Candidate`.
   - **Auto-promote lane:** `{ "linear_id": ..., "clean_runs": 3, "closing_commit": "<sha7-40>", "citations": [exercised, clean, coherent] }` — required ONLY when (a) the watch-for has stayed absent across 3 consecutive runs, (b) you can cite a span/trace proving the watched path ran (`exercised`), (c) you can cite a field/span/row showing the symptom is absent in that path (`clean`), and (d) you can cite the closing commit's diff vs the original symptom (`coherent`), with the closing commit sha verifiable via `git log --grep=<linear_id>`.
   Each citation needs at least one structural anchor (`trace_id` / `span_name` / `table_row`) plus a ≥20-char `quote`. The orchestrator's four invariants (state precedence, scope match, commit verification, bundle freshness) reject any drifted payload — when unsure, stay in the cautious lane.

---

## Gotchas

- **In-memory components** (sector_analysis, macro_trends): no DB trail. Rely on Logfire traces + downstream outputs.
- **`gen_ai.response.text` often empty.** Infer reasoning from output artifacts vs input data.
- **Verify scoring methodology before concluding accuracy is bad.** BEARISH 0% accuracy (178 beliefs, 0 correct) was a measurement artifact — 3% threshold too tight for VN 5-day moves, not agent failure. Always check outcome distribution: `SELECT actual_direction, COUNT(*) FROM agent_beliefs WHERE brier_score IS NOT NULL GROUP BY actual_direction`. If one class is <5% of outcomes, accuracy for that class is meaningless.

---

## Related Skills

| Skill | When |
|-------|------|
| `data-collection` | Always (prerequisite) |
| `pipeline-workflows` | Always (prerequisite) |
| `agent-development` | Always (prerequisite) |
| `finance-prompting` | Findings trace to prompt quality |
| `trading-context` | Validate signals against strategy rules |
| `linear` | Owns the Linear protocol (categories, severity, workflow states, fenced-JSON contract, ad-hoc filing recipes) |
| `pipeline-review` | Full pipeline review instead of targeted audit; Step 1a shortlist pattern overlaps |
