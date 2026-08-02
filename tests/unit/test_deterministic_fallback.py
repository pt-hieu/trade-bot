"""Unit tests for _build_deterministic_fallback() in phase_strategy.

The fallback now consumes the shared `RecommendationGateDecision` rather
than re-deriving a regime-based stance inline. `entries_allowed=False`
drives the DEFENSIVE path; `entries_allowed=True` (or `None`) drives the
NEUTRAL path with a composed floor + max_entries.
"""

from pipeline.phase_strategy import _build_deterministic_fallback
from pipeline.types import Phase1Result, Phase2Result
from shared.rules.recommendation_gate import compose_recommendation_gate

_STUB_SECTIONS = "## GOAL PROGRESS\n(stub)\n\n## ENTRY CRITERIA TODAY\n(stub)"
_STUB_FAILURE = "stub-failure-reason"


def _gate(
    *,
    trading_mode: str = "NORMAL",
    global_risk_regime: str = "CALM",
    urgency_min_rr: float = 2.5,
    urgency_max_picks: int = 1,
    underlying_stress: bool = False,
    strategy_director_failed: bool = False,
):
    return compose_recommendation_gate(
        trading_mode=trading_mode,
        market_regime="NEUTRAL",
        global_risk_regime=global_risk_regime,
        urgency_tier="NORMAL",
        urgency_min_rr=urgency_min_rr,
        urgency_max_picks=urgency_max_picks,
        underlying_stress=underlying_stress,
        strategy_director_failed=strategy_director_failed,
    )


def _build(phase1: Phase1Result, phase2: Phase2Result, gate=None) -> tuple[str, str, dict]:
    return _build_deterministic_fallback(phase1, phase2, _STUB_SECTIONS, _STUB_FAILURE, gate)


def _make_phase1(regime: str | None = "NEUTRAL", global_risk_regime: str = "CALM") -> Phase1Result:
    return Phase1Result(
        market_level={"regime": regime} if regime is not None else None,
        macro_metrics={"global_risk_regime": global_risk_regime},
    )


def _make_phase2(alerts: list[dict] | None = None) -> Phase2Result:
    return Phase2Result(position_alerts={"alerts": alerts if alerts is not None else []})


def _alert(ticker: str = "TCB", action: str = "EXIT", reason: str = "Stop breached") -> dict:
    return {"ticker": ticker, "action": action, "reason": reason}


class TestBlockedEntriesDefensive:
    """`entries_allowed=False` drives DEFENSIVE with zero budget and max_entries=0."""

    def test_crisis_block(self):
        gate = _gate(global_risk_regime="CRISIS")
        position_guidance, entry_strategy, constraints = _build(
            _make_phase1(regime="RISK_OFF"), _make_phase2(), gate
        )
        assert "DEFENSIVE" in entry_strategy
        assert constraints["budget_vnd"] == 0
        assert constraints["max_new_entries"] == 0
        assert constraints["min_rr"] == gate.effective_rr_floor

    def test_low_cash_block(self):
        gate = _gate(trading_mode="LOW_CASH")
        _, entry_strategy, constraints = _build(_make_phase1(), _make_phase2(), gate)
        assert "DEFENSIVE" in entry_strategy
        assert constraints["budget_vnd"] == 0
        assert constraints["max_new_entries"] == 0

    def test_strategy_failed_stressed_block(self):
        gate = _gate(
            global_risk_regime="ELEVATED",
            underlying_stress=True,
            strategy_director_failed=True,
        )
        _, entry_strategy, constraints = _build(_make_phase1(), _make_phase2(), gate)
        assert "DEFENSIVE" in entry_strategy
        assert constraints["max_new_entries"] == 0


class TestAllowedEntriesNeutral:
    """`entries_allowed=True` drives the NEUTRAL conservative-budget path."""

    def test_calm_allows_neutral(self):
        gate = _gate(urgency_min_rr=2.5, urgency_max_picks=3)
        _, entry_strategy, constraints = _build(_make_phase1(), _make_phase2(), gate)
        assert "NEUTRAL" in entry_strategy
        assert constraints["budget_vnd"] == 50_000_000
        assert constraints["max_new_entries"] == 3
        assert constraints["min_rr"] == gate.effective_rr_floor

    def test_elevated_shock_only_uses_relaxed_floor(self):
        gate = _gate(global_risk_regime="ELEVATED", underlying_stress=False)
        _, _, constraints = _build(_make_phase1(), _make_phase2(), gate)
        assert constraints["min_rr"] == 2.5

    def test_elevated_stressed_uses_full_floor(self):
        gate = _gate(global_risk_regime="ELEVATED", underlying_stress=True)
        _, _, constraints = _build(_make_phase1(), _make_phase2(), gate)
        assert constraints["min_rr"] == 3.0


class TestNoneGateFallback:
    """Missing gate_decision must still produce a sane NEUTRAL stance."""

    def test_no_gate_defaults_to_neutral(self):
        _, entry_strategy, constraints = _build(_make_phase1(), _make_phase2(), None)
        assert "NEUTRAL" in entry_strategy
        assert constraints["budget_vnd"] == 50_000_000
        assert constraints["max_new_entries"] == 1
        assert constraints["min_rr"] == 3.0


class TestPositionAlerts:
    def test_position_alerts_included(self):
        gate = _gate()
        position_guidance, _, _ = _build(
            _make_phase1(),
            _make_phase2(
                alerts=[
                    _alert(ticker="TCB", action="EXIT", reason="Stop breached at 34000"),
                    _alert(ticker="FPT", action="REDUCE", reason="Target 90% hit"),
                ]
            ),
            gate,
        )
        assert "TCB" in position_guidance and "EXIT" in position_guidance
        assert "FPT" in position_guidance and "REDUCE" in position_guidance

    def test_alert_reason_included(self):
        gate = _gate()
        position_guidance, _, _ = _build(
            _make_phase1(),
            _make_phase2(
                alerts=[_alert(ticker="VHM", action="MONITOR", reason="Approaching resistance")]
            ),
            gate,
        )
        assert "Approaching resistance" in position_guidance

    def test_long_reason_truncated(self):
        gate = _gate()
        position_guidance, _, _ = _build(
            _make_phase1(), _make_phase2(alerts=[_alert(reason="A" * 100)]), gate
        )
        assert "A" * 80 in position_guidance
        assert "A" * 81 not in position_guidance

    def test_no_alerts_shows_fallback(self):
        gate = _gate()
        position_guidance, _, _ = _build(_make_phase1(), _make_phase2(alerts=[]), gate)
        assert "No position alerts" in position_guidance

    def test_missing_ticker_question_mark(self):
        gate = _gate()
        position_guidance, _, _ = _build(
            _make_phase1(),
            _make_phase2(alerts=[{"action": "EXIT", "reason": "Unknown ticker"}]),
            gate,
        )
        assert "?" in position_guidance

    def test_missing_action_defaults_monitor(self):
        gate = _gate()
        position_guidance, _, _ = _build(
            _make_phase1(),
            _make_phase2(alerts=[{"ticker": "TCB", "reason": "Watching"}]),
            gate,
        )
        assert "MONITOR" in position_guidance


class TestNoneMarketLevel:
    """None market_level must fall through to CAUTIOUS default (no crash)."""

    def test_none_market_level(self):
        gate = _gate()
        phase1 = Phase1Result(market_level=None, macro_metrics={"global_risk_regime": "CALM"})
        _, entry_strategy, constraints = _build(phase1, _make_phase2(), gate)
        assert "CAUTIOUS" in entry_strategy
        assert constraints["budget_vnd"] == 50_000_000

    def test_none_position_alerts(self):
        gate = _gate()
        phase1 = _make_phase1()
        phase2 = Phase2Result(position_alerts=None)
        position_guidance, _, _ = _build(phase1, phase2, gate)
        assert "No position alerts" in position_guidance
