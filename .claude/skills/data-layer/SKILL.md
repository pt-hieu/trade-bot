---
name: data-layer
description: Three-tier data access rules, API-first pattern, sync vs async rules, adding new data sources to pipelines and agent tools.
---

# Data Layer

Three-tier hierarchy: `shared.api.*` (API-first) → `shared.vnstock_client` (HTTP) → `shared.neon.*` (DB). Never bypass a tier.

**Critical:** `*_sync()` before async pipelines destroys the connection pool. See Gotchas in `instructions.md`.

See `instructions.md` for tier rules, patterns, and adding new data sources.
