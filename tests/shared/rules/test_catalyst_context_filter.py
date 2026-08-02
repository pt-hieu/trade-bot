"""SWI-20 — catalyst-context filter tests.

Verifies the LLM-injection gate is permissive on universe overlap, HIGH/
MEDIUM confidence, market-wide, and imminent — but caps at 7 entries by
default and orders by impact/confidence/days_until.
"""

from __future__ import annotations

from shared.rules.catalyst_context_filter import filter_catalyst_context


def _row(**kwargs) -> dict:
    base = {
        "catalyst_key": "k",
        "event": "evt",
        "impact": "WATCH",
        "confidence": "LOW",
        "status": "active",
        "expected": None,
        "affected_tickers": [],
    }
    base.update(kwargs)
    return base


def test_universe_overlap_passes_even_when_low_confidence() -> None:
    rows = [_row(catalyst_key="a", confidence="LOW", affected_tickers=["FPT"])]
    out = filter_catalyst_context(rows, {"FPT"})
    assert [r["catalyst_key"] for r in out] == ["a"]


def test_high_confidence_passes_without_overlap() -> None:
    rows = [_row(catalyst_key="b", confidence="HIGH", affected_tickers=["VHM"])]
    out = filter_catalyst_context(rows, {"FPT"})
    assert out and out[0]["catalyst_key"] == "b"


def test_medium_confidence_passes_without_overlap() -> None:
    rows = [_row(catalyst_key="c", confidence="MEDIUM", affected_tickers=["VHM"])]
    out = filter_catalyst_context(rows, {"FPT"})
    assert out and out[0]["catalyst_key"] == "c"


def test_imminent_passes_when_low_confidence_and_no_overlap() -> None:
    rows = [
        _row(
            catalyst_key="d",
            confidence="LOW",
            status="imminent",
            affected_tickers=["VHM"],
        )
    ]
    out = filter_catalyst_context(rows, {"FPT"})
    assert out and out[0]["catalyst_key"] == "d"


def test_low_non_overlap_dropped() -> None:
    rows = [
        _row(catalyst_key="dropme", confidence="LOW", affected_tickers=["VHM"]),
    ]
    out = filter_catalyst_context(rows, {"FPT"})
    assert out == []


def test_market_wide_vn_index_passes_without_overlap() -> None:
    rows = [_row(catalyst_key="m", confidence="LOW", affected_tickers=["VN-INDEX"])]
    out = filter_catalyst_context(rows, {"FPT"})
    assert out and out[0]["catalyst_key"] == "m"


def test_empty_universe_still_surfaces_high_confidence() -> None:
    rows = [_row(catalyst_key="h", confidence="HIGH", affected_tickers=["VHM"])]
    out = filter_catalyst_context(rows, set())
    assert out and out[0]["catalyst_key"] == "h"


def test_cap_enforced_default_seven() -> None:
    rows = [
        _row(catalyst_key=f"k{i}", confidence="HIGH", affected_tickers=["VHM"]) for i in range(20)
    ]
    out = filter_catalyst_context(rows, set())
    assert len(out) == 7


def test_sort_orders_high_impact_first() -> None:
    rows = [
        _row(catalyst_key="lo", impact="LOW", confidence="HIGH"),
        _row(catalyst_key="hi", impact="HIGH", confidence="HIGH"),
    ]
    out = filter_catalyst_context(rows, set())
    assert [r["catalyst_key"] for r in out] == ["hi", "lo"]
