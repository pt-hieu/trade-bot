"""SWI-15: phantom-metric guard NULLs ratio fields when sample_size < 3."""

from __future__ import annotations

from agents.retro.calibration import _phantom_guard
from shared.rules.calibration import MIN_CALIBRATION_SAMPLE, RATIO_FIELDS


def _full_stats() -> dict:
    return {
        "avg_actual_rr": 3.4,
        "avg_predicted_rr": 2.8,
        "target_hit_rate": 60.0,
        "pct_entries_unreachable": 30.0,
        "pct_stops_too_tight": 25.0,
        "avg_entry_gap_pct": 0.5,
        "sample_size": 1,
    }


def test_phantom_guard_nulls_all_ratio_fields_below_threshold():
    stats = _full_stats()
    out = _phantom_guard(stats, sample_size=1)
    for field in RATIO_FIELDS:
        assert out[field] is None, f"{field} should be NULL when n<{MIN_CALIBRATION_SAMPLE}"
    # Non-ratio field passes through.
    assert out["avg_entry_gap_pct"] == 0.5
    assert out["sample_size"] == 1


def test_phantom_guard_passes_through_above_threshold():
    stats = _full_stats()
    out = _phantom_guard(stats, sample_size=MIN_CALIBRATION_SAMPLE)
    for field in RATIO_FIELDS:
        assert out[field] is not None


def test_loop_uses_constant_so_new_field_is_guarded():
    stats = {field: 1.0 for field in RATIO_FIELDS}
    stats["sample_size"] = 0
    out = _phantom_guard(stats, sample_size=0)
    for field in RATIO_FIELDS:
        assert out[field] is None
