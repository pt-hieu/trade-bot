"""SWI-340: validator exit-contract tests (state-sync + R:R 0.0 regression).

Locks the canonical predicate (`is_trailing_exit`) routing for ATR_TRAIL vs
FIXED_TARGET picks at the validator boundary. Pairs with
test_synthesis_formatters_no_zero_rr.py — both surfaces must agree.
"""

from __future__ import annotations

from tests.unit._fixtures.recommendation_builder import (
    SECTION_TOP_PICKS,
    _default_validator_params,
    validate_structured_recommendations,
)


def _buy_rec(**overrides) -> dict:
    base = {
        "ticker": "SAB",
        "action": "BUY",
        "section": SECTION_TOP_PICKS,
        "entry_price": 45770,
        "stop_price": 42758,
        "target_price": 55000,
        "risk_reward": 3.2,
        "strategy": "BREAKOUT",
        "exit_family": "FIXED_TARGET",
    }
    base.update(overrides)
    return base


def _params():
    return _default_validator_params(min_rr=2.5)


def test_atr_trail_buy_with_numeric_risk_reward_dropped():
    rec = _buy_rec(
        exit_family="ATR_TRAIL",
        strategy="TREND",
        target_price=None,
        risk_reward=2.5,
    )
    validated, warnings = validate_structured_recommendations([rec], **_params())
    assert not any(r.get("action") == "BUY" for r in validated)
    assert any("EXIT CONTRACT" in w and "non-null risk_reward" in w for w in warnings)


def test_atr_trail_buy_with_zero_rr_dropped():
    rec = _buy_rec(
        exit_family="ATR_TRAIL",
        strategy="TREND",
        target_price=None,
        risk_reward=0.0,
    )
    validated, warnings = validate_structured_recommendations([rec], **_params())
    assert not any(r.get("action") == "BUY" for r in validated)
    assert any("EXIT CONTRACT" in w for w in warnings)


def test_atr_trail_buy_with_numeric_target_dropped():
    rec = _buy_rec(
        exit_family="ATR_TRAIL",
        strategy="TREND",
        target_price=50000,
        risk_reward=None,
    )
    validated, warnings = validate_structured_recommendations([rec], **_params())
    assert not any(r.get("action") == "BUY" for r in validated)
    assert any("numeric target_price" in w for w in warnings)


def test_fixed_target_buy_with_null_target_dropped():
    """A FIXED_TARGET label with target=None is contradictory.

    The SSOT predicate routes via the null-target leg of is_trailing_exit,
    so this rec is classified as trailing-with-numeric-RR — still a contract
    violation, still dropped. Either reason is acceptable for this test.
    """
    rec = _buy_rec(exit_family="FIXED_TARGET", target_price=None, risk_reward=3.0)
    validated, warnings = validate_structured_recommendations([rec], **_params())
    assert not any(r.get("action") == "BUY" for r in validated)
    assert any("EXIT CONTRACT" in w for w in warnings)


def test_fixed_target_buy_with_zero_rr_dropped():
    rec = _buy_rec(exit_family="FIXED_TARGET", risk_reward=0.0)
    validated, warnings = validate_structured_recommendations([rec], **_params())
    assert not any(r.get("action") == "BUY" for r in validated)
    assert any("EXIT CONTRACT" in w for w in warnings)


def test_strategy_exit_family_mismatch_uses_exit_family():
    """exit_family is canonical; strategy is advisory.

    DIVERGENCE is NOT in ATR_TRAIL_STRATEGIES — the legacy validator would
    have routed via FIXED_TARGET and dropped the rec for target=None. The
    SSOT predicate routes via exit_family=ATR_TRAIL and lets it pass.
    """
    rec = _buy_rec(
        exit_family="ATR_TRAIL",
        strategy="DIVERGENCE",
        target_price=None,
        risk_reward=None,
    )
    validated, _warnings = validate_structured_recommendations([rec], **_params())
    assert any(r["ticker"] == "SAB" and r["action"] == "BUY" for r in validated)


def test_fixed_target_buy_well_formed_passes():
    rec = _buy_rec()  # target=55k, rr=3.2, exit_family=FIXED_TARGET
    validated, warnings = validate_structured_recommendations([rec], **_params())
    assert any(r["ticker"] == "SAB" and r["action"] == "BUY" for r in validated)
    assert not any("EXIT CONTRACT" in w for w in warnings)
