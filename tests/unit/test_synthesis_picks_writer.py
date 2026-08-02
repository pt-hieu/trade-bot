"""Unit tests for synthesis_picks_writer prompt interpolation.

Ensures the dynamic R:R floor from today's strategy directive is
interpolated into every prompt location (MON-2026-04-16-006). Previous
behavior hardcoded three literal `R:R >= 3.0` occurrences that overrode
the directive floor on CAUTIOUS + SUSTAINED PRESSURE days.
"""

from __future__ import annotations

import re
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from agents.synthesis_picks_writer import _run_picks_writer
from shared.agent_config import AgentConfig


@pytest.fixture
def _stub_agent_and_config():
    """Patch agent creation + config loader + runner so the test builds the
    prompt without invoking an LLM. Captures the rendered prompt for
    assertion.
    """
    captured: dict[str, str] = {}

    async def _fake_timeout_runner(agent, prompt, **_kwargs):
        captured["prompt"] = prompt

        class _FakeResult:
            output = "TOP PICKS\n"

        return _FakeResult()

    fake_agent = AsyncMock()

    fake_config = AgentConfig(
        agent_key="synthesis_picks",
        system_prompt="",
        model_id="z-ai/glm-5",
    )
    with (
        patch(
            "agents.synthesis_picks_writer.load_agent_config",
            new=AsyncMock(return_value=fake_config),
        ),
        patch(
            "agents.synthesis_picks_writer.create_agent",
            return_value=fake_agent,
        ),
        patch(
            "agents.synthesis_picks_writer.run_agent_with_total_timeout",
            new=_fake_timeout_runner,
        ),
    ):
        yield captured


async def _run_with_floor(floor: float | None, captured: dict[str, str]) -> str:
    await _run_picks_writer(
        entry_strategy="STANCE: CAUTIOUS",
        sector_results=[],
        pre_computed_picks=None,
        entries_blocked_reason=None,
        trading_mode={"mode": "NORMAL", "reason": "ok"},
        exit_tickers=[],
        scan_date=date(2026, 4, 15),
        min_rr_floor=floor,
    )
    return captured["prompt"]


class TestRrFloorInterpolation:
    @pytest.mark.asyncio
    async def test_directive_floor_3_5_interpolated_three_places(self, _stub_agent_and_config):
        prompt = await _run_with_floor(3.5, _stub_agent_and_config)

        # Three f-string sites: tasks_section no-picks branch, OUTPUT FORMAT
        # caption, and the RULES block.
        matches = re.findall(r"R:R\s*>=\s*3\.5", prompt)
        assert len(matches) >= 3, (
            f"expected 3 `R:R >= 3.5` interpolations, found {len(matches)}: \n{prompt}"
        )
        # And absolutely no stale `R:R >= 3.0` literals.
        assert "R:R >= 3.0" not in prompt, "stale 3.0 literal should not appear when floor=3.5"

    @pytest.mark.asyncio
    async def test_missing_floor_falls_back_to_2_5(self, _stub_agent_and_config):
        """Fallback floor is 2.5 — the MIN_RR_NORMAL default after the
        2026-02-28 anti-conservatism-death-spiral work."""
        prompt = await _run_with_floor(None, _stub_agent_and_config)

        matches = re.findall(r"R:R\s*>=\s*2\.5", prompt)
        assert len(matches) >= 3, f"expected 2.5 fallback, got {matches}"

    @pytest.mark.asyncio
    async def test_directive_floor_4_0_interpolated(self, _stub_agent_and_config):
        prompt = await _run_with_floor(4.0, _stub_agent_and_config)

        assert "R:R >= 4.0" in prompt
        assert "R:R >= 3.0" not in prompt
        assert "R:R >= 3.5" not in prompt
