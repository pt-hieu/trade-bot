"""
Tests for _score_thresholds() and _classify_stock_category() in agents/screening.py.

Run: uv run pytest tests/unit/test_screening.py -v --tb=short
"""

from types import SimpleNamespace

import pytest

from agents.screening import _classify_stock_category, _score_thresholds


def make_cfg(
    screen_max_pe=25,
    screen_max_pb=3.0,
    screen_min_roe_pct=8.0,
    screen_min_margin_pct=5.0,
    screen_max_de=2.0,
    screen_bank_max_de=10.0,
    screen_tolerance_pct=0.10,
    screen_composite_limit=1.0,
):
    """Factory for mock config with screening threshold attributes."""
    return SimpleNamespace(
        screen_max_pe=screen_max_pe,
        screen_max_pb=screen_max_pb,
        screen_min_roe_pct=screen_min_roe_pct,
        screen_min_margin_pct=screen_min_margin_pct,
        screen_max_de=screen_max_de,
        screen_bank_max_de=screen_bank_max_de,
        screen_tolerance_pct=screen_tolerance_pct,
        screen_composite_limit=screen_composite_limit,
    )


def make_ratios(
    pe=15.0,
    pb=1.5,
    roe=12.0,
    net_margin=8.0,
    debt_to_equity=1.0,
):
    """Factory for a passing ratios dict."""
    return {
        "pe": pe,
        "pb": pb,
        "roe": roe,
        "net_margin": net_margin,
        "debt_to_equity": debt_to_equity,
    }


class TestScoreThresholds:
    """Tests for _score_thresholds(ratios, cfg, sector_row)."""

    def test_all_ratios_within_thresholds_no_hard_fail(self):
        cfg = make_cfg()
        ratios = make_ratios()

        result = _score_thresholds(ratios, cfg, None)

        assert result["hard_fail_metrics"] == []
        assert result["soft_miss_reasons"] == []
        assert result["composite"] == 0.0

    def test_pe_exceeds_max_hard_fails(self):
        # pe=30 vs max=25: distance=0.20 > tolerance 0.10 → hard
        cfg = make_cfg(screen_max_pe=25)
        ratios = make_ratios(pe=30.0)

        result = _score_thresholds(ratios, cfg, None)

        assert any("PE" in r for r in result["hard_fail_metrics"])
        assert result["scores"]["PE"] == 2

    def test_negative_pe_skipped_no_failure(self):
        # Negative PE = loss-making; handled by margin check, not PE check
        cfg = make_cfg(screen_max_pe=25)
        ratios = make_ratios(pe=-5.0)

        result = _score_thresholds(ratios, cfg, None)

        assert all("PE" not in r for r in result["hard_fail_metrics"])
        assert all("PE" not in r for r in result["soft_miss_reasons"])

    def test_pb_exceeds_max_hard_fails(self):
        cfg = make_cfg(screen_max_pb=3.0)
        ratios = make_ratios(pb=4.5)

        result = _score_thresholds(ratios, cfg, None)

        assert any("PB" in r for r in result["hard_fail_metrics"])
        assert result["scores"]["PB"] == 2

    def test_roe_below_min_hard_fails(self):
        cfg = make_cfg(screen_min_roe_pct=8.0)
        ratios = make_ratios(roe=5.0)

        result = _score_thresholds(ratios, cfg, None)

        assert any("ROE" in r for r in result["hard_fail_metrics"])
        assert result["scores"]["ROE"] == 2

    def test_margin_below_min_hard_fails(self):
        cfg = make_cfg(screen_min_margin_pct=5.0)
        ratios = make_ratios(net_margin=2.0)

        result = _score_thresholds(ratios, cfg, None)

        assert any("Margin" in r for r in result["hard_fail_metrics"])
        assert result["scores"]["Margin"] == 2

    def test_de_exceeds_max_without_sector_override_hard_fails(self):
        cfg = make_cfg(screen_max_de=2.0)
        ratios = make_ratios(debt_to_equity=3.5)

        result = _score_thresholds(ratios, cfg, None)

        assert any("D/E" in r for r in result["hard_fail_metrics"])
        assert result["scores"]["D/E"] == 2

    def test_sector_override_relaxes_de_threshold(self):
        # Bank sector override max_de=10.0 supersedes cfg.screen_max_de=2.0
        cfg = make_cfg(screen_max_de=2.0)
        ratios = make_ratios(debt_to_equity=8.0)
        sector_row = {"sector_name": "banking", "max_de": 10.0}

        result = _score_thresholds(ratios, cfg, sector_row)

        assert all("D/E" not in r for r in result["hard_fail_metrics"])
        assert result["composite"] == 0.0

    def test_sector_override_still_fails_when_exceeded(self):
        cfg = make_cfg(screen_max_de=2.0)
        ratios = make_ratios(debt_to_equity=12.0)
        sector_row = {"sector_name": "banking", "max_de": 10.0}

        result = _score_thresholds(ratios, cfg, sector_row)

        assert any("D/E" in r for r in result["hard_fail_metrics"])
        assert result["scores"]["D/E"] == 2

    def test_multiple_hard_fails_all_listed(self):
        cfg = make_cfg(screen_max_pe=25, screen_max_pb=3.0, screen_min_roe_pct=8.0)
        ratios = make_ratios(pe=40.0, pb=5.0, roe=3.0)

        result = _score_thresholds(ratios, cfg, None)

        fails = " ".join(result["hard_fail_metrics"])
        assert "PE" in fails
        assert "PB" in fails
        assert "ROE" in fails
        assert result["scores"]["PE"] == 2
        assert result["scores"]["PB"] == 2
        assert result["scores"]["ROE"] == 2

    @pytest.mark.parametrize("ratio_key", ["pe", "pb", "roe", "net_margin", "debt_to_equity"])
    def test_none_value_for_ratio_skips_check(self, ratio_key):
        # None means data unavailable — should not generate a failure
        cfg = make_cfg()
        ratios = make_ratios()
        ratios[ratio_key] = None

        result = _score_thresholds(ratios, cfg, None)

        assert result["hard_fail_metrics"] == []
        assert result["soft_miss_reasons"] == []

    def test_soft_miss_within_tolerance_band(self):
        # pe=26.5 vs max=25: distance=0.06 < tolerance 0.10 → soft
        cfg = make_cfg(screen_max_pe=25, screen_tolerance_pct=0.10)
        ratios = make_ratios(pe=26.5)

        result = _score_thresholds(ratios, cfg, None)

        assert "PE" not in result["hard_fail_metrics"]
        assert any("PE" in r for r in result["soft_miss_reasons"])
        assert result["scores"]["PE"] == 1


class TestClassifyStockCategory:
    """Tests for _classify_stock_category(ticker, ratios, core_ratio)."""

    def test_speculative_when_core_ratio_below_0_3(self):
        ratios = make_ratios(roe=15.0, net_margin=10.0)

        category = _classify_stock_category("FPT", ratios, core_ratio=0.2)

        assert category == "SPECULATIVE"

    def test_value_trap_when_low_pe_and_weak_roe(self):
        ratios = make_ratios(pe=7.0, roe=5.0, net_margin=8.0)

        category = _classify_stock_category("FPT", ratios, core_ratio=0.6)

        assert category == "VALUE_TRAP"

    def test_value_trap_when_low_pe_and_low_core_ratio(self):
        ratios = make_ratios(pe=8.0, roe=12.0, net_margin=8.0)

        category = _classify_stock_category("FPT", ratios, core_ratio=0.35)

        assert category == "VALUE_TRAP"

    def test_growth_when_roe_margin_and_core_ratio_all_strong(self):
        ratios = make_ratios(pe=18.0, roe=15.0, net_margin=9.0)

        category = _classify_stock_category("FPT", ratios, core_ratio=0.75)

        assert category == "GROWTH"

    def test_default_growth_for_stocks_passing_ratio_screens(self):
        ratios = make_ratios(pe=20.0, roe=9.0, net_margin=4.0)

        category = _classify_stock_category("FPT", ratios, core_ratio=0.5)

        assert category == "GROWTH"

    def test_core_ratio_none_treated_as_1_0(self):
        ratios = make_ratios(pe=18.0, roe=15.0, net_margin=9.0)

        category = _classify_stock_category("FPT", ratios, core_ratio=None)

        assert category == "GROWTH"

    def test_core_ratio_exactly_0_3_is_not_speculative(self):
        ratios = make_ratios(pe=18.0, roe=15.0, net_margin=9.0)

        category = _classify_stock_category("FPT", ratios, core_ratio=0.3)

        assert category != "SPECULATIVE"

    def test_core_ratio_just_below_0_3_is_speculative(self):
        ratios = make_ratios(pe=18.0, roe=15.0, net_margin=9.0)

        category = _classify_stock_category("FPT", ratios, core_ratio=0.29)

        assert category == "SPECULATIVE"
