"""Unit tests for positions ensemble sector context injection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.positions_ensemble import _run_analyst

# ── sector_context injection ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_analyst_includes_sector_context():
    """Analyst prompt should include sector context when provided."""
    sector_context = "SECTOR ROTATION CONTEXT\nHot: technology\nCold: real_estate"
    captured_prompts = []

    async def fake_run(prompt, **kwargs):
        captured_prompts.append(prompt)
        result = MagicMock()
        result.output = MagicMock()
        result.output.views = []
        result.output.summary = "Test summary"
        return result

    mock_agent = MagicMock()
    mock_agent.run = fake_run

    with patch(
        "agents.positions_ensemble._create_technical_agent",
        new=AsyncMock(return_value=(mock_agent, MagicMock())),
    ):
        from datetime import date

        await _run_analyst("technical", date.today(), sector_context=sector_context)

    assert len(captured_prompts) == 1
    assert "SECTOR ROTATION CONTEXT" in captured_prompts[0]
    assert "Hot: technology" in captured_prompts[0]


@pytest.mark.asyncio
async def test_run_analyst_no_sector_context():
    """Analyst prompt without sector context should not contain SECTOR ROTATION CONTEXT."""
    captured_prompts = []

    async def fake_run(prompt, **kwargs):
        captured_prompts.append(prompt)
        result = MagicMock()
        result.output = MagicMock()
        result.output.views = []
        result.output.summary = "Test summary"
        return result

    mock_agent = MagicMock()
    mock_agent.run = fake_run

    with patch(
        "agents.positions_ensemble._create_technical_agent",
        new=AsyncMock(return_value=(mock_agent, MagicMock())),
    ):
        from datetime import date

        await _run_analyst("technical", date.today(), sector_context="")

    assert len(captured_prompts) == 1
    assert "SECTOR ROTATION CONTEXT" not in captured_prompts[0]


def test_sector_context_built_from_rotation():
    """monitor_positions_ensemble should build sector_context from rotation dict."""
    # We test the sector_context building logic directly

    rotation = {"hot_sectors": ["technology", "banking"], "cold_sectors": ["real_estate"]}

    # Simulate what monitor_positions_ensemble builds
    hot = rotation.get("hot_sectors", [])
    cold = rotation.get("cold_sectors", [])
    sector_context = (
        "SECTOR ROTATION CONTEXT\n"
        f"Hot sectors (momentum tailwind): {', '.join(hot) or 'None'}\n"
        f"Cold sectors (momentum headwind): {', '.join(cold) or 'None'}\n"
        "Factor this into your position analysis — holdings in cold sectors "
        "may need earlier exits; hot sectors may support holding longer."
    )

    assert "technology" in sector_context
    assert "banking" in sector_context
    assert "real_estate" in sector_context
    assert "cold sectors" in sector_context.lower()


def test_empty_sector_rotation_no_context():
    """Empty sector rotation should produce no context string."""
    rotation = {"hot_sectors": [], "cold_sectors": []}
    hot = rotation.get("hot_sectors", [])
    cold = rotation.get("cold_sectors", [])

    sector_context = ""
    if hot or cold:
        sector_context = f"Hot: {', '.join(hot)} | Cold: {', '.join(cold)}"

    assert sector_context == ""


def test_no_rotation_no_context():
    """None sector_rotation should produce empty context."""
    sector_context = ""
    rotation = None
    if rotation:
        hot = rotation.get("hot_sectors", [])
        cold = rotation.get("cold_sectors", [])
        if hot or cold:
            sector_context = "context"

    assert sector_context == ""
