"""SSOT helper tests — `read_rr()` returns None for trailing exits and never
coerces None → 0.0. The 4th-instance defect class (SWI-115, SWI-317, SWI-340,
2026-05-14) regressed on the same coercion vector; this test locks the
contract.
"""

from __future__ import annotations

from shared.rules.exit_strategy import read_rr


def test_trailing_exit_returns_none() -> None:
    pick = {"exit_family": "ATR_TRAIL", "risk_reward": None, "strategy": "TREND"}
    assert read_rr(pick) is None


def test_trailing_exit_returns_none_even_with_phantom_rr() -> None:
    """If a producer leaks a non-None risk_reward on a trailing pick, the
    helper still returns None — exit_family is the source of truth."""
    pick = {"exit_family": "ATR_TRAIL", "risk_reward": 3.0}
    assert read_rr(pick) is None


def test_fixed_target_with_rr_returns_float() -> None:
    pick = {"exit_family": "FIXED_TARGET", "risk_reward": 3.0, "target": 50000}
    assert read_rr(pick) == 3.0


def test_fixed_target_with_none_rr_returns_none() -> None:
    """Producer-leak surface: fixed-target pick with risk_reward=None should
    surface as None (not 0.0) so the caller can log/handle the leak."""
    pick = {"exit_family": "FIXED_TARGET", "risk_reward": None, "target": 50000}
    assert read_rr(pick) is None


def test_missing_risk_reward_key_returns_none() -> None:
    pick = {"exit_family": "FIXED_TARGET", "target": 50000}
    assert read_rr(pick) is None


def test_no_exit_family_falls_back_to_target_none_check() -> None:
    """Backward-compat with `is_trailing_exit` legacy fallback: when
    exit_family is absent, target=None implies trailing intent."""
    trailing_pick = {"target": None, "risk_reward": None}
    assert read_rr(trailing_pick) is None

    fixed_pick = {"target": 50000, "risk_reward": 2.5}
    assert read_rr(fixed_pick) == 2.5
