---
name: company-research
description: Interactive research workflow for populating company_profiles DB table. Guides through web research, schema structuring, user review, and DB upsert. Use when researching a Vietnamese stock's business model, supply chain, macro sensitivities, or competitive position.
---

# Company Research

Populates `company_profiles` DB table via guided web research → schema structuring → user review → DB upsert.

**Critical:** Always check if a profile already exists before starting. Use `get_company_knowledge` MCP tool or query `company_profiles` table.

**Prerequisites:** `database` skill (for upsert migration), `trading-context` skill (for sector/macro context).

See `instructions.md` for the full research playbook.
