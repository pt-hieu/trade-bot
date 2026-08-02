"""Underlying-macro stress classifier.

Separate from the geopolitical-shock floor (`geopolitical.apply_shock_floor`).
This module answers: "do the raw macro indicators (VIX/DXY/USD-VND) signal
real stress today?" — used by the recommendation-gate composer to decide
whether ELEVATED regime should enforce the full 3.0 R:R floor or the
shock-only 2.5 floor when the regime is pinned by an active geopolitical
phase while underlying indicators are calm.

Fail-closed: missing or errored macro metrics → treat as stressed (True).
"""

from __future__ import annotations

_STRESS_VIX: frozenset[str] = frozenset({"HIGH", "EXTREME"})
_STRESS_DXY: frozenset[str] = frozenset({"STRONG"})
_STRESS_USD_VND: frozenset[str] = frozenset({"PRESSURE", "FLIGHT"})


def classify_underlying_stress(macro_metrics: dict | None) -> bool:
    """Return True when raw macro signals indicate real stress.

    Inspects the three primary macro channels:
      * VIX signal → HIGH/EXTREME → stress
      * DXY signal → STRONG → stress
      * USD/VND signal → PRESSURE/FLIGHT → stress

    Any one triggers True. All calm → False. Missing data → True
    (fail-closed per CLAUDE.md: missing data → MOST CONSERVATIVE).
    """
    if not macro_metrics or macro_metrics.get("error"):
        return True
    vix_signal = (macro_metrics.get("vix_signal") or "").upper()
    dxy_signal = (macro_metrics.get("dxy_signal") or "").upper()
    usd_vnd_signal = (macro_metrics.get("usd_vnd_signal") or "").upper()
    if not vix_signal and not dxy_signal and not usd_vnd_signal:
        return True
    return (
        vix_signal in _STRESS_VIX or dxy_signal in _STRESS_DXY or usd_vnd_signal in _STRESS_USD_VND
    )
