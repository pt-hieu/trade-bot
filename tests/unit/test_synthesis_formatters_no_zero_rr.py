"""SWI-340: synthesis_formatters must never emit literal "R:R 0.0" / "Target: 0".

Defense-in-depth on top of the validator's _validate_exit_contract — the
formatter must refuse to render deceptive zero rows when an upstream contract
violation slips past picks.py:_passes_rr_floor.
"""

from __future__ import annotations

import pytest

from agents.synthesis_formatters import (
    _format_pre_computed_picks,
    _format_pre_computed_picks_fallback,
)


def _base_pick(**overrides) -> dict:
    base = {
        "ticker": "SAB",
        "sector": "consumer",
        "action": "BUY",
        "entry": 45770,
        "stop": 42758,
        "target": 55000,
        "risk_reward": 3.2,
        "risk_reward_gross": 3.4,
        "target_basis": "conservative",
        "verdict": "full_size",
        "shares": 100,
        "note": "Breakout setup",
        "exit_family": "FIXED_TARGET",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "target,rr_raw",
    [(None, None), (None, 0.0), (0, 0.0), (0, None)],
)
def test_fallback_formatter_never_emits_r_r_zero_zero(target, rr_raw):
    pick = _base_pick(target=target, risk_reward=rr_raw, exit_family="FIXED_TARGET")
    output = _format_pre_computed_picks_fallback([pick], sector_results=[])
    assert "R:R 0.0" not in output
    # "Target: 0" with no decimal would be the broken render.
    assert "Target: 0\n" not in output
    assert "Target: 0," not in output  # rules out "Target: 0,000" malformed


def test_fallback_formatter_atr_trail_routes_correctly():
    pick = _base_pick(target=None, risk_reward=None, exit_family="ATR_TRAIL")
    output = _format_pre_computed_picks_fallback([pick], sector_results=[])
    assert "Target: trailing stop (ATR_TRAIL)" in output
    assert "R:R 0.0" not in output


@pytest.mark.parametrize(
    "target,rr_raw",
    [(None, None), (None, 0.0), (0, 0.0), (0, None)],
)
def test_llm_context_formatter_never_emits_r_r_zero_zero(target, rr_raw):
    pick = _base_pick(target=target, risk_reward=rr_raw, exit_family="FIXED_TARGET")
    output = _format_pre_computed_picks([pick], min_rr_floor=2.5)
    assert "R:R 0.0" not in output
    assert "Target: 0 " not in output


def test_llm_context_formatter_atr_trail_routes_correctly():
    pick = _base_pick(target=None, risk_reward=None, exit_family="ATR_TRAIL")
    output = _format_pre_computed_picks([pick], min_rr_floor=2.5)
    assert "trailing stop (ATR_TRAIL)" in output
    assert "R:R 0.0" not in output


def test_llm_context_formatter_well_formed_pick_renders_r_r():
    pick = _base_pick()
    output = _format_pre_computed_picks([pick], min_rr_floor=2.5)
    assert "R:R 3.2" in output
    assert "Target: 55,000" in output
