#!/usr/bin/env python3
"""Unit tests for watchlist score validation."""

from scripts.agents.watchlist_update import StockScore


def test_correct_score_unchanged():
    """Score matches sum of points - no change."""
    s = StockScore(
        ticker="TCB",
        sector="Banking",
        score=55,
        confidence="high",
        reasons=["RSI 29 (+30)", "Hot sector (+15)", "Liquidity (+10)"],
    )
    assert s.score == 55


def test_incorrect_score_corrected():
    """SHB case: reported 50, reasons sum to 40."""
    s = StockScore(
        ticker="SHB",
        sector="Banking",
        score=50,
        confidence="medium",
        reasons=[
            "RSI 37 (+20)",
            "Good liquidity (+10)",
            "Price 1.6% above support (+10)",
            "Banking sector near buy zone (+15)",
            "Downtrend (-10)",
            "Bearish momentum (-5)",
        ],
    )
    assert s.score == 40


def test_no_points_format_returns_zero():
    """SWI-295: reasons without (+N) tags → computed score is 0.

    Previously the LLM-emitted score field was retained when no tags were
    present. Now `score` is a @computed_field; the LLM never authors it.
    """
    s = StockScore(
        ticker="FPT",
        sector="Technology",
        confidence="high",
        reasons=["RSI oversold", "Hot sector", "Good momentum"],
    )
    assert s.score == 0


def test_negative_points():
    """BCM case: mixed positive and negative points."""
    s = StockScore(
        ticker="BCM",
        sector="Real Estate",
        score=55,
        confidence="medium",
        reasons=[
            "RSI 29 oversold (+30)",
            "Oversold setup (+20)",
            "Good liquidity (+10)",
            "Price near support (+10)",
            "Inverted hammer pattern (+10)",
            "Cold sector (-25)",
        ],
    )
    assert s.score == 55


def test_score_drops_below_threshold():
    """Score corrected from 50 to 40 - threshold enforcement is separate."""
    s = StockScore(
        ticker="XYZ",
        sector="Banking",
        score=50,
        confidence="low",
        reasons=["RSI (+20)", "Sector (+20)"],
    )
    assert s.score == 40


def test_all_negative_points():
    """All reasons are penalties."""
    s = StockScore(
        ticker="BAD",
        sector="Tech",
        score=0,
        confidence="low",
        reasons=["Overbought (-30)", "Cold sector (-20)"],
    )
    assert s.score == -50


def test_single_reason():
    """Single reason with points."""
    s = StockScore(
        ticker="ONE",
        sector="Banking",
        score=99,
        confidence="high",
        reasons=["RSI 28 (+30)"],
    )
    assert s.score == 30


def test_empty_reasons_list():
    """SWI-295: empty reasons list → computed score is 0."""
    s = StockScore(
        ticker="EMPTY",
        sector="Banking",
        confidence="low",
        reasons=[],
    )
    assert s.score == 0
