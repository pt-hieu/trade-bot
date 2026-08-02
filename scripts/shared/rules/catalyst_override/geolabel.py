"""Per-ticker geopolitical-exposure label aggregator (Fix 1, 2026-04-21)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from shared.observability import log_warn

from ..geopolitical import ACTIVE_SHOCK_PHASES
from .types import (
    STACKED_POSITIVE_MIN_CATALYSTS,
    CatalystBoost,
    CatalystInput,
    GeoLabel,
)
from .validators import count_high_positive_per_ticker

if TYPE_CHECKING:
    from pipeline.types import GeopoliticalShockDict

logger = logging.getLogger(__name__)

_factor_map_validated = False


async def _validate_geo_factor_map_once() -> None:
    """Lazy one-shot validator: emit `geo_factor_map_missing` for any active
    geopolitical catalyst row missing structured `catalyst_factors`.

    Memoized via module-level flag — first call walks active catalysts,
    subsequent calls no-op. Never raises.
    """
    global _factor_map_validated
    if _factor_map_validated:
        return
    _factor_map_validated = True
    try:
        from shared.neon.catalysts import get_active_catalysts_db

        rows = await get_active_catalysts_db(None) or []
        for r in rows:
            if (r.get("catalyst_type") or "") != "geopolitical":
                continue
            if not r.get("catalyst_factors"):
                log_warn(
                    "geo_factor_map_missing",
                    catalyst_key=r.get("catalyst_key"),
                    event=r.get("event"),
                )
    except Exception as exc:
        logger.warning("geo factor-map validation skipped: %s", exc)


def _reset_geo_factor_map_validation_for_tests() -> None:
    """Test helper: reset memoization so each test sees first-call behavior."""
    global _factor_map_validated
    _factor_map_validated = False


# Shock-factor direction conventions for the macro-sensitivity score.
# Listed factors = shock sends them UP (oil price, usd_vnd). A ticker with
# POSITIVE sensitivity to an up-moving factor benefits; NEGATIVE sensitivity
# is hurt. Weights mirror MAGNITUDE_WEIGHTS in context_blocks_macro.
_MAGNITUDE_WEIGHTS: dict[str, float] = {"HIGH": 2.0, "MEDIUM": 1.0, "LOW": 0.5}


def classify_geo_label(
    ticker: str,
    macro_sensitivities: list[dict] | None,
    geopolitical_shock: GeopoliticalShockDict | None,
    positive_catalyst_boosts: dict[str, CatalystBoost],
    active_catalysts: list[CatalystInput] | None = None,
    shock_factors: Sequence[str] | None = None,
) -> GeoLabel | None:
    """Unified per-ticker geopolitical classification.

    Returns GEO_BENEFICIARY, GEO_VICTIM, GEO_EXPOSED, GEO_MIXED, or None.

    Tie-break (order matters):
      1. No active shock phase → None.
      2. shock_victim_signal > 0 AND the ticker stacks ≥2 HIGH/MEDIUM
         POSITIVE catalysts → GEO_MIXED (shock-exposed but stacked positive
         catalysts).
      3. Fall through to macro-sensitivity scoring on `shock_factors`.
         POSITIVE sensitivity to a factor shock moves UP → beneficiary;
         NEGATIVE → victim.
      4. Zero-score AND ticker in `affected_tickers` → GEO_EXPOSED.
      5. Otherwise → None (neutral; no shock exposure).

    Inputs:
      * ``positive_catalyst_boosts`` — output of
        :func:`get_catalyst_boosted_tickers`, used so we do not re-compute
        the eligibility set.
      * ``active_catalysts`` — full active catalyst list, needed to count
        stacked HIGH/MEDIUM POSITIVE catalysts that tag the ticker
        (boosts dict collapses to one entry per ticker).
      * ``shock_factors`` — pulled from the shock's structured factor
        column (Fix 2 — `catalysts.catalyst_factors`). When ``None`` the
        aggregator falls back to the legacy `hormuz_closure_2026` set so
        in-flight migrations don't break.
    """
    if not geopolitical_shock:
        return None
    phase_name = geopolitical_shock.get("phase_name")
    if phase_name not in ACTIVE_SHOCK_PHASES:
        return None

    affected_tickers = geopolitical_shock.get("affected_tickers") or []
    if shock_factors is None:
        catalyst_key = geopolitical_shock.get("catalyst_key") or ""
        if catalyst_key == "hormuz_closure_2026":
            shock_factors = ["oil_price", "usd_vnd"]
        else:
            logger.warning(
                "classify_geo_label: no shock_factors for catalyst_key=%r — "
                "falling back to affected-list label",
                catalyst_key,
            )
            return "GEO_EXPOSED" if ticker in affected_tickers else None

    beneficiary_score = 0.0
    victim_score = 0.0
    for sensitivity in macro_sensitivities or []:
        factor = sensitivity.get("factor")
        if factor not in shock_factors:
            continue
        direction = (sensitivity.get("direction") or "").upper()
        magnitude = (sensitivity.get("magnitude") or "MEDIUM").upper()
        weight = _MAGNITUDE_WEIGHTS.get(magnitude, 1.0)
        if direction == "POSITIVE":
            beneficiary_score += weight
        elif direction == "NEGATIVE":
            victim_score += weight

    # GEO_MIXED tie-break: shock hurts the ticker AND it has ≥2 HIGH/MEDIUM
    # POSITIVE catalysts stacked on it. Apply BEFORE declaring victim so
    # stacking positive catalysts beat a blanket shock-victim label.
    if victim_score > 0 and _has_stacked_positive_catalysts(ticker, active_catalysts):
        return "GEO_MIXED"

    if beneficiary_score > victim_score:
        return "GEO_BENEFICIARY"
    if victim_score > beneficiary_score:
        return "GEO_VICTIM"
    if ticker in affected_tickers:
        return "GEO_EXPOSED"
    del positive_catalyst_boosts  # reserved for future tie-break signals
    return None


def _has_stacked_positive_catalysts(
    ticker: str,
    active_catalysts: list[CatalystInput] | None,
) -> bool:
    """True when ≥2 HIGH/MEDIUM POSITIVE catalysts tag this ticker."""
    counts = count_high_positive_per_ticker(active_catalysts, [ticker])
    return counts.get(ticker.upper(), 0) >= STACKED_POSITIVE_MIN_CATALYSTS
