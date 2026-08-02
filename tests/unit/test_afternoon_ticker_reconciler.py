"""Unit tests for afternoon_ticker_reconciler.

Originating incident: MON-2026-04-23-002. The midday LLM returned three
afternoon_plan entries with ticker=None while the reason text still
identified each position by a stop-price fingerprint. The reconciler
promotes mappable entries and leaves unmappable ones null for
migration-316 replay compatibility.
"""

from __future__ import annotations

from agents.midday import AfternoonAction
from shared.rules.afternoon_ticker_reconciler import reconcile_afternoon_tickers


def _holding(ticker: str, stop: int | None = None, avg_cost: int | None = None) -> dict:
    row: dict = {"ticker": ticker, "plan_type": "SWING"}
    if stop is not None:
        row["stop_price_vnd"] = stop
    if avg_cost is not None:
        row["avg_cost"] = avg_cost
    return row


def test_promotes_ticker_via_evidence_price_vnd_stop() -> None:
    """SWI-137 / Fix 2 primary path: structured numeric anchor."""
    entries = [
        AfternoonAction(
            ticker=None,
            action="HOLD",
            confidence="MEDIUM",
            reason="Stop level intact after intraday dip",
            evidence_price_vnd=52000,
        )
    ]
    holdings = [_holding("AAA", stop=52000), _holding("CCC", stop=28000)]
    reconcile_afternoon_tickers(entries, holdings)
    assert entries[0].ticker == "AAA"


def test_promotes_ticker_via_evidence_price_vnd_avg_cost() -> None:
    """SWI-137 / Fix 2 primary path: matches against avg_cost."""
    entries = [
        AfternoonAction(
            ticker=None,
            action="HOLD",
            confidence="LOW",
            reason="Cost basis well below current level",
            evidence_price_vnd=65000,
        )
    ]
    holdings = [_holding("BBB", stop=60000, avg_cost=65000)]
    reconcile_afternoon_tickers(entries, holdings)
    assert entries[0].ticker == "BBB"


def test_evidence_price_within_tolerance_resolves() -> None:
    """SWI-137 / Fix 2: ±2% tolerance — evidence 82000 matches FPT avg_cost 81500."""
    entries = [
        AfternoonAction(
            ticker=None,
            action="HOLD",
            confidence="MEDIUM",
            reason="Average cost is the floor",
            evidence_price_vnd=82000,
        )
    ]
    holdings = [_holding("BBB", stop=68800, avg_cost=81500)]
    reconcile_afternoon_tickers(entries, holdings)
    assert entries[0].ticker == "BBB"


def test_validator_raises_when_price_cited_without_evidence_field() -> None:
    """SWI-137 / Fix 2: prose price token + null evidence + null ticker
    must raise so the LLM retry budget actively populates the structured field."""
    import pytest

    with pytest.raises(ValueError, match="evidence_price_vnd"):
        AfternoonAction(
            ticker=None,
            action="HOLD",
            confidence="MEDIUM",
            reason="Stop 52,000 VND still intact",
        )


def test_fingerprint_fallback_when_no_price_in_reason() -> None:
    """Pure prose without price tokens still hits fingerprint fallback through
    bare ticker token match."""
    entries = [
        AfternoonAction(
            ticker=None,
            action="TRIM",
            confidence="LOW",
            reason="AAA momentum fading",
        )
    ]
    holdings = [_holding("AAA", stop=52000)]
    reconcile_afternoon_tickers(entries, holdings)
    assert entries[0].ticker == "AAA"


def test_leaves_ticker_null_when_unmappable() -> None:
    entries = [
        AfternoonAction(
            ticker=None,
            action="NOTE",
            confidence="LOW",
            reason="Market flat; no position action required",
        )
    ]
    holdings = [_holding("AAA", stop=52000)]
    reconcile_afternoon_tickers(entries, holdings)
    # Preserves migration 316 null-ticker semantics — replay-safe.
    assert entries[0].ticker is None


def test_preserves_valid_ticker_already_in_holdings() -> None:
    entries = [
        AfternoonAction(
            ticker="AAA",
            action="HOLD",
            confidence="HIGH",
            reason="Stop intact",
        )
    ]
    holdings = [_holding("AAA", stop=52000)]
    reconcile_afternoon_tickers(entries, holdings)
    assert entries[0].ticker == "AAA"


def test_promotes_via_bare_ticker_token_in_reason() -> None:
    entries = [
        AfternoonAction(
            ticker=None,
            action="TRIM",
            confidence="LOW",
            reason="CCC uptrend intact but momentum fading",
        )
    ]
    holdings = [_holding("CCC", stop=28000), _holding("BBB", stop=60000)]
    reconcile_afternoon_tickers(entries, holdings)
    assert entries[0].ticker == "CCC"


def test_non_holding_ticker_in_reason_stays_null() -> None:
    """A 3-letter token that isn't a current holding must not leak through."""
    entries = [
        AfternoonAction(
            ticker=None,
            action="NOTE",
            confidence="LOW",
            reason="DDD sector rotation noted",
        )
    ]
    holdings = [_holding("AAA", stop=52000)]
    reconcile_afternoon_tickers(entries, holdings)
    assert entries[0].ticker is None
