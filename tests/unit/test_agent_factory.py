"""Unit tests for agent factory."""

from unittest.mock import patch

import pytest
from pydantic import BaseModel
from pydantic_ai.models.test import TestModel

from shared.agent_config import AgentConfig


def _make_config(**overrides) -> AgentConfig:
    defaults = {
        "agent_key": "test_agent",
        "system_prompt": "You are a test agent.",
        "model_id": None,
        "temperature": None,
        "max_tokens": None,
        "top_p": None,
        "output_retries": 0,
        "model_settings": None,
        "disable_fallback": False,
    }
    defaults.update(overrides)
    return AgentConfig(**defaults)


class TestResolveModelWithFallback:
    """T03: disable_fallback flag semantics."""

    def test_disable_fallback_returns_retry_wrapped_primary(self, monkeypatch):
        """disable_fallback skips FallbackModel but still wraps in RetryModel+HopTiming.

        Pre-2026-04-22 this branch returned a bare OpenRouterModel — a silent
        provider hang then burned the full 240s outer wall. Post-fix the
        primary is wrapped in HopTimingModel (75s per-hop wall, SWI-318) plus
        RetryModel (up to 2 conditional retries with 2-8s jitter when no
        cluster evidence), but the FallbackModel chain is still skipped.
        """
        from pydantic_ai.models.fallback import FallbackModel

        from agents.model import resolvers as model_module

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.setattr(model_module, "_primary_healthy", True)
        monkeypatch.setattr(model_module, "is_dry_run", lambda: False)

        config = _make_config(model_id="moonshotai/Kimi-K2.5", disable_fallback=True)
        resolved = model_module.resolve_model_with_fallback(config)

        assert isinstance(resolved, model_module.RetryModel)
        assert isinstance(resolved.wrapped, model_module.HopTimingModel)
        assert not isinstance(resolved, FallbackModel)

    def test_disable_fallback_raises_when_primary_unhealthy(self, monkeypatch):
        from agents.model import resolvers as model_module
        from shared.errors import ProviderUnavailable

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.setattr(model_module, "_primary_healthy", False)
        monkeypatch.setattr(model_module, "is_dry_run", lambda: False)

        config = _make_config(
            agent_key="sector_aggregator",
            model_id="moonshotai/Kimi-K2.5",
            disable_fallback=True,
        )
        with pytest.raises(ProviderUnavailable, match="fallback disabled"):
            model_module.resolve_model_with_fallback(config)

    def test_default_config_still_wraps_with_fallback(self, monkeypatch):
        from pydantic_ai.models.fallback import FallbackModel

        from agents.model import resolvers as model_module

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.setattr(model_module, "_primary_healthy", True)
        monkeypatch.setattr(model_module, "is_dry_run", lambda: False)

        config = _make_config(model_id="moonshotai/Kimi-K2.5", disable_fallback=False)
        resolved = model_module.resolve_model_with_fallback(config)

        assert isinstance(resolved, FallbackModel)


class _TestOutput(BaseModel):
    result: str


@pytest.fixture
def mock_deps():
    """Mock resolve_model."""
    with patch("agents.agent_factory.resolve_model_with_fallback") as mock_model:
        mock_model.return_value = TestModel()
        yield mock_model


class TestCreateAgent:
    def test_basic_agent_creation(self, mock_deps):
        from agents.agent_factory import create_agent

        config = _make_config()
        agent = create_agent(config)
        assert "You are a test agent." in agent._system_prompts[0]

    def test_with_output_type(self, mock_deps):
        from agents.agent_factory import create_agent

        config = _make_config()
        agent = create_agent(config, output_type=_TestOutput)
        assert agent.output_type is _TestOutput

    def test_temperature_applied(self, mock_deps):
        from agents.agent_factory import create_agent

        config = _make_config(temperature=0.7)
        agent = create_agent(config)
        assert agent.model_settings["temperature"] == 0.7

    def test_all_settings_applied(self, mock_deps):
        from agents.agent_factory import create_agent

        config = _make_config(
            temperature=0.5,
            max_tokens=2048,
            top_p=0.9,
            model_settings={"frequency_penalty": 0.1},
        )
        agent = create_agent(config)
        assert agent.model_settings["temperature"] == 0.5
        assert agent.model_settings["max_tokens"] == 2048
        assert agent.model_settings["top_p"] == 0.9

    def test_native_tools_registered(self, mock_deps):
        """Post-SWI-180: every agent gets the full native catalog + unlock_tool."""
        from agents.agent_factory import create_agent
        from agents.tools.broker.registry import TOOL_CATALOG

        config = _make_config()
        agent = create_agent(config)
        toolset = agent._function_toolset
        tool_names = {t.name for t in toolset.tools.values()}
        assert "unlock_tool" in tool_names
        assert tool_names >= set(TOOL_CATALOG.keys())

    def test_output_retries(self, mock_deps):
        from agents.agent_factory import create_agent

        config = _make_config(output_retries=3)
        agent = create_agent(config, output_type=_TestOutput)
        assert agent._max_result_retries == 3

    def test_factory_uses_non_stream_path(self, mock_deps):
        """Prod agents do not enable streaming, so the non-stream `request()` wall is
        the active silent-hang guard — NOT a per-chunk stream idle timeout.

        Documents the corrected code-path understanding (SWI-378): the per-chunk
        stream idle guard (Fix D) is out of scope precisely because `agent.run()`
        takes the non-stream branch when no `event_stream_handler` is set. A future
        reader must not re-add a stream-only fix without first enabling streaming.
        """
        from agents.agent_factory import create_agent

        config = _make_config()
        agent = create_agent(config)
        assert agent.event_stream_handler is None
