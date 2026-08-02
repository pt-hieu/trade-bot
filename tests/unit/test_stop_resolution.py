"""Unit tests for `shared.rules.stop_resolution.resolve_stop_for_rec`.

Precedence invariant (highest wins):
    ATR_TRAIL > SWING breakeven > LONGTERM catastrophic > brief-explicit > None

Includes named regression for ACV 2026-04-24: a held SWING position with
breakeven_stop=44910 and no brief-explicit stop must resolve to
ResolvedStop(44910, "BREAKEVEN_HOLDING", "SWING"). Before this contract
the DB persisted stop_price_vnd=NULL for ACV and retro evaluated
`stop_hit = bool(None)` which is trivially False regardless of price action.
"""

from __future__ import annotations

import pytest

from shared.rules.stop_resolution import (
    ResolvedStop,
    StopResolutionInput,
    resolve_stop_for_rec,
)


def test_acv_2026_04_24_regression_swing_breakeven():
    """ACV held SWING with breakeven_stop=44910, no brief stop → BREAKEVEN_HOLDING."""
    holding: StopResolutionInput = {
        "ticker": "ACV",
        "plan_type": "SWING",
        "breakeven_stop": 44910,
        "catastrophic_stop": None,
    }
    result = resolve_stop_for_rec(
        plan_type="SWING",
        holding=holding,
        brief_stop_vnd=None,
        atr_trail_state=None,
    )
    assert result == ResolvedStop(price_vnd=44910, source="BREAKEVEN_HOLDING", plan_type="SWING")


def test_atr_trail_beats_swing_breakeven():
    """Active ATR trail above entry takes precedence over breakeven."""
    holding: StopResolutionInput = {
        "ticker": "FPT",
        "plan_type": "SWING",
        "breakeven_stop": 93000,
    }
    trail_state = {"strategy": "MOMENTUM", "stop_price": 98500, "entry_price": 93000}
    result = resolve_stop_for_rec(
        plan_type="SWING",
        holding=holding,
        brief_stop_vnd=None,
        atr_trail_state=trail_state,  # type: ignore[arg-type]
    )
    assert result is not None
    assert result.source == "ATR_TRAIL"
    assert result.price_vnd == 98500


def test_non_trail_strategy_falls_through_to_breakeven():
    """A non-trail strategy (FIXED_TARGET-style) does not claim ATR_TRAIL precedence."""
    holding: StopResolutionInput = {
        "ticker": "TCB",
        "plan_type": "SWING",
        "breakeven_stop": 30000,
    }
    stale_state = {"strategy": "MEAN_REVERSION", "stop_price": 31000}
    result = resolve_stop_for_rec(
        plan_type="SWING",
        holding=holding,
        brief_stop_vnd=None,
        atr_trail_state=stale_state,  # type: ignore[arg-type]
    )
    assert result is not None
    assert result.source == "BREAKEVEN_HOLDING"
    assert result.price_vnd == 30000


def test_longterm_catastrophic_floor():
    """LONGTERM holding uses catastrophic_stop, not breakeven."""
    holding: StopResolutionInput = {
        "ticker": "VHM",
        "plan_type": "LONGTERM",
        "catastrophic_stop": 40000,
    }
    result = resolve_stop_for_rec(
        plan_type="LONGTERM",
        holding=holding,
        brief_stop_vnd=None,
        atr_trail_state=None,
    )
    assert result == ResolvedStop(
        price_vnd=40000, source="CATASTROPHIC_FLOOR", plan_type="LONGTERM"
    )


def test_brief_explicit_used_when_no_holding():
    """Fresh BUY (not yet held) falls back to brief-explicit stop."""
    result = resolve_stop_for_rec(
        plan_type="SWING",
        holding=None,
        brief_stop_vnd=26500,
        atr_trail_state=None,
    )
    assert result == ResolvedStop(price_vnd=26500, source="BRIEF_EXPLICIT", plan_type="SWING")


def test_brief_explicit_beats_brief_only_when_no_holding():
    """With holding+breakeven, brief-explicit is ignored."""
    holding: StopResolutionInput = {
        "ticker": "HPG",
        "plan_type": "SWING",
        "breakeven_stop": 22000,
    }
    result = resolve_stop_for_rec(
        plan_type="SWING",
        holding=holding,
        brief_stop_vnd=21500,
        atr_trail_state=None,
    )
    assert result is not None
    assert result.source == "BREAKEVEN_HOLDING"
    assert result.price_vnd == 22000


def test_no_inputs_returns_none():
    """No holding + no brief-explicit + no trail state → None (fail-loud at caller)."""
    result = resolve_stop_for_rec(
        plan_type="SWING",
        holding=None,
        brief_stop_vnd=None,
        atr_trail_state=None,
    )
    assert result is None


def test_zero_stop_values_ignored():
    """Zero or negative stop values are treated as missing, not valid stops."""
    holding: StopResolutionInput = {
        "ticker": "BAD",
        "plan_type": "SWING",
        "breakeven_stop": 0,
    }
    result = resolve_stop_for_rec(
        plan_type="SWING",
        holding=holding,
        brief_stop_vnd=12000,
        atr_trail_state=None,
    )
    assert result is not None
    assert result.source == "BRIEF_EXPLICIT"
    assert result.price_vnd == 12000


def test_holding_plan_type_wins_over_caller_plan_type():
    """When holding.plan_type disagrees with caller plan_type, holding wins."""
    holding: StopResolutionInput = {
        "ticker": "GAS",
        "plan_type": "LONGTERM",
        "catastrophic_stop": 88000,
    }
    result = resolve_stop_for_rec(
        plan_type="SWING",
        holding=holding,
        brief_stop_vnd=None,
        atr_trail_state=None,
    )
    assert result is not None
    assert result.source == "CATASTROPHIC_FLOOR"
    assert result.plan_type == "LONGTERM"


@pytest.mark.parametrize(
    "strategy,price,expected_source",
    [
        ("TREND", 50000, "ATR_TRAIL"),
        ("MOMENTUM", 50000, "ATR_TRAIL"),
        ("BREAKOUT", 50000, "ATR_TRAIL"),
        ("trend", 50000, "ATR_TRAIL"),  # case-insensitive
        ("FIXED_TARGET", 50000, "BREAKEVEN_HOLDING"),
        (None, 50000, "BREAKEVEN_HOLDING"),
    ],
)
def test_atr_trail_strategy_table(strategy, price, expected_source):
    """Table-driven: only ATR_TRAIL_STRATEGIES activate trail-price precedence."""
    holding: StopResolutionInput = {
        "ticker": "T",
        "plan_type": "SWING",
        "breakeven_stop": 45000,
    }
    state = {"strategy": strategy, "stop_price": price} if strategy is not None else None
    result = resolve_stop_for_rec(
        plan_type="SWING",
        holding=holding,
        brief_stop_vnd=None,
        atr_trail_state=state,  # type: ignore[arg-type]
    )
    assert result is not None
    assert result.source == expected_source
