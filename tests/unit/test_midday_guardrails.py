"""Tests for midday deterministic guardrails — DEFENSIVE + ADX gates."""

from agents.midday import MiddayQualitative, RecommendationOverride
from agents.midday_guardrails import apply_defensive_gate, apply_downtrend_gate


def _make_qualitative(existing_overrides: list[RecommendationOverride] | None = None):
    return MiddayQualitative(
        morning_reflection="test",
        afternoon_plan=[],
        capital_note="test",
        recommendation_overrides=list(existing_overrides or []),
    )


class TestDefensiveGate:
    """DEFENSIVE stance blocks ADD/BUY/LIMIT_BUY."""

    def test_defensive_cancels_add(self):
        qualitative = _make_qualitative()
        recs = [{"ticker": "FPT", "action": "ADD"}]
        precomputed = {
            "strategy_directive": {"directive": "DEFENSIVE — VIX 31 confirms elevated risk"}
        }
        apply_defensive_gate(qualitative, recs, precomputed)
        assert len(qualitative.recommendation_overrides) == 1
        assert qualitative.recommendation_overrides[0].ticker == "FPT"
        assert qualitative.recommendation_overrides[0].midday_status == "CANCEL"

    def test_defensive_cancels_buy(self):
        qualitative = _make_qualitative()
        recs = [{"ticker": "MWG", "action": "BUY"}]
        precomputed = {"strategy_directive": {"directive": "STANCE\nDEFENSIVE — deploy 0.75x"}}
        apply_defensive_gate(qualitative, recs, precomputed)
        assert len(qualitative.recommendation_overrides) == 1
        assert qualitative.recommendation_overrides[0].midday_status == "CANCEL"

    def test_defensive_ignores_hold(self):
        qualitative = _make_qualitative()
        recs = [{"ticker": "TCB", "action": "HOLD"}]
        precomputed = {"strategy_directive": {"directive": "DEFENSIVE stance active"}}
        apply_defensive_gate(qualitative, recs, precomputed)
        assert len(qualitative.recommendation_overrides) == 0

    def test_non_defensive_allows_add(self):
        qualitative = _make_qualitative()
        recs = [{"ticker": "FPT", "action": "ADD"}]
        precomputed = {"strategy_directive": {"directive": "AGGRESSIVE — deploy full capital"}}
        apply_defensive_gate(qualitative, recs, precomputed)
        assert len(qualitative.recommendation_overrides) == 0

    def test_existing_override_not_duplicated(self):
        existing = [
            RecommendationOverride(
                ticker="FPT", morning_action="ADD", midday_status="CANCEL", reason="LLM cancelled"
            )
        ]
        qualitative = _make_qualitative(existing)
        recs = [{"ticker": "FPT", "action": "ADD"}]
        precomputed = {"strategy_directive": {"directive": "DEFENSIVE stance"}}
        apply_defensive_gate(qualitative, recs, precomputed)
        assert len(qualitative.recommendation_overrides) == 1

    def test_none_directive_is_safe(self):
        qualitative = _make_qualitative()
        recs = [{"ticker": "FPT", "action": "ADD"}]
        apply_defensive_gate(qualitative, recs, {})
        assert len(qualitative.recommendation_overrides) == 0


class TestDowntrendGate:
    """ADX > 35 + Supertrend DOWN blocks ADD/BUY."""

    def test_strong_downtrend_cancels_add(self):
        qualitative = _make_qualitative()
        recs = [{"ticker": "FPT", "action": "ADD"}]
        # Flat canonical shape — see shared/api/technicals.py::get_technicals.
        precomputed = {
            "held_technicals": {
                "FPT": {
                    "adx": 44.0,
                    "adx_dmp": 12.0,
                    "adx_dmn": 37.0,
                    "supertrend_direction": "DOWN",
                }
            }
        }
        apply_downtrend_gate(qualitative, recs, precomputed)
        assert len(qualitative.recommendation_overrides) == 1
        assert qualitative.recommendation_overrides[0].midday_status == "CANCEL"
        assert "ADX 44" in qualitative.recommendation_overrides[0].reason

    def test_weak_trend_allows_add(self):
        qualitative = _make_qualitative()
        recs = [{"ticker": "FPT", "action": "ADD"}]
        precomputed = {
            "held_technicals": {
                "FPT": {
                    "adx": 20.0,
                    "adx_dmp": 15.0,
                    "adx_dmn": 18.0,
                    "supertrend_direction": "DOWN",
                }
            }
        }
        apply_downtrend_gate(qualitative, recs, precomputed)
        assert len(qualitative.recommendation_overrides) == 0

    def test_uptrend_allows_add(self):
        qualitative = _make_qualitative()
        recs = [{"ticker": "FPT", "action": "ADD"}]
        precomputed = {
            "held_technicals": {
                "FPT": {
                    "adx": 44.0,
                    "adx_dmp": 37.0,
                    "adx_dmn": 12.0,
                    "supertrend_direction": "UP",
                }
            }
        }
        apply_downtrend_gate(qualitative, recs, precomputed)
        assert len(qualitative.recommendation_overrides) == 0

    def test_missing_technicals_is_safe(self):
        qualitative = _make_qualitative()
        recs = [{"ticker": "FPT", "action": "ADD"}]
        apply_downtrend_gate(qualitative, recs, {})
        assert len(qualitative.recommendation_overrides) == 0

    def test_hold_not_affected(self):
        qualitative = _make_qualitative()
        recs = [{"ticker": "FPT", "action": "HOLD"}]
        precomputed = {
            "held_technicals": {
                "FPT": {
                    "adx": 50.0,
                    "adx_dmp": 10.0,
                    "adx_dmn": 40.0,
                    "supertrend_direction": "DOWN",
                }
            }
        }
        apply_downtrend_gate(qualitative, recs, precomputed)
        assert len(qualitative.recommendation_overrides) == 0
