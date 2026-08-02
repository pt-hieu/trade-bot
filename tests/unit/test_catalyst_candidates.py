"""Coverage for select_catalyst_candidates — DEF-005 bounded universe selector.

Pure deterministic Python. Hardest test to get right: the dedup precedence
of (impact_rank, confidence_rank). A ticker named by multiple catalysts
must keep the highest-ranked pair; NEGATIVE and LOW catalysts never
produce candidates regardless of universe overlap.
"""

from __future__ import annotations

from shared.rules.catalyst_candidates import select_catalyst_candidates


def _catalyst(
    *,
    catalyst_key: str = "c1",
    event: str = "fuel tax 0%",
    impact: str = "POSITIVE",
    confidence: str = "HIGH",
    affected_tickers: list[str] | None = None,
) -> dict:
    return {
        "catalyst_key": catalyst_key,
        "event": event,
        "impact": impact,
        "confidence": confidence,
        "affected_tickers": affected_tickers or ["PLX", "BSR"],
    }


class TestCandidateSelectorEligibility:
    def test_high_positive_produces_candidates_in_universe(self) -> None:
        candidates = select_catalyst_candidates(
            changed_catalysts=[_catalyst()],
            holdings_tickers={"PLX"},
            watchlist_tickers={"BSR"},
        )
        tickers = {c["ticker"] for c in candidates}
        assert tickers == {"PLX", "BSR"}
        for candidate in candidates:
            assert candidate["impact"] == "POSITIVE"
            assert candidate["confidence"] == "HIGH"

    def test_medium_positive_produces_candidates(self) -> None:
        candidates = select_catalyst_candidates(
            changed_catalysts=[_catalyst(confidence="MEDIUM")],
            holdings_tickers=set(),
            watchlist_tickers={"PLX", "BSR"},
        )
        assert {c["ticker"] for c in candidates} == {"PLX", "BSR"}

    def test_low_positive_rejected(self) -> None:
        candidates = select_catalyst_candidates(
            changed_catalysts=[_catalyst(confidence="LOW")],
            holdings_tickers={"PLX"},
            watchlist_tickers={"BSR"},
        )
        assert candidates == []

    def test_negative_high_rejected_even_for_held_ticker(self) -> None:
        # Critical: a NEGATIVE catalyst naming a held ticker must NOT
        # produce a BUY candidate. Fail-closed.
        candidates = select_catalyst_candidates(
            changed_catalysts=[_catalyst(impact="NEGATIVE", confidence="HIGH")],
            holdings_tickers={"PLX"},
            watchlist_tickers={"BSR"},
        )
        assert candidates == []

    def test_neutral_rejected(self) -> None:
        candidates = select_catalyst_candidates(
            changed_catalysts=[_catalyst(impact="NEUTRAL", confidence="HIGH")],
            holdings_tickers={"PLX"},
            watchlist_tickers=set(),
        )
        assert candidates == []


class TestCandidateSelectorUniverseBound:
    def test_out_of_universe_ticker_not_promoted(self) -> None:
        # HIGH/POSITIVE catalyst naming a ticker we don't hold or watch:
        # no candidate emitted. Catalyst revision may NEVER widen the
        # tradable set.
        candidates = select_catalyst_candidates(
            changed_catalysts=[_catalyst(affected_tickers=["OUTSIDER"])],
            holdings_tickers={"PLX"},
            watchlist_tickers={"BSR"},
        )
        assert candidates == []

    def test_partial_universe_overlap_keeps_only_held_or_watched(self) -> None:
        candidates = select_catalyst_candidates(
            changed_catalysts=[_catalyst(affected_tickers=["PLX", "OUTSIDER", "BSR"])],
            holdings_tickers={"PLX"},
            watchlist_tickers={"BSR"},
        )
        assert {c["ticker"] for c in candidates} == {"PLX", "BSR"}

    def test_empty_universe_returns_empty(self) -> None:
        candidates = select_catalyst_candidates(
            changed_catalysts=[_catalyst()],
            holdings_tickers=set(),
            watchlist_tickers=set(),
        )
        assert candidates == []

    def test_case_insensitive_universe_match(self) -> None:
        # Universe can arrive either case; selector upper-cases both sides.
        candidates = select_catalyst_candidates(
            changed_catalysts=[_catalyst(affected_tickers=["plx"])],
            holdings_tickers={"PLX"},
            watchlist_tickers=set(),
        )
        assert [c["ticker"] for c in candidates] == ["PLX"]


class TestCandidateSelectorDedup:
    def test_same_ticker_across_catalysts_keeps_higher_confidence(self) -> None:
        medium = _catalyst(
            catalyst_key="weak",
            confidence="MEDIUM",
            affected_tickers=["PLX"],
        )
        high = _catalyst(
            catalyst_key="strong",
            confidence="HIGH",
            affected_tickers=["PLX"],
        )
        # Order intentionally medium first so selector must replace.
        candidates = select_catalyst_candidates(
            changed_catalysts=[medium, high],
            holdings_tickers={"PLX"},
            watchlist_tickers=set(),
        )
        assert len(candidates) == 1
        assert candidates[0]["catalyst_key"] == "strong"
        assert candidates[0]["confidence"] == "HIGH"

    def test_tie_keeps_first_seen(self) -> None:
        first = _catalyst(catalyst_key="first", affected_tickers=["PLX"])
        second = _catalyst(catalyst_key="second", affected_tickers=["PLX"])
        candidates = select_catalyst_candidates(
            changed_catalysts=[first, second],
            holdings_tickers={"PLX"},
            watchlist_tickers=set(),
        )
        assert len(candidates) == 1
        assert candidates[0]["catalyst_key"] == "first"


class TestCandidateSelectorRawShape:
    def test_empty_catalyst_list_returns_empty(self) -> None:
        assert (
            select_catalyst_candidates(
                changed_catalysts=[],
                holdings_tickers={"PLX"},
                watchlist_tickers={"BSR"},
            )
            == []
        )

    def test_affected_fallback_field(self) -> None:
        # Revision sometimes uses legacy `affected` key — selector accepts
        # both shapes.
        catalyst = {
            "catalyst_key": "c1",
            "event": "fuel tax",
            "impact": "POSITIVE",
            "confidence": "HIGH",
            "affected": ["PLX"],
        }
        candidates = select_catalyst_candidates(
            changed_catalysts=[catalyst],
            holdings_tickers={"PLX"},
            watchlist_tickers=set(),
        )
        assert [c["ticker"] for c in candidates] == ["PLX"]
