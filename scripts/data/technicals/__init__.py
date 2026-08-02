"""Technical indicators calculation via vnstock.

Module layout (post-modularisation, SWI-212):
  * ``_numpy.py`` — numpy → native sanitizer for JSON serialization.
  * ``levels.py`` — swing-point detection, N-day range, nearest S/R.
  * ``patterns.py`` — candlestick patterns, volume-vs-avg, closed-at-low.
  * ``trend.py`` — trend classification + analysis-text generator.
  * ``analysis.py`` — async + sync orchestrators that batch-fetch and assemble.
  * ``__init__.py`` — re-exports the public surface (existing consumers
    continue using ``from data.technicals import …``).
"""

from __future__ import annotations

from ._numpy import _sanitize_numpy
from .analysis import fetch_technicals, fetch_technicals_async
from .levels import calculate_range_levels, detect_swing_points, find_nearest_levels
from .patterns import (
    calculate_closed_at_low,
    calculate_volume_vs_avg,
    detect_candlestick_patterns,
)
from .trend import classify_trend, generate_analysis_text

__all__ = [
    "_sanitize_numpy",
    "calculate_closed_at_low",
    "calculate_range_levels",
    "calculate_volume_vs_avg",
    "classify_trend",
    "detect_candlestick_patterns",
    "detect_swing_points",
    "fetch_technicals",
    "fetch_technicals_async",
    "find_nearest_levels",
    "generate_analysis_text",
]
