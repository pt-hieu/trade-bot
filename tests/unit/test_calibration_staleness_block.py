"""SWI-15: staleness banner driven by calibration row."""

from __future__ import annotations

from pipeline.context_blocks_calibration import (
    _format_calibration_staleness_banner,
)


def test_banner_when_swing_sample_size_low():
    banner = _format_calibration_staleness_banner({"swing_sample_size": 1, "staleness_days": 1})
    assert "Calibration data is stale" in banner
    assert "proceed with normal entry sizing" in banner


def test_banner_when_staleness_days_high():
    banner = _format_calibration_staleness_banner({"swing_sample_size": 10, "staleness_days": 10})
    assert "10 days since last trade exit" in banner


def test_no_banner_when_fresh():
    banner = _format_calibration_staleness_banner({"swing_sample_size": 10, "staleness_days": 1})
    assert banner == ""


def test_no_banner_when_missing_fields():
    banner = _format_calibration_staleness_banner({})
    assert banner == ""
