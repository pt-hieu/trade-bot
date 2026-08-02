"""Degradation handling + fallback precedence for positions_aggregator.

TimeoutError / ProviderUnavailable / unexpected exceptions must not silently
swallow to `{"alerts": []}` for real holdings. Fallback precedence is
EXIT > TRIM > EVALUATE > HOLD with ADD blocked.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from agents.belief_models import TickerBelief
from agents.positions_ensemble_aggregator import aggregate_analyst_reports
from agents.positions_ensemble_fallback import (
    collect_ticker_union,
    derive_alerts_from_subreports,
)
from agents.positions_ensemble_models import AnalystReport, AnalystView
from shared.errors import ProviderUnavailable


def _belief(ticker: str, direction: str = "NEUTRAL") -> TickerBelief:
    return TickerBelief(
        ticker=ticker,
        belief_narrative="test narrative",
        direction=direction,  # type: ignore[arg-type]
        bull_probability=0.33,
        base_probability=0.34,
        bear_probability=0.33,
        price_target_vnd=100000,
        conviction=0.5,
        belief_status="NEW",
    )


def _view(
    ticker: str,
    action: str,
    confidence: int = 6,
    reasoning: str = "Test reasoning.",
    belief: TickerBelief | None = None,
) -> AnalystView:
    return AnalystView(
        ticker=ticker,
        action=action,
        confidence=confidence,
        reasoning=reasoning,
        belief=belief if belief is not None else _belief(ticker),
    )


def _report(views: list[AnalystView], summary: str = "test") -> AnalystReport:
    return AnalystReport(views=views, summary=summary)


class TestDeriveAlertsFromSubreports:
    """Fix 1d — conservative per-ticker action precedence."""

    def test_exit_wins_over_hold(self):
        """When any sub-agent says EXIT, fallback produces EXIT."""
        technical = _report([_view("FPT", "EXIT", confidence=9, reasoning="Stop breached.")])
        value = _report([_view("FPT", "HOLD", confidence=5)])
        thesis = _report([_view("FPT", "HOLD", confidence=5)])

        result = derive_alerts_from_subreports(
            technical=technical,
            value=value,
            thesis=thesis,
            degradation_type="TimeoutError",
        )

        assert len(result["alerts"]) == 1
        alert = result["alerts"][0]
        assert alert["ticker"] == "FPT"
        assert alert["action"] == "EXIT"
        assert alert["urgency"] == "high"  # confidence 9 → high
        assert "[DERIVED_FROM_BELIEFS]" in alert["reason"]
        # Degradation provenance moved out of the reader-facing `reason`
        # into an internal `source_note` (Group 6 / MON-2026-04-19-008 fix).
        assert "TimeoutError" in alert["source_note"]

    def test_trim_wins_over_hold_and_add(self):
        """TRIM beats HOLD/ADD in fallback precedence."""
        technical = _report([_view("TCB", "ADD", confidence=8)])
        value = _report([_view("TCB", "TRIM", confidence=7)])
        thesis = _report([_view("TCB", "HOLD", confidence=5)])

        result = derive_alerts_from_subreports(
            technical=technical,
            value=value,
            thesis=thesis,
            degradation_type="ProviderUnavailable",
        )

        assert result["alerts"][0]["action"] == "TRIM"

    def test_add_is_collapsed_to_hold(self):
        """Fallback never emits ADD — even if all 3 sub-agents agree."""
        technical = _report([_view("MWG", "ADD", confidence=9)])
        value = _report([_view("MWG", "ADD", confidence=8)])
        thesis = _report([_view("MWG", "ADD", confidence=9)])

        result = derive_alerts_from_subreports(
            technical=technical,
            value=value,
            thesis=thesis,
            degradation_type="TimeoutError",
        )

        assert result["alerts"][0]["action"] == "HOLD"

    def test_all_hold_yields_hold(self):
        """Unanimous HOLD → HOLD."""
        technical = _report([_view("VCB", "HOLD", confidence=5)])
        value = _report([_view("VCB", "HOLD", confidence=5)])
        thesis = _report([_view("VCB", "HOLD", confidence=4)])

        result = derive_alerts_from_subreports(
            technical=technical,
            value=value,
            thesis=thesis,
            degradation_type="TimeoutError",
        )

        assert result["alerts"][0]["action"] == "HOLD"

    def test_counter_thesis_captured_from_dissenter(self):
        """Non-dominant dissenting view populates counter_thesis."""
        technical = _report(
            [_view("HPG", "EXIT", confidence=9, reasoning="Stop breached on volume.")]
        )
        value = _report(
            [_view("HPG", "HOLD", confidence=6, reasoning="Fair value intact, drop is noise.")]
        )
        thesis = _report([_view("HPG", "EXIT", confidence=5, reasoning="Thesis weakening.")])

        result = derive_alerts_from_subreports(
            technical=technical,
            value=value,
            thesis=thesis,
            degradation_type="TimeoutError",
        )

        counter = result["alerts"][0]["counter_thesis"]
        assert counter is not None
        assert "Fair value" in counter

    def test_beliefs_are_passed_through(self):
        """Sub-agent beliefs survive the fallback path."""
        tech_belief = _belief("VHM", "BULLISH")
        val_belief = _belief("VHM", "NEUTRAL")

        technical = _report([_view("VHM", "ADD", confidence=7, belief=tech_belief)])
        value = _report([_view("VHM", "HOLD", confidence=6, belief=val_belief)])
        thesis = _report([_view("VHM", "HOLD", confidence=5)])

        result = derive_alerts_from_subreports(
            technical=technical,
            value=value,
            thesis=thesis,
            degradation_type="TimeoutError",
        )

        beliefs = result["beliefs"]
        agents = {b["agent_key"] for b in beliefs}
        assert "positions_technical" in agents
        assert "positions_value" in agents

    def test_multiple_tickers_each_get_alert(self):
        """Fallback produces one alert per unique ticker across all reports."""
        technical = _report(
            [
                _view("FPT", "EXIT", confidence=9),
                _view("TCB", "HOLD", confidence=5),
            ]
        )
        value = _report(
            [
                _view("FPT", "HOLD", confidence=5),
                _view("TCB", "HOLD", confidence=5),
            ]
        )
        thesis = _report(
            [
                _view("FPT", "HOLD", confidence=4),
                _view("TCB", "TRIM", confidence=6),
            ]
        )

        result = derive_alerts_from_subreports(
            technical=technical,
            value=value,
            thesis=thesis,
            degradation_type="TimeoutError",
        )

        actions_by_ticker = {a["ticker"]: a["action"] for a in result["alerts"]}
        assert actions_by_ticker == {"FPT": "EXIT", "TCB": "TRIM"}


class TestCollectTickerUnion:
    def test_union_across_reports(self):
        technical = _report([_view("A", "HOLD"), _view("B", "HOLD")])
        value = _report([_view("B", "HOLD"), _view("C", "HOLD")])
        thesis = _report([_view("A", "HOLD")])

        assert collect_ticker_union(technical, value, thesis) == {"A", "B", "C"}

    def test_lowercase_tickers_are_uppercased(self):
        technical = _report([_view("fpt", "HOLD")])
        value = _report([])
        thesis = _report([])

        assert collect_ticker_union(technical, value, thesis) == {"FPT"}


class TestAggregateAnalystReportsDegradation:
    """Fix 1d — end-to-end degradation handling in aggregate_analyst_reports."""

    @pytest.fixture
    def three_reports(self):
        technical = _report([_view("FPT", "EXIT", confidence=8, reasoning="Stop breached.")])
        value = _report([_view("FPT", "HOLD", confidence=5, reasoning="Still cheap.")])
        thesis = _report([_view("FPT", "HOLD", confidence=4, reasoning="Thesis intact.")])
        return technical, value, thesis

    @pytest.mark.asyncio
    async def test_timeout_error_falls_back_to_sub_reports(self, three_reports):
        """TimeoutError → derive_alerts_from_subreports is called."""
        technical, value, thesis = three_reports

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(side_effect=TimeoutError("phase wall"))

        with (
            patch(
                "agents.positions_ensemble_aggregator.create_agent",
                return_value=mock_agent,
            ),
            patch("agents.positions_ensemble_aggregator.load_agent_config", AsyncMock()),
        ):
            result = await aggregate_analyst_reports(
                technical,
                value,
                thesis,
                scan_date=date.today(),
            )

        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["ticker"] == "FPT"
        assert result["alerts"][0]["action"] == "EXIT"
        assert "[DERIVED_FROM_BELIEFS]" in result["summary"]
        assert "TimeoutError" in result["summary"]

    @pytest.mark.asyncio
    async def test_provider_unavailable_falls_back(self, three_reports):
        """ProviderUnavailable → fallback path."""
        technical, value, thesis = three_reports

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(side_effect=ProviderUnavailable("kimi down"))

        with (
            patch(
                "agents.positions_ensemble_aggregator.create_agent",
                return_value=mock_agent,
            ),
            patch("agents.positions_ensemble_aggregator.load_agent_config", AsyncMock()),
        ):
            result = await aggregate_analyst_reports(
                technical,
                value,
                thesis,
                scan_date=date.today(),
            )

        assert len(result["alerts"]) == 1
        assert "ProviderUnavailable" in result["summary"]

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_structured_error(self, three_reports):
        """Unexpected exception → returns error dict but never re-raises."""
        technical, value, thesis = three_reports

        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(side_effect=ValueError("unexpected parse failure"))

        with (
            patch(
                "agents.positions_ensemble_aggregator.create_agent",
                return_value=mock_agent,
            ),
            patch("agents.positions_ensemble_aggregator.load_agent_config", AsyncMock()),
        ):
            result = await aggregate_analyst_reports(
                technical,
                value,
                thesis,
                scan_date=date.today(),
            )

        assert result["alerts"] == []
        assert "error" in result
        assert "unexpected parse failure" in result["error"]
