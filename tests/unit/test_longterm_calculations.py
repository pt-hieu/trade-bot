"""Unit tests for longterm_calculations.py — all deterministic, no DB/LLM calls."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from shared.longterm_calculations import (
    CONVICTION_LEVELS,
    _percentile,
    _score_to_conviction,
    adjust_conviction,
    apply_entry_zone_adjustment,
    calculate_entry_zone,
    compute_review_flags,
    score_conviction,
    screen_candidates,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_ratio(
    pe=18.0,
    pb=3.0,
    roe=22.0,
    roa=8.0,
    net_margin=12.0,
    gross_margin=35.0,
    eps=5000.0,
    debt_to_equity=0.5,
    current_ratio=1.5,
    report_period="2025Q4",
):
    return {
        "report_period": report_period,
        "pe": pe,
        "pb": pb,
        "roe": roe,
        "roa": roa,
        "net_margin": net_margin,
        "gross_margin": gross_margin,
        "eps": eps,
        "debt_to_equity": debt_to_equity,
        "current_ratio": current_ratio,
    }


GOOD_RATIOS = [
    _make_ratio(pe=18, roe=25.0, eps=5500, report_period="2025Q4"),
    _make_ratio(pe=17, roe=23.0, eps=5200, report_period="2025Q3"),
    _make_ratio(pe=20, roe=21.0, eps=4900, report_period="2025Q2"),
    _make_ratio(pe=22, roe=20.0, eps=4600, report_period="2025Q1"),
    _make_ratio(pe=24, roe=19.0, eps=4300, report_period="2024Q4"),
    _make_ratio(pe=21, roe=18.0, eps=4000, report_period="2024Q3"),
    _make_ratio(pe=19, roe=17.0, eps=3800, report_period="2024Q2"),
    _make_ratio(pe=23, roe=16.0, eps=3500, report_period="2024Q1"),
]


# ── _percentile ────────────────────────────────────────────────────────────────


def test_percentile_25th():
    values = [10, 20, 30, 40, 50]
    result = _percentile(values, 25)
    assert 17 < result < 23


def test_percentile_50th():
    values = [10, 20, 30, 40, 50]
    result = _percentile(values, 50)
    assert result == 30.0


def test_percentile_single_element():
    assert _percentile([42.0], 25) == 42.0


# ── _score_to_conviction ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "score,expected",
    [
        (75, "High"),
        (70, "High"),
        (55, "Medium-High"),
        (50, "Medium-High"),
        (35, "Medium"),
        (30, "Medium"),
        (18, "Medium-Low"),
        (15, "Medium-Low"),
        (10, "Low"),
        (0, "Low"),
    ],
)
def test_score_to_conviction(score, expected):
    assert _score_to_conviction(score) == expected


# ── calculate_entry_zone ──────────────────────────────────────────────────────


def test_calculate_entry_zone_returns_int():
    entry, method = calculate_entry_zone(GOOD_RATIOS, low_52w=80000, current_entry_vnd=95000)
    assert isinstance(entry, int)
    assert method == "calculated"


def test_calculate_entry_zone_fallback_insufficient_data():
    entry, method = calculate_entry_zone(GOOD_RATIOS[:2], None, 95000)
    assert entry == 95000
    assert method == "manual_fallback"


def test_calculate_entry_zone_no_data_fallback():
    entry, method = calculate_entry_zone([], None, 90000)
    assert entry == 90000
    assert method == "manual_fallback"


def test_calculate_entry_zone_rounded_to_1000():
    entry, method = calculate_entry_zone(GOOD_RATIOS, None, 95000)
    if entry:
        assert entry % 1000 == 0


def test_calculate_entry_zone_positive():
    entry, _ = calculate_entry_zone(GOOD_RATIOS, low_52w=70000, current_entry_vnd=95000)
    if entry:
        assert entry > 0


# ── score_conviction ──────────────────────────────────────────────────────────


def test_score_conviction_high_quality():
    level, score = score_conviction("FPT", GOOD_RATIOS)
    assert level in CONVICTION_LEVELS
    assert score >= 50  # good fundamentals = Medium-High or better


def test_score_conviction_no_data():
    level, score = score_conviction("FPT", [])
    assert level == "Medium"
    assert score == 30


def test_score_conviction_poor_fundamentals():
    poor = [_make_ratio(pe=35, roe=5.0, net_margin=2.0, debt_to_equity=2.5, current_ratio=0.8)]
    level, score = score_conviction("TEST", poor)
    assert level in ("Low", "Medium-Low", "Medium")
    assert score < 30


def test_score_conviction_bank_high_de():
    # Banks have higher D/E threshold — 2.0 should NOT trigger penalty for bank
    bank_ratio = [_make_ratio(roe=18.0, net_margin=15.0, debt_to_equity=1.8, pe=12)]
    level_bank, score_bank = score_conviction("TCB", bank_ratio)
    level_other, score_other = score_conviction("FPT", bank_ratio)
    # Bank should score same or better (D/E 1.8 < 2.0 bank threshold, < 1.0 non-bank threshold)
    assert score_bank >= score_other


# ── adjust_conviction ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "current,adj,expected",
    [
        ("Medium", 0, "Medium"),
        ("Medium", 1, "Medium-High"),
        ("Medium", -1, "Medium-Low"),
        ("High", 1, "High"),  # capped at top
        ("Low", -1, "Low"),  # capped at bottom
        ("Medium", 2, "Medium-High"),  # adj capped at ±1
        ("Medium-High", -1, "Medium"),
    ],
)
def test_adjust_conviction(current, adj, expected):
    assert adjust_conviction(current, adj) == expected


# ── apply_entry_zone_adjustment ───────────────────────────────────────────────


def test_apply_entry_zone_positive():
    result = apply_entry_zone_adjustment(100_000, 5.0)
    assert result == 105_000


def test_apply_entry_zone_negative():
    result = apply_entry_zone_adjustment(100_000, -10.0)
    assert result == 90_000


def test_apply_entry_zone_capped_at_10():
    result = apply_entry_zone_adjustment(100_000, 15.0)  # cap at 10%
    assert result == 110_000


def test_apply_entry_zone_capped_at_minus_10():
    result = apply_entry_zone_adjustment(100_000, -20.0)  # cap at -10%
    assert result == 90_000


def test_apply_entry_zone_rounded_to_1000():
    result = apply_entry_zone_adjustment(95_500, 3.0)
    assert result % 1000 == 0


# ── compute_review_flags ──────────────────────────────────────────────────────


def test_no_flags_for_healthy_stock():
    flags = compute_review_flags("FPT", GOOD_RATIOS, "Medium-High", "Medium-High")
    assert "ROE_BELOW_8PCT_2Q" not in flags
    assert "HIGH_DEBT" not in flags


def test_roe_below_8pct_flag():
    poor_roe = [
        _make_ratio(roe=5.0, report_period="2025Q4"),
        _make_ratio(roe=4.0, report_period="2025Q3"),
    ]
    flags = compute_review_flags("FPT", poor_roe, "Medium-Low", "Medium")
    assert "ROE_BELOW_8PCT_2Q" in flags


def test_no_roe_flag_one_quarter():
    one_bad = [
        _make_ratio(roe=4.0, report_period="2025Q4"),
        _make_ratio(roe=15.0, report_period="2025Q3"),
    ]
    flags = compute_review_flags("FPT", one_bad, "Medium", "Medium")
    assert "ROE_BELOW_8PCT_2Q" not in flags


def test_conviction_downgrade_flag():
    flags = compute_review_flags(
        "FPT",
        GOOD_RATIOS[:2],
        calculated_conviction="Low",
        current_conviction="High",
    )
    assert "CONVICTION_DOWNGRADE_2+" in flags


def test_no_conviction_downgrade_one_level():
    flags = compute_review_flags(
        "FPT",
        GOOD_RATIOS[:2],
        calculated_conviction="Medium-High",
        current_conviction="High",
    )
    assert "CONVICTION_DOWNGRADE_2+" not in flags


def test_high_debt_flag():
    high_de = [_make_ratio(debt_to_equity=2.0)]
    flags = compute_review_flags("FPT", high_de, "Medium", "Medium")
    assert "HIGH_DEBT" in flags


def test_no_financial_data_flag():
    flags = compute_review_flags("FPT", [], "Medium", "Medium")
    assert "NO_FINANCIAL_DATA" in flags


# ── screen_candidates ─────────────────────────────────────────────────────────


def test_screen_candidates_filters_existing():
    ratios_batch = {
        "FPT": _make_ratio(roe=25.0, pe=18, net_margin=12.0),
        "TCB": _make_ratio(roe=20.0, pe=12, net_margin=15.0),
        "NEW1": _make_ratio(roe=18.0, pe=20, net_margin=10.0),
    }
    existing = {"FPT", "TCB"}
    candidates = screen_candidates(ratios_batch, existing)
    tickers = [c["ticker"] for c in candidates]
    assert "FPT" not in tickers
    assert "TCB" not in tickers
    assert "NEW1" in tickers


def test_screen_candidates_filters_low_roe():
    ratios_batch = {
        "LOW1": _make_ratio(roe=5.0, pe=18, net_margin=10.0),
    }
    candidates = screen_candidates(ratios_batch, set())
    assert len(candidates) == 0


def test_screen_candidates_filters_high_pe():
    ratios_batch = {
        "HIGH_PE": _make_ratio(roe=20.0, pe=35, net_margin=10.0),
    }
    candidates = screen_candidates(ratios_batch, set())
    assert len(candidates) == 0


def test_screen_candidates_sorted_by_score():
    ratios_batch = {
        "A": _make_ratio(roe=25.0, pe=15, net_margin=15.0, debt_to_equity=0.3),
        "B": _make_ratio(roe=12.0, pe=28, net_margin=8.0, debt_to_equity=1.0),
    }
    candidates = screen_candidates(ratios_batch, set())
    assert candidates[0]["ticker"] == "A"  # A has higher score


def test_screen_candidates_includes_sector():
    ratios_batch = {"HPG": _make_ratio(roe=15.0, pe=12, net_margin=10.0)}
    candidates = screen_candidates(ratios_batch, set(), {"HPG": "Infrastructure"})
    assert candidates[0]["sector"] == "Infrastructure"
