---
name: data-collection
description: Script-first data collection for pipeline review, audit, and any analysis needing DB/Logfire/GH data. Pre-built collector script + adhoc script patterns.
---

# Data Collection

Script-first approach to fetching pipeline data. Replaces MCP tool calls with Python scripts that write JSON to temp files.

## When to Use

Activate when:
- Running `/pipeline-review` or `/audit` (prerequisite)
- Any analysis needing DB, Logfire, or GH Actions data
- Fetching data that would require >3 MCP calls
- Writing adhoc queries for deeper investigation

## Key Tools

- `scripts/collect_review_data.py` — pre-built collector for pipeline review data
- Adhoc script templates for custom queries
- Logfire REST API helper (`LOGFIRE_READ_TOKEN`)

## Instructions
See `instructions.md` for CLI reference, templates, and data cleaning details.
