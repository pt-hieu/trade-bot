"""Unit tests for agent config loader."""

import pytest

from shared.agent_config import _parse_model_settings


@pytest.mark.parametrize(
    "input_val,expected",
    [
        ({"a": 1, "b": "x"}, {"a": 1, "b": "x"}),  # dict passthrough
        ('{"a": 1}', {"a": 1}),  # JSON string
        (None, {}),  # None
        ("", {}),  # empty string
        (0, {}),  # zero
        ([1, 2], {}),  # list
    ],
)
def test_parse_model_settings(input_val, expected):
    assert _parse_model_settings(input_val) == expected


def test_configs_dir_exists():
    """YAML configs directory must exist with files."""
    from shared.agent_config import CONFIGS_DIR

    assert CONFIGS_DIR.exists(), f"Configs dir not found: {CONFIGS_DIR}"
    yaml_files = list(CONFIGS_DIR.glob("*.yaml"))
    assert len(yaml_files) >= 30, f"Expected 30+ configs, found {len(yaml_files)}"


@pytest.mark.asyncio
async def test_load_agent_config_reads_yaml():
    """Config loader reads from YAML files."""
    from shared.agent_config import clear_config_cache, load_agent_config

    clear_config_cache()
    config = await load_agent_config("market_level")
    assert config.agent_key == "market_level"
    assert config.system_prompt
    assert config.model_id


@pytest.mark.asyncio
async def test_load_agent_config_caches():
    """Second call returns cached instance."""
    from shared.agent_config import clear_config_cache, load_agent_config

    clear_config_cache()
    config1 = await load_agent_config("market_level")
    config2 = await load_agent_config("market_level")
    assert config1 is config2


@pytest.mark.asyncio
async def test_load_agent_config_missing_key():
    """Missing agent key raises ValueError."""
    from shared.agent_config import clear_config_cache, load_agent_config

    clear_config_cache()
    with pytest.raises(ValueError, match="No config file"):
        await load_agent_config("nonexistent_agent_key_xyz")


@pytest.mark.asyncio
async def test_load_agent_config_resolves_tool_retry_fragment():
    """{{include: tool_retry_guardrail}} expands to the canonical 5-bullet block."""
    from shared.agent_config import clear_config_cache, load_agent_config

    clear_config_cache()
    config = await load_agent_config("longterm")
    prompt = config.system_prompt
    assert "{{include:" not in prompt, "include directive should be resolved"
    assert "## TOOL RETRY GUARDRAIL" in prompt
    assert "State explicitly what data is missing rather than retrying indefinitely." in prompt


def test_resolve_includes_preserves_indent():
    """Fragment expansion prepends the directive's indent to every fragment line."""
    from shared.agent_config import _resolve_includes

    text = "    {{include: tool_retry_guardrail}}"
    resolved = _resolve_includes(text, "test-agent")
    assert "{{include:" not in resolved
    for line in resolved.splitlines():
        if line:
            assert line.startswith("    "), f"line lost indent: {line!r}"


def test_resolve_includes_raises_on_missing_fragment():
    """Unknown fragment name raises immediately with the looked-up path."""
    from shared.agent_config import _resolve_includes

    with pytest.raises(ValueError, match="Agent config fragment not found"):
        _resolve_includes("{{include: does_not_exist}}", "test-agent")


def test_resolve_includes_raises_on_inline_directive():
    """Inline (non-standalone-line) directives are not supported and must raise."""
    from shared.agent_config import _resolve_includes

    with pytest.raises(ValueError, match="unresolved include directive"):
        _resolve_includes("prefix {{include: tool_retry_guardrail}} suffix", "test-agent")
