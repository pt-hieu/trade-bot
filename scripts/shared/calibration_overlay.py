"""Deterministic calibration overlay for entry gap adjustment.

Reads calibration_insights (retro pipeline output) and adjusts
max_entry_gap_pct used by compute_setup_from_levels(). Pure Python,
no LLM. CLAUDE.md Rule 9 compliant.

Called once at pipeline start (Phase 0). Falls back gracefully
if calibration data is unavailable or insufficient.

Regime-aware: RISK_OFF/CRISIS apply a tighter ceiling on entry gaps
so pullback entries stay closer to market price — critical during
geopolitical shocks where support levels are unreliable and false
breakdowns recover quickly.

Staleness bypass: when calibration data hasn't been refreshed for
STALE_DAYS (no new BUY evals), falls back to default gap to break
the chicken-and-egg deadlock (tight gap → no picks → no data → stale).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Calibration thresholds — entry gap tightens when too many entries are unreachable
UNREACHABLE_HIGH_PCT = 60.0  # above this → use TIGHT gap
UNREACHABLE_MODERATE_PCT = 40.0  # above this → use MODERATE gap
TIGHT_GAP_PCT = 1.5  # tight entry gap (% below close)
MODERATE_GAP_PCT = 2.0  # moderate entry gap
CAUTIOUS_GAP_PCT = 2.5  # cautious entry gap (geo sustained pressure)

# Staleness — if calibration data is older than this, ignore it and use default gap.
# Breaks the deadlock: tight gap → 0 picks → no new data → calibration frozen.
STALE_DAYS = 5

# Regime ceiling — overrides calibration when market risk is elevated.
# RISK_OFF: pullback entries max 2% below close (not 3%+)
# CRISIS: pullback entries max 1.5% below close
_REGIME_GAP_CEILING: dict[str, float] = {
    "RISK_OFF": MODERATE_GAP_PCT,
    "CRISIS": TIGHT_GAP_PCT,
    "ELEVATED": MODERATE_GAP_PCT,
    "CAUTIOUS": CAUTIOUS_GAP_PCT,
}

_calibrated_entry_gap: float | None = None


def compute_calibrated_entry_gap(
    default_gap_pct: float,
    pct_unreachable: float | None,
    sample_size: int | None,
    min_sample_size: int = 5,
    regime: str | None = None,
    as_of: date | None = None,
    today: date | None = None,
) -> float:
    """Deterministic entry gap adjustment based on calibration data + regime.

    Args:
        default_gap_pct: Static default from trading_config (typically 3.0%)
        pct_unreachable: % of entries that were unreachable in rolling window
        sample_size: Number of data points in the rolling window
        min_sample_size: Minimum samples required to trust calibration
        regime: Global risk regime (CALM/CAUTIOUS/ELEVATED/RISK_OFF/CRISIS)
        as_of: Date of the most recent calibration data point
        today: Override for current date (testing). Defaults to date.today().

    Returns:
        Adjusted max_entry_gap_pct (bounded between TIGHT_GAP_PCT and default)
    """
    current_date = today or date.today()

    if as_of is not None and (current_date - as_of) > timedelta(days=STALE_DAYS):
        logger.warning(
            "Calibration data stale (%s, %d days old) — bypassing to default %.1f%%",
            as_of,
            (current_date - as_of).days,
            default_gap_pct,
        )
        gap = default_gap_pct
    elif pct_unreachable is not None and sample_size is not None and sample_size >= min_sample_size:
        # Fresh calibration — apply normal adjustment
        if pct_unreachable > UNREACHABLE_HIGH_PCT:
            gap = TIGHT_GAP_PCT
        elif pct_unreachable > UNREACHABLE_MODERATE_PCT:
            gap = MODERATE_GAP_PCT
        else:
            gap = default_gap_pct
    else:
        gap = default_gap_pct

    # Apply regime ceiling — tighter of calibration vs regime constraint
    regime_ceiling = _REGIME_GAP_CEILING.get(regime or "")
    if regime_ceiling is not None:
        gap = min(gap, regime_ceiling)

    return gap


async def init_calibration_overlay(regime: str | None = None) -> None:
    """Load calibration data and compute overlay. Call once at pipeline start.

    Args:
        regime: Global risk regime for regime-aware gap ceiling.
    """
    global _calibrated_entry_gap  # noqa: PLW0603
    from shared.neon.learnings import get_calibration_insights
    from shared.trading_config import get_trading_config

    try:
        calibration = await get_calibration_insights() or {}
        default = get_trading_config().max_entry_gap_pct
        pct_unreachable = calibration.get("pct_entries_unreachable")
        sample_size = calibration.get("sample_size")
        as_of_str = calibration.get("as_of")
        as_of = date.fromisoformat(as_of_str) if as_of_str else None

        _calibrated_entry_gap = compute_calibrated_entry_gap(
            default,
            pct_unreachable,
            sample_size,
            regime=regime,
            as_of=as_of,
        )
        logger.info(
            "Calibration overlay: max_entry_gap_pct %.1f%% -> %.1f%% "
            "(unreachable=%.1f%%, n=%s, regime=%s, as_of=%s)",
            default,
            _calibrated_entry_gap,
            pct_unreachable or 0,
            sample_size,
            regime or "N/A",
            as_of or "N/A",
        )
    except Exception as exception:
        logger.warning("Calibration overlay failed (using default): %s", exception)


def get_calibrated_entry_gap() -> float | None:
    """Return calibrated entry gap, or None if not initialized."""
    return _calibrated_entry_gap


def clear_calibration_cache() -> None:
    """Reset cached value — for test isolation."""
    global _calibrated_entry_gap  # noqa: PLW0603
    _calibrated_entry_gap = None
