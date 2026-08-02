"""Lock-in for the synthesis_holdings empty-theses guard.

2026-04-28 fragility class: pydantic accepted ``HoldingsTheses(theses=[])``
because the field carries ``default_factory=list``, so an LLM that drafted
paragraphs in its thinking block but failed to emit them in the final
structured output silently shipped a degraded brief.

The guard makes empty theses a structured-output failure — first
attempt retries; second attempt raises ``EmptyStructuredOutputError`` so
the caller's existing fallback path triggers loudly.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from agents.synthesis_writers import (
    EmptyStructuredOutputError,
    HoldingsTheses,
    ThesisParagraph,
    _run_holdings_writer,
)


@pytest.mark.asyncio
async def test_empty_paragraphs_first_attempt_retries_then_succeeds() -> None:
    """First-attempt empty payload must retry; if attempt 2 returns content, succeed."""
    empty_result = type("R", (), {"output": HoldingsTheses(theses=[])})()
    populated_result = type(
        "R",
        (),
        {"output": HoldingsTheses(theses=[ThesisParagraph(ticker="FPT", paragraph="thesis")])},
    )()

    runner = AsyncMock(side_effect=[empty_result, populated_result])

    with (
        patch("agents.synthesis_writers.load_agent_config", new=AsyncMock(return_value=object())),
        patch("agents.synthesis_writers.create_agent", return_value=object()),
        patch("agents.synthesis_writers.build_usage_limits", return_value=None),
        patch("agents.synthesis_writers.run_agent_with_total_timeout", new=runner),
    ):
        output = await _run_holdings_writer(
            held_actions=[],
            position_alerts=None,
            correlation=None,
            trading_mode=None,
            flow_context="",
            scan_date=date(2026, 4, 28),
        )

    assert runner.await_count == 2
    assert [(t.ticker, t.paragraph) for t in output.theses] == [("FPT", "thesis")]


@pytest.mark.asyncio
async def test_empty_paragraphs_second_attempt_raises_empty_structured_output_error() -> None:
    """Two empty attempts in a row must raise so the caller's fallback fires."""
    empty_result = type("R", (), {"output": HoldingsTheses(theses=[])})()

    runner = AsyncMock(side_effect=[empty_result, empty_result])

    with (
        patch("agents.synthesis_writers.load_agent_config", new=AsyncMock(return_value=object())),
        patch("agents.synthesis_writers.create_agent", return_value=object()),
        patch("agents.synthesis_writers.build_usage_limits", return_value=None),
        patch("agents.synthesis_writers.run_agent_with_total_timeout", new=runner),
        pytest.raises(EmptyStructuredOutputError),
    ):
        await _run_holdings_writer(
            held_actions=[],
            position_alerts=None,
            correlation=None,
            trading_mode=None,
            flow_context="",
            scan_date=date(2026, 4, 28),
        )

    assert runner.await_count == 2
