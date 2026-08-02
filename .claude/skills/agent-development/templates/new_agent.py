"""
<Agent Name> Agent

<Brief description of what this agent does and when it runs.>
"""

import logging
from datetime import date
from typing import Literal  # noqa: F401 — used in template examples below

from pydantic import BaseModel, Field

from shared.agent_config import load_agent_config
from shared.observability import span

from .agent_factory import AgentDeps, create_agent

logger = logging.getLogger(__name__)

AGENT_KEY = "<agent_key>"  # Must match YAML filename: scripts/agents/configs/<agent_key>.yaml


# --- Output Schema ---


class AgentOutput(BaseModel):
    """Structured output for the agent."""

    # Use Literal types for tight agents (parsers, classifiers):
    #   action: Literal["BUY", "SELL", "HOLD"]
    # Use str for loose agents (narrative, commentary):
    #   summary: str
    field_name: str = Field(description="Description of this field")


# --- Entry Point ---


async def run_agent(input_data: dict, scan_date: date, tickers: list[str]) -> AgentOutput:
    """Entry point — called by pipeline.

    Args:
        input_data: Dict with pipeline context (portfolio state, upstream agent output, etc.)
        scan_date: Trading date being analyzed.
        tickers: Tickers in scope for this run (used by ticker-scoped tools).
    """
    config = await load_agent_config(AGENT_KEY)
    agent = create_agent(config, output_type=AgentOutput)

    # Tools come from two sources:
    #   1. Native registry tools — listed in YAML `allowed_tools:` block, auto-wired by
    #      create_agent via build_native_tools() + prepare_tools(). The agent can call
    #      any allowlisted tool by its dotted name (e.g. fundamental.get_valuation), and
    #      can admit a non-allowlisted tool at run time via unlock_tool(tool_name="...").
    #   2. Inline module-specific tools — register on the agent here when no shared tool
    #      fits. These bypass the allowlist by design.
    #
    #   @agent.tool_plain
    #   async def tool_get_something() -> list[dict]:
    #       """Docstring the LLM sees as the tool description."""
    #       return await fetch_from_db()

    prompt = f"""Task description here.

DATE: {scan_date}

INPUT:
{input_data}"""

    deps = AgentDeps(scan_date=scan_date, agent_key=AGENT_KEY, tickers_in_scope=tickers)

    with span(AGENT_KEY, scan_date=str(scan_date)):
        result = await agent.run(prompt, deps=deps)

    return result.output
