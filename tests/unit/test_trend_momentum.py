"""Unit tests for shared.rules.trend_momentum — direction derivation + BUY gate."""

from __future__ import annotations

import pytest

from shared.rules.trend_momentum import (
    ADX_FLAT_DELTA,
    MomentumSignals,
    _direction,
    buy_trend_follow_eligible,
    derive_momentum_signals,
)

# ── _direction ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "series",
    [None, [], [42.0], [40.0, 42.0]],
)
def test_direction_insufficient_history_returns_none(series):
    """Short/empty/None series have no direction."""
    assert _direction(series, lookback=3, min_delta=1.0) is None


def test_direction_rising_beyond_delta():
    """curr > prev + min_delta returns True."""
    assert _direction([20.0, 22.0, 25.0, 28.0, 30.0], lookback=3, min_delta=1.0) is True


def test_direction_fading_beyond_delta():
    """curr < prev - min_delta returns False."""
    assert _direction([40.0, 38.0, 36.0, 33.0, 32.0], lookback=3, min_delta=1.0) is False


def test_direction_flat_within_delta_returns_none():
    """curr within ±delta of prev returns None — do not over-suppress pullbacks."""
    # prev = series[-4] = 30.2; curr = 30.5; delta 1.0 → within window
    series = [30.0, 30.2, 30.5, 30.8, 30.5]
    assert _direction(series, lookback=3, min_delta=ADX_FLAT_DELTA) is None


# ── derive_momentum_signals ────────────────────────────────────────────────


def test_derive_all_rising():
    flat = {
        "adx_series": [20.0, 22.0, 24.0, 27.0, 30.0],
        "rsi_series": [50.0, 52.0, 54.0, 57.0, 60.0],
        "macd_histogram_series": [0.1, 0.2, 0.3, 0.4],
        "volume_context": {"volume_trend": "increasing"},
    }
    sig = derive_momentum_signals(flat)
    assert sig.adx_rising is True
    assert sig.rsi_rising is True
    assert sig.macd_hist_rising is True
    assert sig.volume_trending_up is True


def test_derive_volume_stable_maps_to_none():
    flat = {
        "adx_series": None,
        "rsi_series": None,
        "macd_histogram_series": None,
        "volume_context": {"volume_trend": "stable"},
    }
    sig = derive_momentum_signals(flat)
    assert sig.volume_trending_up is None


def test_derive_missing_volume_context():
    sig = derive_momentum_signals({})
    assert sig == MomentumSignals(
        adx_rising=None,
        rsi_rising=None,
        macd_hist_rising=None,
        volume_trending_up=None,
    )


# ── buy_trend_follow_eligible ──────────────────────────────────────────────


_NEUTRAL_SIGNALS = MomentumSignals(
    adx_rising=None,
    rsi_rising=None,
    macd_hist_rising=None,
    volume_trending_up=None,
)


def test_gate_blocks_when_no_structural_uptrend():
    flat = {"supertrend_direction": "DOWN", "adx_dmp": 15.0, "adx_dmn": 20.0, "adx": 28.0}
    eligible, reason = buy_trend_follow_eligible(flat, _NEUTRAL_SIGNALS)
    assert eligible is False
    assert reason == "no structural uptrend"


def test_gate_blocks_weak_adx():
    flat = {
        "supertrend_direction": "UP",
        "adx_dmp": 20.0,
        "adx_dmn": 15.0,
        "adx": 20.0,
    }
    eligible, reason = buy_trend_follow_eligible(flat, _NEUTRAL_SIGNALS)
    assert eligible is False
    assert "ADX weak" in reason
    assert "20" in reason


def test_gate_blocks_fading_adx():
    flat = {
        "supertrend_direction": "UP",
        "adx_dmp": 25.0,
        "adx_dmn": 15.0,
        "adx": 32.0,
    }
    fading = MomentumSignals(
        adx_rising=False,
        rsi_rising=None,
        macd_hist_rising=None,
        volume_trending_up=None,
    )
    eligible, reason = buy_trend_follow_eligible(flat, fading)
    assert eligible is False
    assert reason == "ADX fading"


def test_gate_passes_on_rising_adx():
    flat = {
        "supertrend_direction": "UP",
        "adx_dmp": 25.0,
        "adx_dmn": 15.0,
        "adx": 32.0,
    }
    rising = MomentumSignals(
        adx_rising=True,
        rsi_rising=None,
        macd_hist_rising=None,
        volume_trending_up=None,
    )
    eligible, reason = buy_trend_follow_eligible(flat, rising)
    assert eligible is True
    assert reason == "trend-follow gate OK"


def test_gate_passes_on_flat_adx_avoids_oversuppression():
    """Flat-within-delta (None) must not block — routine pullbacks are healthy."""
    flat = {
        "supertrend_direction": "UP",
        "adx_dmp": 25.0,
        "adx_dmn": 15.0,
        "adx": 32.0,
    }
    eligible, reason = buy_trend_follow_eligible(flat, _NEUTRAL_SIGNALS)
    assert eligible is True
    assert reason == "trend-follow gate OK"


def test_gate_none_adx_value_treated_as_weak():
    """ADX missing → treat as weak (fail-closed / conservative)."""
    flat = {
        "supertrend_direction": "UP",
        "adx_dmp": 25.0,
        "adx_dmn": 15.0,
        "adx": None,
    }
    eligible, _reason = buy_trend_follow_eligible(flat, _NEUTRAL_SIGNALS)
    assert eligible is False
