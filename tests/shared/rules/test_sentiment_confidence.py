"""Tests for shared.rules.sentiment_confidence (SWI-103)."""

from __future__ import annotations

from shared.rules.sentiment_confidence import (
    CONFIDENCE_RANK,
    is_trusted,
    max_confidence,
)


class TestIsTrusted:
    def test_high_is_trusted(self):
        assert is_trusted("high")

    def test_medium_is_trusted(self):
        assert is_trusted("medium")

    def test_low_is_not_trusted(self):
        assert not is_trusted("low")

    def test_abstain_is_not_trusted(self):
        assert not is_trusted("abstain")

    def test_none_is_not_trusted(self):
        assert not is_trusted(None)

    def test_unknown_string_is_not_trusted(self):
        assert not is_trusted("garbage")


class TestMaxConfidence:
    def test_picks_high_over_medium(self):
        assert max_confidence(["medium", "high"]) == "high"

    def test_picks_medium_over_low(self):
        assert max_confidence(["low", "medium"]) == "medium"

    def test_skips_none(self):
        assert max_confidence([None, "low", None]) == "low"

    def test_all_none_returns_none(self):
        assert max_confidence([None, None]) is None

    def test_empty_returns_none(self):
        assert max_confidence([]) is None


class TestRanking:
    def test_rank_total_order(self):
        assert (
            CONFIDENCE_RANK["abstain"]
            < CONFIDENCE_RANK["low"]
            < CONFIDENCE_RANK["medium"]
            < CONFIDENCE_RANK["high"]
        )
