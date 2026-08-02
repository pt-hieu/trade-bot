"""Trend-momentum signal derivation and BUY gate rules.

All direction booleans computed in one pass from short indicator series
emitted by the upstream vnstock API. Consumed by:
- `pipeline/context_blocks_ticker.py` — render direction tags for LLM readability
- `agents/picks.py` — deterministic TREND/MOMENTUM gate (trend-follow symmetry)

Pure deterministic Python: no async, no DB, no LLM. Matches the
`shared/rules/` canonical home for gate logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.types import FlatTechnicalsRow


# Flat-window tolerances — prevent over-suppression on routine pullbacks.
# 1.0 ADX flutter = noise, not a fade; 2.0 RSI flutter covers intraday chop;
# MACD histogram sign/slope is already denoised so min_delta is 0.0.
ADX_FLAT_DELTA: float = 1.0
RSI_FLAT_DELTA: float = 2.0
MACD_HIST_FLAT_DELTA: float = 0.0

# ADX strength floor — below this value the trend is too weak to call "rising"
# meaningful; direction derivation is dominated by noise.
ADX_STRENGTH_FLOOR: float = 25.0

# Strategies that represent the trend-follow class. Gate logic consumes
# this set from both agents.picks and future exit-side symmetry (DEF-2026-04-23-001).
# PULLBACK/BOUNCE/BREAKOUT/DIVERGENCE/MEAN_REVERSION have different criteria and
# bypass the gate.
TREND_FOLLOW_STRATEGIES: frozenset[str] = frozenset({"TREND", "MOMENTUM"})


def _direction(
    series: list[float] | None,
    lookback: int,
    min_delta: float,
) -> bool | None:
    """Return direction of a short series with flat-within-delta tolerance.

    True  — curr > prev + min_delta (rising meaningfully)
    False — curr < prev - min_delta (falling meaningfully)
    None  — flat-within-delta OR insufficient history (do not block, do not green-light)
    """
    if not series or len(series) <= lookback:
        return None
    curr = series[-1]
    prev = series[-(lookback + 1)]
    if curr > prev + min_delta:
        return True
    if curr < prev - min_delta:
        return False
    return None


@dataclass(frozen=True)
class MomentumSignals:
    """Direction signals for the four trend-momentum indicators.

    Each field is tri-state:
    - True  = rising meaningfully (or, for volume, trend == "increasing")
    - False = falling meaningfully (or, for volume, trend == "decreasing")
    - None  = flat / unknown / insufficient history (do not gate on this signal)
    """

    adx_rising: bool | None
    rsi_rising: bool | None
    macd_hist_rising: bool | None
    volume_trending_up: bool | None


def derive_momentum_signals(flat: FlatTechnicalsRow | dict) -> MomentumSignals:
    """Compute all four direction signals in one pass from a flat technicals row.

    Reads `adx_series`, `rsi_series`, `macd_histogram_series`, and
    `volume_context.volume_trend`. Missing or short series map to None —
    consumers treat None as "do not gate" (see `buy_trend_follow_eligible`).
    """
    adx = flat.get("adx_series")
    rsi = flat.get("rsi_series")
    mac = flat.get("macd_histogram_series")
    vol_ctx = flat.get("volume_context") or {}
    vol_trend = vol_ctx.get("volume_trend") if isinstance(vol_ctx, dict) else None

    if vol_trend == "increasing":
        volume_trending_up: bool | None = True
    elif vol_trend == "decreasing":
        volume_trending_up = False
    else:
        # "stable" / "unknown" / missing → no directional signal.
        volume_trending_up = None

    return MomentumSignals(
        adx_rising=_direction(adx, lookback=3, min_delta=ADX_FLAT_DELTA),
        rsi_rising=_direction(rsi, lookback=3, min_delta=RSI_FLAT_DELTA),
        macd_hist_rising=_direction(mac, lookback=2, min_delta=MACD_HIST_FLAT_DELTA),
        volume_trending_up=volume_trending_up,
    )


def buy_trend_follow_eligible(
    flat: FlatTechnicalsRow | dict,
    signals: MomentumSignals,
) -> tuple[bool, str]:
    """Deterministic gate for trend-follow BUY candidates.

    Returns (eligible, reason). `reason` is a human-readable audit string
    surfaced in the downgrade note so composer logs show *why* the gate
    rejected (or approved) the candidate.

    Rules (all must hold for eligibility):
    1. Structural uptrend: Supertrend UP + DM+ > DM-
    2. ADX ≥ ADX_STRENGTH_FLOOR (currently 25)
    3. ADX is not fading (adx_rising True or None allowed — flat passes so
       routine pullbacks are not over-suppressed)
    """
    # Import here to avoid circular dependency (technicals tool module
    # imports from shared.rules, shared.rules.trend_momentum would pull
    # the whole agents.tools graph at module load).
    from agents.tools.technicals import is_structural_uptrend

    # is_structural_uptrend accepts dict; TypedDict is runtime-dict so the
    # cast is type-only (no structural copy).
    if not is_structural_uptrend(dict(flat)):
        return False, "no structural uptrend"

    adx_value = flat.get("adx")
    if adx_value is None or adx_value < ADX_STRENGTH_FLOOR:
        return False, f"ADX weak ({adx_value})"

    if signals.adx_rising is False:
        return False, "ADX fading"

    # adx_rising is True (rising) or None (flat-within-delta) → allow.
    # Flat-window tolerance prevents over-suppression on healthy pullbacks.
    return True, "trend-follow gate OK"
