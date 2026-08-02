---
name: pipeline-workflows
description: Pipeline schedules, database tables, LLM analysis steps, alert architecture, script inventory. Use when working on pipeline scripts, debugging workflows, understanding data flow, or tracing which script writes to which table.
---

# Pipeline Workflows

Three daily pipelines: morning brief (00:00 UTC), midday check (~04:00 UTC), retrospective (08:00 UTC). Weekly watchlist (Sat 00:00 UTC).

**Critical:** Trading mode is deterministic (`determine_mode()` in Python) — LOW_CASH/REALLOCATION hard-block BUY regardless of LLM output.

See `instructions.md` for full reference.
