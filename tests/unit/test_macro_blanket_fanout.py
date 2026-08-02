"""Tests for the macro-blanket fan-out + stacked-positive isolation rule.

Covers AUDIT-2026-04-24-001 / ISSUE-2026-04-24-002. The new
``get_macro_blanket_boosts`` helper fans VN-INDEX macro catalysts onto the
trading candidate universe, but ``_has_stacked_positive_catalysts`` must
keep reading from the original ``affected_tickers`` field only — reading
the fanned dict would inflate every ticker's stack count and silently
flip regime labels.
"""

from __future__ import annotations

import pytest

from shared.rules.catalyst_news import classify_macro_catalyst_scope
from shared.rules.catalyst_override import (
    CatalystInput,
    _has_stacked_positive_catalysts,
    get_macro_blanket_boosts,
)


def _macro_catalyst(
    key: str,
    event: str = "Fuel tax cut boosts Vietnamese market",
    impact: str = "POSITIVE",
    confidence: str = "HIGH",
    catalyst_type: str = "macro",
    affected: list[str] | None = None,
) -> CatalystInput:
    return CatalystInput(
        catalyst_key=key,
        event=event,
        impact=impact,
        confidence=confidence,
        affected_tickers=affected if affected is not None else ["VN-INDEX"],
        phases=None,
        supporting_article_count=3,
        catalyst_type=catalyst_type,
    )


class TestMacroBlanketScope:
    def test_vn_index_macro_is_blanket(self) -> None:
        catalyst = _macro_catalyst("fuel_tax_cut_2026")
        assert classify_macro_catalyst_scope(catalyst) == "macro_blanket"

    def test_per_ticker_catalyst_stays_per_ticker(self) -> None:
        catalyst = _macro_catalyst(
            "fpt_ai_contract",
            catalyst_type="corporate_action",
            affected=["FPT"],
        )
        assert classify_macro_catalyst_scope(catalyst) == "per_ticker"

    def test_vn_index_with_non_macro_type_is_per_ticker(self) -> None:
        # Regulatory catalysts aren't in MACRO_BLANKET_ELIGIBLE_TYPES.
        catalyst = _macro_catalyst("sbv_circular_new", catalyst_type="regulatory")
        assert classify_macro_catalyst_scope(catalyst) == "per_ticker"


class TestMacroBlanketFanOut:
    def test_positive_catalyst_fans_onto_universe(self) -> None:
        catalyst = _macro_catalyst("fuel_tax_cut_2026")
        universe = ["FPT", "TCB", "HPG"]
        fanned = get_macro_blanket_boosts([catalyst], universe)
        assert set(fanned.keys()) == {"FPT", "TCB", "HPG"}
        for boost in fanned.values():
            assert boost["phase_lifecycle"] == "MACRO_BLANKET"
            assert boost["rr_floor_adjustment"] == pytest.approx(0.25)

    def test_negative_catalyst_is_not_fanned(self) -> None:
        catalyst = _macro_catalyst("fuel_levy_hike", impact="NEGATIVE", event="Fuel levy hike")
        fanned = get_macro_blanket_boosts([catalyst], ["FPT", "TCB"])
        assert fanned == {}

    def test_low_confidence_is_not_fanned(self) -> None:
        catalyst = _macro_catalyst("vague_macro_rumor", confidence="LOW")
        fanned = get_macro_blanket_boosts([catalyst], ["FPT", "TCB"])
        assert fanned == {}

    def test_per_ticker_catalyst_never_fans_out(self) -> None:
        catalyst = _macro_catalyst(
            "fpt_earnings_beat",
            catalyst_type="earnings",
            affected=["FPT"],
        )
        fanned = get_macro_blanket_boosts([catalyst], ["FPT", "TCB", "HPG"])
        assert fanned == {}

    def test_medium_confidence_uses_half_magnitude(self) -> None:
        catalyst = _macro_catalyst("mid_sig_macro", confidence="MEDIUM")
        fanned = get_macro_blanket_boosts([catalyst], ["FPT"])
        assert fanned["FPT"]["rr_floor_adjustment"] == pytest.approx(0.125)


class TestStackedPositiveIsolation:
    """Pins the F1 invariant: _has_stacked_positive_catalysts must read
    from the original affected_tickers, never the fan-out dict."""

    def test_macro_blanket_does_not_inflate_stack_count(self) -> None:
        # Two separate HIGH/POSITIVE catalysts, but only one tags FPT
        # directly — the other is VN-INDEX. _has_stacked_positive_catalysts
        # must count 1, not 2.
        per_ticker = _macro_catalyst(
            "fpt_ai_contract",
            catalyst_type="corporate_action",
            affected=["FPT"],
        )
        macro_blanket = _macro_catalyst("fuel_tax_cut_2026")
        catalysts = [per_ticker, macro_blanket]

        # Fan the macro one out for verification that the fan-out dict
        # has FPT in it (proving the isolation is genuine).
        fanned = get_macro_blanket_boosts([macro_blanket], ["FPT"])
        assert "FPT" in fanned

        # But stack count reads original affected_tickers only.
        assert _has_stacked_positive_catalysts("FPT", catalysts) is False

    def test_two_explicit_per_ticker_hits_stacked(self) -> None:
        first = _macro_catalyst(
            "fpt_ai_contract",
            catalyst_type="corporate_action",
            affected=["FPT"],
        )
        second = _macro_catalyst(
            "fpt_data_center_japan",
            catalyst_type="corporate_action",
            affected=["FPT"],
        )
        assert _has_stacked_positive_catalysts("FPT", [first, second]) is True
