"""
Agent factory — creates PydanticAI agents from YAML config.

Usage:
    config = await load_agent_config("market_level")
    agent = create_agent(config, output_type=MarketRegimeResult)
    deps = AgentDeps(scan_date=today, agent_key="market_level")
    result = await agent.run(prompt, deps=deps)

The factory wires native PydanticAI tools (`build_native_tools()`) and the
`unlock_tool` helper into every agent. `prepare_tools` filters the surface
to ``config.allowed_tools | deps.unlocked | {"unlock_tool"}`` per call.
The agent's `system_prompt` is prepended with the rendered tool catalog so
the model sees the available tools without a search round-trip. See
SWI-180.
"""

import logging
from typing import Any

from pydantic_ai import Agent, Tool
from pydantic_ai.settings import ModelSettings

from shared.agent_config import AgentConfig
from shared.session import get_extra_body

from .model import resolve_model_with_fallback
from .tools.native_tools import (
    AgentDeps,
    build_native_tools,
    make_prepare_tools,
    render_catalog,
    unlock_tool,
)

__all__ = ["AgentDeps", "create_agent"]

logger = logging.getLogger(__name__)


def create_agent(
    config: AgentConfig,
    output_type: type | None = None,
) -> Agent[AgentDeps, Any]:
    """Create a PydanticAI agent from YAML config.

    `config.allowed_tools` drives both the rendered catalog and the
    `prepare_tools` filter. Run-time deps flow via `agent.run(deps=...)`.
    """
    model = resolve_model_with_fallback(config)

    settings: dict[str, object] = {}
    if config.temperature is not None:
        settings["temperature"] = config.temperature
    if config.max_tokens is not None:
        settings["max_tokens"] = config.max_tokens
    if config.top_p is not None:
        settings["top_p"] = config.top_p
    if config.model_settings:
        settings.update(config.model_settings)

    openrouter_extra = get_extra_body(agent_name=config.agent_key)
    if openrouter_extra:
        existing_extra = settings.get("extra_body")
        if isinstance(existing_extra, dict):
            settings["extra_body"] = {**existing_extra, **openrouter_extra}
        else:
            settings["extra_body"] = openrouter_extra

    catalog_block = render_catalog(config.allowed_tools)
    system_prompt = f"{catalog_block}\n\n{config.system_prompt}"

    kwargs: dict[str, object] = {
        "system_prompt": system_prompt,
        "name": config.agent_key,
        "deps_type": AgentDeps,
        "tools": [*build_native_tools(), Tool(unlock_tool, takes_ctx=True)],
        "prepare_tools": make_prepare_tools(config.allowed_tools),
    }
    if output_type:
        kwargs["output_type"] = output_type
    if config.output_retries > 0:
        kwargs["output_retries"] = config.output_retries
    if settings:
        # ModelSettings is a TypedDict with per-key concrete types; the values
        # came from YAML and were validated during AgentConfig loading.
        kwargs["model_settings"] = ModelSettings(**settings)  # type: ignore[arg-type]

    return Agent(model, retries=2, **kwargs)  # type: ignore[arg-type]
