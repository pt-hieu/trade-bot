"""
Agent configuration loader — reads config from YAML files in the codebase.

Caches configs in-memory for the lifetime of the process.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic_ai.usage import UsageLimits

CONFIGS_DIR = Path(__file__).parent.parent / "agents" / "configs"
_FRAGMENTS_DIR = CONFIGS_DIR / "_fragments"

# Concurrency cap for high-volume per-record LLM labeling tasks (narrative
# labeling, article sentiment scoring). Hoisted here so all labeling
# orchestrators share the same semaphore size — bumping this cap rebalances
# the whole fleet at once. (SWI-103 R2 arch F3.)
LLM_LABELING_CONCURRENCY: int = 10

# Matches a line whose sole non-whitespace content is `{{include: <name>}}`.
# Captures the leading indent so expansion preserves it on every fragment line.
_INCLUDE_PATTERN = re.compile(
    r"^([ \t]*)\{\{include:\s*([a-zA-Z0-9_]+)\s*\}\}[ \t]*$", re.MULTILINE
)

_fragment_cache: dict[str, str] = {}


def _load_fragment(name: str) -> str:
    """Read a fragment file from configs/_fragments/<name>.md. Raises if missing."""
    if name in _fragment_cache:
        return _fragment_cache[name]
    path = _FRAGMENTS_DIR / f"{name}.md"
    if not path.exists():
        raise ValueError(f"Agent config fragment not found: {path}")
    text = path.read_text(encoding="utf-8").rstrip("\n")
    _fragment_cache[name] = text
    return text


def _resolve_includes(text: str, agent_key: str) -> str:
    """Expand `{{include: <name>}}` directives inline, preserving each directive's leading indent."""

    def _replace(match: re.Match[str]) -> str:
        indent = match.group(1)
        fragment = _load_fragment(match.group(2))
        return "\n".join(f"{indent}{line}" if line else line for line in fragment.splitlines())

    resolved = _INCLUDE_PATTERN.sub(_replace, text)
    if "{{include:" in resolved:
        raise ValueError(
            f"Agent '{agent_key}' has an unresolved include directive in system_prompt; "
            "only standalone lines like `{{include: name}}` are supported."
        )
    return resolved


@dataclass(frozen=True)
class AgentConfig:
    """Full agent configuration from YAML."""

    agent_key: str
    system_prompt: str
    model_id: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    output_retries: int = 0
    request_limit: int = 30
    model_settings: dict[str, object] | None = None
    # opt out of FallbackModel wrapping. MiniMax M2.7 chokes on nested
    # Pydantic structured output (3+ nesting levels); agents with deeply
    # nested output_types set this true in YAML to skip the fallback chain
    # entirely and raise ProviderUnavailable if the primary is unhealthy.
    disable_fallback: bool = False
    # Per-agent broker tool allowlist. Names are dotted broker tool ids
    # (e.g. ``enrichment.get_flow``). Any tool NOT in this set is hidden from
    # the agent unless it calls ``unlock_tool`` to admit it for the rest of
    # the run. ``frozenset()`` for an inject-first agent that doesn't need
    # any broker tool by default. See SWI-180.
    allowed_tools: frozenset[str] = frozenset()


def build_usage_limits(config: AgentConfig) -> UsageLimits:
    return UsageLimits(request_limit=config.request_limit)


_cache: dict[str, AgentConfig] = {}


def _parse_model_settings(value: object) -> dict[str, object]:
    """Normalize model_settings — YAML may produce dict, None, or str."""
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


async def load_agent_config(agent_key: str) -> AgentConfig:
    """Load full agent config from YAML file by agent_key, with caching."""
    if agent_key in _cache:
        return _cache[agent_key]

    config_path = CONFIGS_DIR / f"{agent_key}.yaml"
    if not config_path.exists():
        raise ValueError(f"No config file for agent_key={agent_key}. Expected: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    resolved_prompt = _resolve_includes(data["system_prompt"], agent_key)

    config = AgentConfig(
        agent_key=agent_key,
        system_prompt=resolved_prompt,
        model_id=data.get("model_id"),
        temperature=data.get("temperature"),
        max_tokens=data.get("max_tokens"),
        top_p=data.get("top_p"),
        output_retries=data.get("output_retries") or 0,
        request_limit=data.get("request_limit") or 30,
        model_settings=_parse_model_settings(data.get("model_settings")),
        disable_fallback=bool(data.get("disable_fallback") or False),
        allowed_tools=frozenset(data.get("allowed_tools") or ()),
    )

    # Validate config fields
    if not config.system_prompt or not config.system_prompt.strip():
        raise ValueError(f"Agent '{agent_key}' has empty system_prompt in {config_path}")
    if config.temperature is not None and not (0.0 <= config.temperature <= 2.0):
        raise ValueError(f"Agent '{agent_key}' has invalid temperature: {config.temperature}")
    if config.max_tokens is not None and config.max_tokens <= 0:
        raise ValueError(f"Agent '{agent_key}' has invalid max_tokens: {config.max_tokens}")

    _cache[agent_key] = config
    return config


def clear_config_cache():
    """Clear cached configs (useful for testing or hot-reload)."""
    _cache.clear()
    _fragment_cache.clear()
