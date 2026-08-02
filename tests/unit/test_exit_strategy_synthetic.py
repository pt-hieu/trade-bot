"""SWI-316 follow-up — synthetic ATR_TRAIL helpers recalibration.

Covers:
* `derive_atr_trail_synthetic_target` uses ``SYNTHETIC_TARGET_ATR_MULT = 2.0``
  (down from 3.0) and is pure exit-math (no stop kwarg, no cap).
* `derive_atr_trail_synthetic_rr` caps reward at
  ``SYNTHETIC_RR_RISK_CAP * risk`` so the audit-row RR never saturates the
  `sqrt(rr/10)` normalizer's 10:1 ceiling.
* Adversarial inputs (atr=0/None, entry<=stop, stop=None) fail-loud-by-zeroing.
"""

from __future__ import annotations

from shared.rules.exit_strategy import (
    SYNTHETIC_RR_RISK_CAP,
    derive_atr_trail_synthetic_rr,
    derive_atr_trail_synthetic_target,
)


def test_target_uses_2x_atr_coefficient():
    assert derive_atr_trail_synthetic_target(entry=47000, atr=1000) == 49000


def test_target_atr_none_falls_back_to_plus_one():
    assert derive_atr_trail_synthetic_target(entry=10000, atr=None) == 10001


def test_target_atr_zero_falls_back_to_plus_one():
    assert derive_atr_trail_synthetic_target(entry=10000, atr=0) == 10001


def test_rr_caps_at_risk_cap_for_wide_atr_tight_stop():
    """Wide-ATR + tight-stop case that previously saturated the normalizer.

    Pre-fix: entry=47000 stop=46800 atr=1000 → reward = 3*1000 = 3000,
    risk = 200 → rr = 15.0, clamped to 10 by normalizer → 1.0 → 20pts.
    Post-fix: target reward = 2*1000 = 2000, capped at 4*200 = 800,
    rr = 4.0.
    """
    rr = derive_atr_trail_synthetic_rr(entry=47000, stop=46800, atr=1000)
    assert rr == SYNTHETIC_RR_RISK_CAP  # 4.0


def test_rr_uncapped_when_below_cap():
    """Reward < cap*risk → return the raw rr unchanged."""
    # entry=47000, stop=46500, atr=200 → target=47400, reward=400,
    # risk=500, raw rr = 0.8, cap = 2000, so reward not capped.
    rr = derive_atr_trail_synthetic_rr(entry=47000, stop=46500, atr=200)
    assert rr == 400 / 500


def test_rr_sab_like_typical_case_in_sweet_spot():
    """SAB-like (entry=47000, stop=46500, atr=1000) lands in sweet-spot."""
    rr = derive_atr_trail_synthetic_rr(entry=47000, stop=46500, atr=1000)
    # target = 47000 + 2000 = 49000, reward = 2000, risk = 500
    # raw rr = 4.0, cap = 4*500 = 2000 (reward equal to cap)
    assert rr == 4.0


def test_rr_entry_le_stop_returns_zero():
    assert derive_atr_trail_synthetic_rr(entry=47000, stop=47000, atr=1000) == 0.0
    assert derive_atr_trail_synthetic_rr(entry=46000, stop=47000, atr=1000) == 0.0


def test_rr_stop_none_returns_zero():
    assert derive_atr_trail_synthetic_rr(entry=47000, stop=None, atr=1000) == 0.0


def test_rr_entry_none_returns_zero():
    assert derive_atr_trail_synthetic_rr(entry=None, stop=46500, atr=1000) == 0.0


def test_rr_atr_zero_still_returns_positive_floor():
    """atr=0 → target = entry+1, reward=1, risk=500 → rr ≈ 0.002 (non-zero, tiny)."""
    rr = derive_atr_trail_synthetic_rr(entry=47000, stop=46500, atr=0)
    assert 0 < rr < 0.01
