# Monitoring Items — Bundle-side Update Protocol

**What this file is:** the bundle-side *how-to* for the regression-watch slice that ships in every `/pipeline-review` run. Generic Linear protocol (categories, severity, workflow states, label taxonomy, fenced-JSON contract, outage behavior) lives in the **`linear` skill** — load it first.

The collector ships two rendered markdown files (generated fresh by `scripts/export_issues.py`):

- `monitoring_items.md` — active regression-watch items.
- `resolved_items.md` — Resolved ≤90 days regression-watch items (regression cross-check reference).

Both inject into every subagent prompt at Step 3 as `## KNOWN ACTIVE ISSUES` and `## RESOLVED ISSUES`.

---

## Purpose

Cross-run memory for pipeline review findings that are:
- **Ambiguous** — need more observations before fixing.
- **Under suppression** — e.g. a fix landed recently and is in a wait window.
- **Slow-burn** — persistent issues not yet promoted to a fix ticket.
- **Fix candidates** — already fixed elsewhere; watching to confirm no regression.

Goal: stop subagents re-raising the same finding every day, and give the orchestrator a place to record "watch this for N more runs" decisions.

---

## Update protocol (run by the pipeline-review orchestrator after aggregation)

Follow these steps at the end of every pipeline review — after all 3 subagents have returned but before presenting the final report:

1. **Concatenate subagent reports** — each subagent embeds a fenced JSON block per `references/subagent-prompts.md`.
2. **Invoke the write-back script** — see Step 4a in `instructions.md`.
3. **Abstinence on updates:** if a subagent's findings are inconclusive (relevant pipeline didn't run, trace missing, evidence indirect), the subagent omits that bump/regression — the clean-run counter only counts runs where the watch-for condition was actually observable.
4. **Promotion on worsening:** when evidence grew (more tickers, longer durations, new pipeline), the subagent records a `bumps[]` entry with a reproduction note. To raise severity or priority, edit the Linear issue directly in UI — the Pydantic contract does not carry "escalate in place".

---

## Subagent contract

Subagents receive `monitoring_items.md` + `resolved_items.md` inside the bundle. Subagent-side rules (match-then-bump/regress, cite Linear id, emit fenced JSON only, never-call-Linear) live in `references/subagent-prompts.md`. The fenced-JSON contract itself is the `linear` skill.

---

## Anti-patterns

- ❌ Editing the bundle's `monitoring_items.md` / `resolved_items.md` directly — they regenerate on every collector run.
- ❌ Subagents calling Linear MCP tools — subagents emit fenced JSON only.
- ❌ Promoting to Done on the first clean run when the rule says 3 consecutive — use `resolved_candidates[]`.
- ❌ Skipping the fenced JSON block at report end — the write-back falls back to a parse-failure comment, but the class of finding is lost as a tag action.
