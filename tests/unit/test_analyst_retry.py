"""Retry-parity tests for positions_ensemble._run_analyst.

Ported from sector_analysts retry pattern (2026-04-20 silent-hang fix).
Positions ensemble was missing the 2-attempt retry that sector analysts
have used successfully in prod (e.g. retry on transient provider stalls).
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.positions_ensemble import _run_analyst


def _make_successful_result(views=None, summary="OK"):
    result = MagicMock()
    result.output = MagicMock()
    result.output.views = views or []
    result.output.summary = summary
    return result


@pytest.mark.asyncio
async def test_timeout_on_attempt_1_succeeds_on_attempt_2():
    """First attempt times out, second succeeds → agent returns successful report."""
    call_count = {"n": 0}

    async def fake_run(prompt, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise TimeoutError("simulated silent hang")
        return _make_successful_result(summary="attempt 2 succeeded")

    mock_agent = MagicMock()
    mock_agent.run = fake_run

    async def fake_wait_for(coro, timeout):
        # Propagate the underlying exception instead of the real timeout race.
        return await coro

    with (
        patch(
            "agents.positions_ensemble._create_technical_agent",
            new=AsyncMock(return_value=(mock_agent, MagicMock())),
        ),
        patch("agents.positions_ensemble.asyncio.wait_for", side_effect=fake_wait_for),
        patch("agents.positions_ensemble.emit_silent_provider_hang_span"),
    ):
        report = await _run_analyst("technical", date.today())

    assert call_count["n"] == 2, "should have retried once after TimeoutError"
    assert report.summary == "attempt 2 succeeded"


@pytest.mark.asyncio
async def test_timeout_on_both_attempts_returns_empty_report():
    """Both attempts time out → agent returns empty-views error report (no raise)."""
    call_count = {"n": 0}

    async def fake_run(prompt, **kwargs):
        call_count["n"] += 1
        raise TimeoutError("simulated silent hang")

    mock_agent = MagicMock()
    mock_agent.run = fake_run

    async def fake_wait_for(coro, timeout):
        return await coro

    with (
        patch(
            "agents.positions_ensemble._create_value_agent",
            new=AsyncMock(return_value=(mock_agent, MagicMock())),
        ),
        patch("agents.positions_ensemble.asyncio.wait_for", side_effect=fake_wait_for),
        patch("agents.positions_ensemble.emit_silent_provider_hang_span"),
    ):
        report = await _run_analyst("value", date.today())

    assert call_count["n"] == 2
    assert report.views == []
    assert "timed out after 2 attempts" in report.summary


@pytest.mark.asyncio
async def test_transient_exception_on_attempt_1_retries():
    """Generic transient exception triggers retry, then success on attempt 2."""
    call_count = {"n": 0}

    async def fake_run(prompt, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("transient network flake")
        return _make_successful_result(summary="recovered")

    mock_agent = MagicMock()
    mock_agent.run = fake_run

    async def fake_wait_for(coro, timeout):
        return await coro

    with (
        patch(
            "agents.positions_ensemble._create_thesis_agent",
            new=AsyncMock(return_value=(mock_agent, MagicMock())),
        ),
        patch("agents.positions_ensemble.asyncio.wait_for", side_effect=fake_wait_for),
        patch("agents.positions_ensemble.asyncio.sleep", return_value=None),
    ):
        report = await _run_analyst("thesis", date.today())

    assert call_count["n"] == 2
    assert report.summary == "recovered"


@pytest.mark.asyncio
async def test_success_on_first_attempt_no_retry():
    """Happy path — single attempt, no retry logic triggered."""
    call_count = {"n": 0}

    async def fake_run(prompt, **kwargs):
        call_count["n"] += 1
        return _make_successful_result(summary="first try")

    mock_agent = MagicMock()
    mock_agent.run = fake_run

    async def fake_wait_for(coro, timeout):
        return await coro

    with (
        patch(
            "agents.positions_ensemble._create_technical_agent",
            new=AsyncMock(return_value=(mock_agent, MagicMock())),
        ),
        patch("agents.positions_ensemble.asyncio.wait_for", side_effect=fake_wait_for),
    ):
        report = await _run_analyst("technical", date.today())

    assert call_count["n"] == 1
    assert report.summary == "first try"


@pytest.mark.asyncio
async def test_schema_error_reraises_without_retry():
    """Pydantic ValidationError / UnexpectedModelBehavior should re-raise, not retry.

    PydanticAI already retried output_retries=2 times internally before the
    schema error surfaced — an outer retry with the same model + prompt
    produces the same failure."""
    from pydantic_ai.exceptions import UnexpectedModelBehavior

    call_count = {"n": 0}

    async def fake_run(prompt, **kwargs):
        call_count["n"] += 1
        raise UnexpectedModelBehavior("schema mismatch")

    mock_agent = MagicMock()
    mock_agent.run = fake_run

    async def fake_wait_for(coro, timeout):
        return await coro

    with (
        patch(
            "agents.positions_ensemble._create_value_agent",
            new=AsyncMock(return_value=(mock_agent, MagicMock())),
        ),
        patch("agents.positions_ensemble.asyncio.wait_for", side_effect=fake_wait_for),
        pytest.raises(UnexpectedModelBehavior),
    ):
        await _run_analyst("value", date.today())

    assert call_count["n"] == 1, "schema errors must NOT retry"


@pytest.mark.asyncio
async def test_usage_limit_exceeded_returns_early_no_retry():
    """UsageLimitExceeded is deterministic — retry would fail identically."""
    from pydantic_ai.exceptions import UsageLimitExceeded

    call_count = {"n": 0}

    async def fake_run(prompt, **kwargs):
        call_count["n"] += 1
        raise UsageLimitExceeded("request_limit exceeded")

    mock_agent = MagicMock()
    mock_agent.run = fake_run

    async def fake_wait_for(coro, timeout):
        return await coro

    with (
        patch(
            "agents.positions_ensemble._create_thesis_agent",
            new=AsyncMock(return_value=(mock_agent, MagicMock())),
        ),
        patch("agents.positions_ensemble.asyncio.wait_for", side_effect=fake_wait_for),
    ):
        report = await _run_analyst("thesis", date.today())

    assert call_count["n"] == 1, "usage-limit errors must NOT retry"
    assert report.views == []
    assert "usage limit" in report.summary.lower()
