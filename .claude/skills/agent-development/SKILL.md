---
name: agent-development
description: PydanticAI agent config architecture, tool registry patterns, agent factory, creating new agents, model resolution, eval framework. Use when creating or modifying agents, tools, or running evals.
---

# Agent Development

**Critical:** Agent config lives in YAML files at `scripts/agents/configs/{agent_key}.yaml`. Config changes are committed to git — no migration needed.

See `instructions.md` for architecture, tool registry, degrees-of-freedom calibration, and eval framework.

## Templates

| Template | Use for |
|----------|---------|
| [templates/new_agent.py](templates/new_agent.py) | Creating a new PydanticAI agent with config loading + output schema |
