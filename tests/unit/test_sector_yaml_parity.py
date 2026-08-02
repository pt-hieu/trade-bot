"""Sibling-config parity for sector_*.yaml retry-guardrail include.

Mirrors `scripts/hooks/check_sector_yaml_guardrail_parity.py`. Tool-using
sector configs MUST include the shared `tool_retry_guardrail` fragment;
inject-only configs (sector_technical) are explicitly exempt.
"""

from __future__ import annotations

from pathlib import Path

import pytest

CONFIGS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "agents" / "configs"

TOOL_USING = ("sector_news", "sector_enrichment", "sector_rotation")
INJECT_ONLY = ("sector_technical", "sector_aggregator")
INCLUDE_DIRECTIVE = "{{include: tool_retry_guardrail}}"


@pytest.mark.parametrize("agent_key", TOOL_USING)
def test_tool_using_sector_configs_include_retry_guardrail(agent_key: str) -> None:
    path = CONFIGS_DIR / f"{agent_key}.yaml"
    assert path.exists(), f"missing config {path}"
    text = path.read_text()
    assert INCLUDE_DIRECTIVE in text, (
        f"{path} missing '{INCLUDE_DIRECTIVE}' — sibling parity rule "
        "(scripts/hooks/check_sector_yaml_guardrail_parity.py)."
    )


@pytest.mark.parametrize("agent_key", INJECT_ONLY)
def test_inject_only_sector_configs_omit_retry_guardrail(agent_key: str) -> None:
    """sector_technical is intentionally inject-only — adding the include
    would invite spurious tool calls."""
    path = CONFIGS_DIR / f"{agent_key}.yaml"
    assert path.exists()
    text = path.read_text()
    assert INCLUDE_DIRECTIVE not in text, (
        f"{path} unexpectedly includes '{INCLUDE_DIRECTIVE}' — "
        "this config is inject-only by design."
    )
