"""SWI-307 — build_score_inputs derives synthetic R:R for ATR_TRAIL setups.

Previously `setup["risk_reward"]` was None on ATR_TRAIL (load-bearing per
SWI-115) and the audit row inherited 0.0 → 0 contribution on the largest
single weight (0.20). After the fix, the audit path uses the shared helper
`derive_atr_trail_synthetic_rr` to produce a meaningful R:R for scoring
only — the helper does not write back to setup, so the four downstream
consumers of `is_trailing_exit` remain undisturbed.
"""

from __future__ import annotations

from agents.picks_audit import build_score_inputs


def _atr_trail_setup(**overrides: object) -> dict:
    base: dict = {
        "valid": True,
        "exit_family": "ATR_TRAIL",
        "entry": 162000,
        "stop": 155000,
        "risk_reward": None,  # SWI-115 invariant
        "target": None,
    }
    base.update(overrides)
    return base


def test_atr_trail_passed_synthetic_rr_nonzero():
    """ATR_TRAIL with valid entry/stop/atr produces a non-zero risk_reward."""
    inputs = build_score_inputs(
        signal={"ticker": "VHM"},
        tech_data={"atr": 3000},
        setup=_atr_trail_setup(),
    )
    assert inputs["risk_reward"] > 0, (
        f"expected positive synthetic R:R, got {inputs['risk_reward']}"
    )


def test_atr_trail_atr_zero_degenerates_to_zero():
    """atr=0 → reward=1, then sqrt-normalize maps R:R≈0 to 0 (fail-loud)."""
    inputs = build_score_inputs(
        signal={"ticker": "VHM"},
        tech_data={"atr": 0},
        setup=_atr_trail_setup(),
    )
    # reward = max(1, 0) = 1, risk = 7000 → rr ≈ 0.000143
    assert 0 < inputs["risk_reward"] < 0.01


def test_atr_trail_atr_none_treated_as_zero():
    """atr=None must produce the same value as atr=0."""
    none_inputs = build_score_inputs(
        signal={"ticker": "VHM"},
        tech_data={"atr": None},
        setup=_atr_trail_setup(),
    )
    zero_inputs = build_score_inputs(
        signal={"ticker": "VHM"},
        tech_data={"atr": 0},
        setup=_atr_trail_setup(),
    )
    assert none_inputs["risk_reward"] == zero_inputs["risk_reward"]


def test_atr_trail_entry_le_stop_returns_zero():
    """Defensive: entry ≤ stop must zero out (degenerate setup)."""
    inputs = build_score_inputs(
        signal={"ticker": "VHM"},
        tech_data={"atr": 3000},
        setup=_atr_trail_setup(entry=155000, stop=155000),
    )
    assert inputs["risk_reward"] == 0.0


def test_fixed_target_unaffected():
    """FIXED_TARGET path reads setup['risk_reward'] verbatim."""
    inputs = build_score_inputs(
        signal={"ticker": "VHM"},
        tech_data={"atr": 3000},
        setup={
            "valid": True,
            "exit_family": "FIXED_TARGET",
            "entry": 162000,
            "stop": 155000,
            "risk_reward": 3.5,
            "target": 180000,
        },
    )
    assert inputs["risk_reward"] == 3.5


def test_setup_invalid_returns_zero():
    """setup['valid']=False → 0.0 regardless of exit_family."""
    inputs = build_score_inputs(
        signal={"ticker": "VHM"},
        tech_data={"atr": 3000},
        setup={
            "valid": False,
            "exit_family": "ATR_TRAIL",
            "entry": 162000,
            "stop": 155000,
        },
    )
    assert inputs["risk_reward"] == 0.0
