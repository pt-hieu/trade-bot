"""Unit tests for model resolution priority chain."""

import os
from unittest.mock import MagicMock, patch

import pytest

from shared.agent_config import AgentConfig


def _make_config(**overrides) -> AgentConfig:
    """Create AgentConfig with defaults."""
    defaults = {
        "agent_key": "test",
        "system_prompt": "test prompt",
        "model_id": None,
    }
    defaults.update(overrides)
    return AgentConfig(**defaults)


@pytest.fixture(autouse=True)
def _reset_logged_tier():
    """Reset the _logged_tier flag before each test."""
    import agents.model as m

    m._logged_tier = False
    yield
    m._logged_tier = False


@pytest.fixture(autouse=True)
def _disable_dry_run(monkeypatch):
    """Disable SWINGY_DRY_RUN / is_dry_run so these tests exercise the
    real resolve_model priority chain even when the test suite is run
    with SWINGY_DRY_RUN=true."""
    import agents.model as m

    monkeypatch.delenv("SWINGY_DRY_RUN", raising=False)
    monkeypatch.setattr(m, "is_dry_run", lambda: False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


@pytest.fixture
def mock_provider():
    with patch("agents.model._get_provider") as mock:
        mock.return_value = MagicMock()
        yield mock


class TestResolveModel:
    @patch.dict(os.environ, {"SWINGY_MODEL_TIER": "cheap"}, clear=False)
    def test_cheap_tier_overrides_everything(self, mock_provider):
        from agents.model import resolve_model

        config = _make_config(model_id="some/model")
        model = resolve_model(config)
        assert "Qwen2.5-7B" in model.model_name

    @patch.dict(
        os.environ,
        {"SWINGY_MODEL_TIER": "production", "EVAL_MODEL_OVERRIDE": "test/eval-model"},
        clear=False,
    )
    def test_eval_override_takes_precedence(self, mock_provider):
        from agents.model import resolve_model

        config = _make_config(model_id="some/model")
        model = resolve_model(config)
        assert model.model_name == "test/eval-model"

    @patch.dict(
        os.environ,
        {"SWINGY_MODEL_TIER": "production"},
        clear=False,
    )
    def test_config_model_id_used(self, mock_provider):
        from agents.model import resolve_model

        os.environ.pop("EVAL_MODEL_OVERRIDE", None)
        config = _make_config(model_id="custom/my-model")
        model = resolve_model(config)
        assert model.model_name == "custom/my-model"

    @patch.dict(
        os.environ,
        {"SWINGY_MODEL_TIER": "production"},
        clear=False,
    )
    def test_missing_model_id_raises(self, mock_provider):
        from agents.model import resolve_model

        os.environ.pop("EVAL_MODEL_OVERRIDE", None)
        config = _make_config(model_id=None, agent_key="my_agent")
        with pytest.raises(ValueError, match="my_agent"):
            resolve_model(config)

    @patch.dict(
        os.environ,
        {"SWINGY_MODEL_TIER": "production"},
        clear=False,
    )
    def test_missing_model_id_error_includes_migration_hint(self, mock_provider):
        from agents.model import resolve_model

        os.environ.pop("EVAL_MODEL_OVERRIDE", None)
        config = _make_config(model_id=None, agent_key="sector_agent")
        with pytest.raises(ValueError, match="no model_id configured"):
            resolve_model(config)


class TestResolveModelWithFallback:
    """Fallback wrapping ensures primary != fallback model."""

    @patch.dict(os.environ, {"SWINGY_MODEL_TIER": "production"}, clear=False)
    def test_normal_config_uses_standard_fallback(self, mock_provider):
        from agents.model import _FALLBACK_MODEL, resolve_model_with_fallback
        from shared.config import LLM_MODEL

        os.environ.pop("EVAL_MODEL_OVERRIDE", None)
        import agents.model as m

        m._primary_healthy = None  # unknown — take normal path

        config = _make_config(model_id=LLM_MODEL)
        model = resolve_model_with_fallback(config)
        # FallbackModel wraps both — fallback should be MiniMax
        assert hasattr(model, "models")
        model_names = [m.model_name for m in model.models]
        assert model_names[0] == LLM_MODEL
        assert model_names[1] == _FALLBACK_MODEL

    @patch.dict(os.environ, {"SWINGY_MODEL_TIER": "production"}, clear=False)
    def test_fallback_model_config_gets_different_fallback(self, mock_provider):
        """When agent IS the fallback model, fallback swaps to primary."""
        from agents.model import _FALLBACK_MODEL, resolve_model_with_fallback
        from shared.config import LLM_MODEL

        os.environ.pop("EVAL_MODEL_OVERRIDE", None)
        import agents.model as m

        m._primary_healthy = None

        config = _make_config(model_id=_FALLBACK_MODEL)
        model = resolve_model_with_fallback(config)
        model_names = [m.model_name for m in model.models]
        assert model_names[0] == _FALLBACK_MODEL
        assert model_names[1] == LLM_MODEL  # swapped — not same model

    @patch.dict(os.environ, {"SWINGY_MODEL_TIER": "production"}, clear=False)
    def test_unhealthy_primary_fallback_model_config_gets_wrapped(self, mock_provider):
        """When primary unhealthy AND agent is fallback model, still wraps with fallback."""
        from agents.model import _FALLBACK_MODEL, resolve_model_with_fallback
        from shared.config import LLM_MODEL

        os.environ.pop("EVAL_MODEL_OVERRIDE", None)
        import agents.model as m

        m._primary_healthy = False

        config = _make_config(model_id=_FALLBACK_MODEL)
        model = resolve_model_with_fallback(config)
        # Should be FallbackModel, NOT bare model
        assert hasattr(model, "models")
        model_names = [m.model_name for m in model.models]
        assert model_names[0] == _FALLBACK_MODEL
        assert model_names[1] == LLM_MODEL
