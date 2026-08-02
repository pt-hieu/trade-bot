"""Tests for shared.rules.catalyst_expected_parser.parse_expected.

Bridges the LLM-emitted free text on `CatalystAddition.expected` to
`(date | None, expected_status)`. Parametrized per shape bucket plus the
bias-to-ongoing rule (round-2 review fix) so the lifecycle scorer never
gets flooded with false `unparseable` rows on plain narrative.
"""

from __future__ import annotations

from datetime import date

import pytest

from shared.rules.catalyst_expected_parser import parse_expected

TODAY = date(2026, 4, 27)


class TestOngoingPhrases:
    @pytest.mark.parametrize(
        "expected",
        [
            "ongoing",
            "Ongoing",
            "ONGOING",
            "Effective immediately",
            "effective immediately.",
            "continuous",
            "indefinite",
            "TBD",
            "Until further notice",
            "in due course",
            "n/a",
            "N/A",
            "none",
            "",
        ],
    )
    def test_ongoing_phrase_set(self, expected: str) -> None:
        parsed_date, status = parse_expected(expected, TODAY)
        assert parsed_date is None
        assert status == "ongoing"

    def test_none_input(self) -> None:
        parsed_date, status = parse_expected(None, TODAY)
        assert parsed_date is None
        assert status == "ongoing"


class TestIsoDate:
    @pytest.mark.parametrize(
        ("expected", "want_date"),
        [
            ("2026-08-15", date(2026, 8, 15)),
            ("decision on 2026-08-15", date(2026, 8, 15)),
            ("2026/08/15", date(2026, 8, 15)),
            ("2026-1-5", date(2026, 1, 5)),
        ],
    )
    def test_iso_dates(self, expected: str, want_date: date) -> None:
        parsed_date, status = parse_expected(expected, TODAY)
        assert parsed_date == want_date
        assert status == "dated"


class TestQuarter:
    @pytest.mark.parametrize(
        ("expected", "want_date"),
        [
            ("Q3 2026", date(2026, 9, 30)),
            ("q3 2026", date(2026, 9, 30)),
            ("Q1 2026", date(2026, 3, 31)),
            ("Q4 2026", date(2026, 12, 31)),
            ("expected Q2 2027", date(2027, 6, 30)),
            ("2026 Q3", date(2026, 9, 30)),
        ],
    )
    def test_quarter_labels(self, expected: str, want_date: date) -> None:
        parsed_date, status = parse_expected(expected, TODAY)
        assert parsed_date == want_date
        assert status == "quarter"


class TestMonthLabel:
    @pytest.mark.parametrize(
        ("expected", "want_date"),
        [
            ("August 2026", date(2026, 8, 31)),
            ("Aug 2026", date(2026, 8, 31)),
            ("Aug. 2026", date(2026, 8, 31)),
            ("February 2027", date(2027, 2, 28)),
            ("decision Sep 2026", date(2026, 9, 30)),
        ],
    )
    def test_month_labels(self, expected: str, want_date: date) -> None:
        parsed_date, status = parse_expected(expected, TODAY)
        assert parsed_date == want_date
        assert status == "month"


class TestEuDate:
    def test_eu_date(self) -> None:
        parsed_date, status = parse_expected("15/08/2026", TODAY)
        assert parsed_date == date(2026, 8, 15)
        assert status == "dated"

    def test_eu_date_dashes(self) -> None:
        parsed_date, status = parse_expected("15-08-2026", TODAY)
        assert parsed_date == date(2026, 8, 15)
        assert status == "dated"


class TestRelative:
    @pytest.mark.parametrize(
        ("expected", "want_date"),
        [
            ("next 30 days", date(2026, 5, 27)),
            ("in 2 weeks", date(2026, 5, 11)),
            ("in 3 months", date(2026, 7, 26)),
            ("decision in 7 days", date(2026, 5, 4)),
        ],
    )
    def test_relative_windows(self, expected: str, want_date: date) -> None:
        parsed_date, status = parse_expected(expected, TODAY)
        assert parsed_date == want_date
        assert status == "relative"


class TestBiasToOngoing:
    """Round-2 review fix: pure narrative without a temporal token must
    bias to `ongoing` (not `unparseable`) so the lifecycle scorer doesn't
    get flooded with false 14d-staleness rows."""

    @pytest.mark.parametrize(
        "expected",
        [
            "subject to regulatory approval",
            "pending",
            "to be confirmed",
            "expected soon",
            "shortly",
        ],
    )
    def test_narrative_without_temporal_token_is_ongoing(self, expected: str) -> None:
        parsed_date, status = parse_expected(expected, TODAY)
        assert parsed_date is None
        assert status == "ongoing"


class TestUnparseable:
    """Temporal token present but no recognised shape — surface for the
    14d staleness path so genuine parse-failures don't escape forever."""

    @pytest.mark.parametrize(
        "expected",
        [
            "expected within 6 weeks",  # has temporal token "weeks" but lacks 'in'/'next' prefix → unparseable
            "Q5 2026",  # invalid quarter label
            "decision in Octember 2026",  # malformed month
        ],
    )
    def test_temporal_token_with_failed_parse(self, expected: str) -> None:
        parsed_date, status = parse_expected(expected, TODAY)
        assert parsed_date is None
        assert status == "unparseable"


class TestPriority:
    """ISO date wins over EU date so 2026-08-15 doesn't get
    misread as 26 Aug 2015."""

    def test_iso_wins_over_eu(self) -> None:
        parsed_date, status = parse_expected("2026-08-15", TODAY)
        assert parsed_date == date(2026, 8, 15)
        assert status == "dated"

    def test_quarter_wins_over_year_only_month(self) -> None:
        parsed_date, status = parse_expected("Q3 2026", TODAY)
        assert parsed_date == date(2026, 9, 30)
        assert status == "quarter"
