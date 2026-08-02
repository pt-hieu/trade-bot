"""Tests for shared.rules.macro_stress.classify_underlying_stress."""

from __future__ import annotations

import pytest

from shared.rules.macro_stress import classify_underlying_stress


class TestFailClosedDefaults:
    """Fail-closed invariant — missing data is MOST CONSERVATIVE (True)."""

    def test_none_metrics_returns_true(self) -> None:
        assert classify_underlying_stress(None) is True

    def test_empty_dict_returns_true(self) -> None:
        assert classify_underlying_stress({}) is True

    def test_error_flag_returns_true(self) -> None:
        assert classify_underlying_stress({"error": "vnstock outage"}) is True

    def test_all_signals_blank_returns_true(self) -> None:
        assert (
            classify_underlying_stress({"vix_signal": "", "dxy_signal": "", "usd_vnd_signal": ""})
            is True
        )


class TestCalmSignals:
    """All-calm indicators → no stress."""

    def test_calm_all(self) -> None:
        metrics = {"vix_signal": "LOW", "dxy_signal": "WEAK", "usd_vnd_signal": "STABLE"}
        assert classify_underlying_stress(metrics) is False

    def test_moderate_vix_without_other_stress(self) -> None:
        metrics = {
            "vix_signal": "MODERATE",
            "dxy_signal": "NEUTRAL",
            "usd_vnd_signal": "STABLE",
        }
        assert classify_underlying_stress(metrics) is False


class TestStressedSignals:
    """Any single stressed channel triggers True."""

    @pytest.mark.parametrize("vix_signal", ["HIGH", "EXTREME"])
    def test_vix_stress(self, vix_signal: str) -> None:
        metrics = {
            "vix_signal": vix_signal,
            "dxy_signal": "WEAK",
            "usd_vnd_signal": "STABLE",
        }
        assert classify_underlying_stress(metrics) is True

    def test_dxy_strong(self) -> None:
        metrics = {
            "vix_signal": "LOW",
            "dxy_signal": "STRONG",
            "usd_vnd_signal": "STABLE",
        }
        assert classify_underlying_stress(metrics) is True

    @pytest.mark.parametrize("usd_vnd_signal", ["PRESSURE", "FLIGHT"])
    def test_usd_vnd_stress(self, usd_vnd_signal: str) -> None:
        metrics = {
            "vix_signal": "LOW",
            "dxy_signal": "WEAK",
            "usd_vnd_signal": usd_vnd_signal,
        }
        assert classify_underlying_stress(metrics) is True

    def test_case_insensitive(self) -> None:
        metrics = {
            "vix_signal": "high",
            "dxy_signal": "weak",
            "usd_vnd_signal": "stable",
        }
        assert classify_underlying_stress(metrics) is True


class TestReproducesAprilTwentyBug:
    """VIX LOW + DXY WEAK + USD/VND STABLE = no underlying stress.

    On 2026-04-20 the regime was pinned to ELEVATED by the Hormuz geopolitical
    shock phase floor while these three indicators were all calm. The
    recommendation gate uses this classification to apply the shock-only
    2.5 floor instead of the full 3.0 stressed floor.
    """

    def test_april_20_macro_snapshot(self) -> None:
        april_20 = {
            "vix_value": 17.48,
            "vix_signal": "LOW",
            "dxy_value": 98.1,
            "dxy_signal": "WEAK",
            "usd_vnd_rate": 26400,
            "usd_vnd_signal": "STABLE",
        }
        assert classify_underlying_stress(april_20) is False
