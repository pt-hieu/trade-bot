"""Emit-presence tests for belief_models._normalize_belief_probabilities (SWI-206)."""

from __future__ import annotations

from agents.belief_models import TickerBelief


def _make(**overrides) -> dict:
    base = {
        "ticker": "FPT",
        "belief_narrative": "neutral on near-term",
        "direction": "NEUTRAL",
        "bull_probability": 0.30,
        "base_probability": 0.50,
        "bear_probability": 0.20,
        "price_target_vnd": 50000,
        "timeframe_days": 5,
        "conviction": 0.5,
        "belief_status": "NEW",
    }
    base.update(overrides)
    return base


def test_percentage_rescue_emits(capture_emits: list[dict]) -> None:
    TickerBelief(**_make(bull_probability=30, base_probability=50, bear_probability=20))
    assert any(
        e["rule_id"] == "belief_probabilities" and e["reason"] == "percentage_rescue"
        for e in capture_emits
    )


def test_garbage_fallback_emits(capture_emits: list[dict]) -> None:
    TickerBelief(**_make(bull_probability=0.05, base_probability=0.05, bear_probability=0.05))
    assert any(e["reason"] == "garbage_fallback" for e in capture_emits)


def test_direction_correction_emits(capture_emits: list[dict]) -> None:
    # bull > 0.4 → BULLISH expected; declared NEUTRAL → correction.
    TickerBelief(
        **_make(
            direction="NEUTRAL",
            bull_probability=0.55,
            base_probability=0.30,
            bear_probability=0.15,
        )
    )
    assert any(e["reason"] == "direction_correction" for e in capture_emits)


def test_normal_belief_no_emit(capture_emits: list[dict]) -> None:
    TickerBelief(**_make())
    # Sum is 1.0, direction matches, no correction expected.
    assert capture_emits == []
