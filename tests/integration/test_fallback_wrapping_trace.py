"""Integration test: verify FallbackModel wrapping per agent config.

Closes the Subagent 3 "19 unwrapped agents" false-positive claim with
direct evidence from `resolve_model_with_fallback()`. We sweep every
real agent YAML config and assert:

  - configs with `disable_fallback: true` resolve to a raw OpenRouterModel
    (intentional — see commit `c5b995dd`; MiniMax M2.7 breaks on deeply
    nested Pydantic schemas, so retry storms are worse than no fallback).
  - all other configs resolve to a FallbackModel wrapper.

Done at the resolution layer, NOT via Logfire span attributes — span
attributes can change shape per PydanticAI release; the resolver is the
contract under our control.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openrouter import OpenRouterModel

from shared.agent_config import AgentConfig

CONFIG_DIR = Path(__file__).resolve().parents[2] / "scripts" / "agents" / "configs"


def _all_configs() -> list[AgentConfig]:
    configs: list[AgentConfig] = []
    for yaml_path in sorted(CONFIG_DIR.glob("*.yaml")):
        data = yaml.safe_load(yaml_path.read_text()) or {}
        if not data.get("model_id"):
            continue
        configs.append(
            AgentConfig(
                agent_key=yaml_path.stem,
                system_prompt=data.get("system_prompt") or "",
                model_id=data.get("model_id"),
                temperature=data.get("temperature"),
                max_tokens=data.get("max_tokens"),
                top_p=data.get("top_p"),
                output_retries=data.get("output_retries") or 0,
                model_settings=data.get("model_settings"),
                disable_fallback=bool(data.get("disable_fallback") or False),
            )
        )
    return configs


@pytest.fixture
def healthy_primary(monkeypatch):
    from agents import model as model_module

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(model_module, "_primary_healthy", True)
    monkeypatch.setattr(model_module, "is_dry_run", lambda: False)
    return model_module


@pytest.mark.parametrize("config", _all_configs(), ids=lambda c: c.agent_key)
def test_per_config_wrapping_matches_disable_fallback_flag(config, healthy_primary):
    resolved = healthy_primary.resolve_model_with_fallback(config)
    if config.disable_fallback:
        assert isinstance(resolved, OpenRouterModel), (
            f"{config.agent_key}: disable_fallback=true must resolve to "
            f"raw OpenRouterModel (not {type(resolved).__name__})"
        )
        assert not isinstance(resolved, FallbackModel)
    else:
        assert isinstance(resolved, FallbackModel), (
            f"{config.agent_key}: disable_fallback=false must resolve to "
            f"FallbackModel wrapper (not {type(resolved).__name__})"
        )


def test_known_disable_fallback_set_matches_design():
    """Snapshot: agents intentionally bypassing FallbackModel.

    Updating this set requires CLAUDE.md doc + a comment in `model.py`
    explaining why the schema can't survive a MiniMax M2.7 retry.
    """
    expected = {
        "critic",
        "entry_strategist",
        "positions_aggregator",
        "sector_aggregator",
        "synthesis_holdings",
        "synthesis_picks",
    }
    actual = {c.agent_key for c in _all_configs() if c.disable_fallback}
    assert actual == expected, (
        f"disable_fallback set drift — expected {expected}, got {actual}. "
        f"If intentional, update this test AND scripts/hooks/check_provider_timeouts.py."
    )
