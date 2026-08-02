"""Calibration staleness + phantom-metric thresholds (SWI-15).

Single source of truth for the constants the retro pipeline + context
blocks both consume. Kept under `shared.rules.` so future agents and
tests can import the same values.
"""

from __future__ import annotations

MIN_CALIBRATION_SAMPLE = 3
CALIBRATION_STALENESS_DAYS = 5

# The five ratio fields that become statistically meaningless when
# `sample_size < MIN_CALIBRATION_SAMPLE`. Loop this constant from the
# phantom-metric guard so a future field addition cannot drift.
RATIO_FIELDS = (
    "avg_actual_rr",
    "avg_predicted_rr",
    "target_hit_rate",
    "pct_entries_unreachable",
    "pct_stops_too_tight",
)
