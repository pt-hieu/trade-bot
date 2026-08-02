---
name: coordinator-architecture
description: Coordinator agent architecture decisions — tool broker, skills, delegation, caching strategy, sub-agent management. Use when modifying coordinator tools, adding/removing sub-agents, or changing how the coordinator routes queries.
---

# Coordinator Architecture

Manages how the coordinator agent routes queries: direct tool calls vs skill delegation vs sub-agent dispatch.

**Critical:** Changes to coordinator routing affect ALL downstream agents. Test with `workflow_dispatch` before deploying.

See `instructions.md` for full reference.
