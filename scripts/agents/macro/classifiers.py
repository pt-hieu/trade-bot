"""Deterministic classification functions — pure Python, no LLM, no I/O."""

from __future__ import annotations

import math
from typing import Literal

from shared.rules.geopolitical import apply_shock_floor

DxySignal = Literal["WEAK", "NEUTRAL", "STRONG"]
VixSignal = Literal["LOW", "MODERATE", "HIGH", "EXTREME"]
UsdVndSignal = Literal["STABLE", "PRESSURE", "FLIGHT"]
GlobalRiskRegime = Literal["CALM", "CAUTIOUS", "ELEVATED", "CRISIS"]


# Sentinel returned by classify_* when input is NaN/None/inf.
# fetch_macro_metrics checks for this and triggers fail-closed CAUTIOUS path.
MISSING_SIGNAL = "MISSING"

# Safe defaults when a signal is MISSING — used in both live pipeline and backfill
MISSING_SIGNAL_DEFAULTS = {
    "dxy": "NEUTRAL",
    "vix": "MODERATE",
    "usd_vnd": "PRESSURE",
    "oil": "NORMAL",
}


def _is_valid_number(value) -> bool:
    """True if value is a finite number (not None, NaN, or inf)."""
    if value is None:
        return False
    try:
        return math.isfinite(value)
    except (TypeError, ValueError):
        return False


def classify_dxy(value: float, change_pct: float) -> str:
    """Classify DXY signal based on value and daily change."""
    if not _is_valid_number(value) or not _is_valid_number(change_pct):
        return MISSING_SIGNAL
    if value < 100 or change_pct < -0.5:
        return "WEAK"
    elif value > 105 or change_pct > 0.5:
        return "STRONG"
    return "NEUTRAL"


def classify_vix(value: float) -> str:
    """Classify VIX signal based on value.

    Thresholds raised from 18/25/30 to 22/28/35:
    VIX spends ~50% of time above 18 historically, making MODERATE the default.
    At 22+, the signal is genuinely elevated risk, not routine volatility.
    """
    if not _is_valid_number(value):
        return MISSING_SIGNAL
    if value < 22:
        return "LOW"
    elif value < 28:
        return "MODERATE"
    elif value < 35:
        return "HIGH"
    return "EXTREME"


def classify_oil(price: float, change_pct: float) -> str:
    """Classify crude oil signal based on price and daily change.

    Thresholds calibrated for WTI (CL=F) / vnstock oil_crude:
    < 60: LOW (deflationary, cheap energy)
    60-80: NORMAL (stable)
    80-100: ELEVATED (inflationary pressure — impacts VN logistics/manufacturing)
    > 100: EXTREME (supply disruption, energy crisis)
    Daily change > 5%: append _SPIKE suffix (e.g. ELEVATED_SPIKE).
    """
    if not _is_valid_number(price):
        return MISSING_SIGNAL
    if price < 60:
        signal = "LOW"
    elif price < 80:
        signal = "NORMAL"
    elif price < 100:
        signal = "ELEVATED"
    else:
        signal = "EXTREME"
    if _is_valid_number(change_pct) and abs(change_pct) > 5:
        signal = signal + "_SPIKE"
    return signal


_YF_STABLE_OFFSET = 200  # VND above rolling median → STABLE ceiling
_YF_PRESSURE_OFFSET = 400  # VND above rolling median → PRESSURE ceiling
_YF_STATIC_STABLE = 26200  # Static fallback when no rolling median
_YF_STATIC_PRESSURE = 26500


def classify_usd_vnd(
    rate: float,
    source: str = "sbv",
    rolling_median: float | None = None,
) -> str:
    """Classify USD/VND signal based on rate and source.

    SBV reference rate (~25,000-25,200): official central bank rate.
    yfinance market rate: interbank/commercial rate, drifts with market.
    When rolling_median is provided, yfinance thresholds are anchored dynamically.
    """
    if not _is_valid_number(rate):
        return MISSING_SIGNAL
    if source == "yfinance":
        if rolling_median is not None and _is_valid_number(rolling_median):
            stable_ceil = rolling_median + _YF_STABLE_OFFSET
            pressure_ceil = rolling_median + _YF_PRESSURE_OFFSET
        else:
            stable_ceil = _YF_STATIC_STABLE
            pressure_ceil = _YF_STATIC_PRESSURE
        if rate < stable_ceil:
            return "STABLE"
        elif rate <= pressure_ceil:
            return "PRESSURE"
        return "FLIGHT"
    else:
        if rate < 25200:
            return "STABLE"
        elif rate <= 25500:
            return "PRESSURE"
        return "FLIGHT"


def calculate_global_regime(
    dxy_signal: str,
    vix_signal: str,
    usd_vnd_signal: str,
    has_event_within_3_days: bool,
    oil_signal: str = "NORMAL",
    active_geopolitical_phase: str | None = None,
    phase_stale: bool = False,
) -> str:
    """Calculate global risk regime. Deterministic. phase_stale softens
    the shock floor one notch; see apply_shock_floor for L2 semantics.
    """
    if vix_signal == "EXTREME":
        return "CRISIS"
    if vix_signal == "HIGH" and usd_vnd_signal == "FLIGHT" and dxy_signal == "STRONG":
        return "CRISIS"
    if "EXTREME" in oil_signal and usd_vnd_signal == "FLIGHT":
        return "CRISIS"

    if (
        vix_signal == "HIGH"
        or usd_vnd_signal == "FLIGHT"
        or (usd_vnd_signal == "PRESSURE" and dxy_signal == "STRONG")
        or "EXTREME" in oil_signal
    ):
        computed = "ELEVATED"
    else:
        moderate_signals = sum(
            [
                vix_signal == "MODERATE",
                dxy_signal == "STRONG",
                has_event_within_3_days,
                usd_vnd_signal == "PRESSURE",
                "_SPIKE" in oil_signal,
            ]
        )
        computed = "CAUTIOUS" if moderate_signals >= 2 else "CALM"

    return apply_shock_floor(computed, active_geopolitical_phase, phase_stale=phase_stale)
