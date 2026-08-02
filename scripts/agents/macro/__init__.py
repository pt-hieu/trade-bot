"""Global Macro Metrics Agent using PydanticAI.

Fetches DXY and VIX via yfinance (Lightsail API), USD/VND via vnstock_data.
Classification is deterministic. LLM only used for interpretation text.

Module layout (post-modularisation, SWI-212):
  * ``classifiers.py`` — pure deterministic classify_* + calculate_global_regime.
  * ``fetch.py`` — _fetch_macro_data + _yf_pair (external I/O).
  * ``build.py`` — fetch_macro_metrics orchestrator + _generate_interpretation.
  * ``__init__.py`` — MacroMetricsResult + re-exports of public API.
"""

from __future__ import annotations

from pydantic import BaseModel

from .build import fetch_macro_metrics
from .classifiers import (
    MISSING_SIGNAL,
    MISSING_SIGNAL_DEFAULTS,
    DxySignal,
    GlobalRiskRegime,
    UsdVndSignal,
    VixSignal,
    _is_valid_number,
    calculate_global_regime,
    classify_dxy,
    classify_oil,
    classify_usd_vnd,
    classify_vix,
)
from .fetch import _fetch_macro_data, _yf_pair
from .interpretation import _build_failclosed_output, _generate_interpretation


class MacroMetricsResult(BaseModel):
    """Global macro metrics result."""

    date: str
    dxy_value: float
    dxy_change_pct: float
    dxy_signal: DxySignal
    vix_value: float
    vix_change_pct: float
    vix_signal: VixSignal
    usd_vnd_rate: float
    usd_vnd_signal: UsdVndSignal
    global_risk_regime: GlobalRiskRegime
    interpretation: str
    upcoming_events: list[str]


__all__ = [
    "DxySignal",
    "GlobalRiskRegime",
    "MISSING_SIGNAL",
    "MISSING_SIGNAL_DEFAULTS",
    "MacroMetricsResult",
    "UsdVndSignal",
    "VixSignal",
    "_build_failclosed_output",
    "_fetch_macro_data",
    "_generate_interpretation",
    "_is_valid_number",
    "_yf_pair",
    "calculate_global_regime",
    "classify_dxy",
    "classify_oil",
    "classify_usd_vnd",
    "classify_vix",
    "fetch_macro_metrics",
]
