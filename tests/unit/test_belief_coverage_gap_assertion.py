"""Test for the shared belief coverage assertion.

Required (sub-agent) keys: 1 missing → ERROR log, 2+ missing → ``RuntimeError``.
Optional (aggregator) keys: missing → ERROR log + counter bump, never raise.
"""

from __future__ import annotations

import logging

import pytest

from shared import observability
from shared.rules.belief_coverage import (
    EXPECTED_POSITION_AGENT_KEYS,
    EXPECTED_SECTOR_AGENT_KEYS,
    OPTIONAL_POSITION_AGENT_KEYS,
    OPTIONAL_SECTOR_AGENT_KEYS,
    assert_belief_coverage,
)

_logger = logging.getLogger("shared.rules.belief_coverage.test")


def _belief(agent_key: str, ticker: str = "FPT") -> dict:
    return {
        "agent_key": agent_key,
        "ticker": ticker,
        "direction": "BULLISH",
        "bull_probability": 0.5,
        "base_probability": 0.3,
        "bear_probability": 0.2,
        "conviction": 0.55,
    }


@pytest.fixture(autouse=True)
def _reset_counters():
    observability.reset_health_counters()
    yield
    observability.reset_health_counters()


def test_no_raise_when_all_expected_keys_present():
    beliefs = [_belief(k) for k in EXPECTED_SECTOR_AGENT_KEYS]
    assert_belief_coverage(
        beliefs,
        EXPECTED_SECTOR_AGENT_KEYS,
        ensemble_label="sector",
        logger=_logger,
    )  # no raise


def test_total_collapse_raises():
    # SWI-191: zero beliefs while there WERE tickers to analyze is total
    # coverage collapse — the most expensive failure (a brief with no ensemble
    # signal). It short-circuited at the early `if not beliefs: return` guard
    # before any coverage check ran; now it raises. Keyed on expected_tickers
    # (the "work was expected" signal), not the always-non-empty key constant.
    with pytest.raises(RuntimeError, match="SECTOR_TOTAL_COVERAGE_COLLAPSE"):
        assert_belief_coverage(
            [],
            EXPECTED_SECTOR_AGENT_KEYS,
            ensemble_label="sector",
            logger=_logger,
            expected_tickers=frozenset({"FPT", "VHM"}),
        )


def test_no_expectations_is_noop():
    # Boundary: nothing expected → total-collapse raise must not fire even
    # with an empty beliefs list (an ensemble that ran on an empty universe).
    assert_belief_coverage(
        [],
        frozenset(),
        ensemble_label="sector",
        logger=_logger,
        expected_tickers=None,
    )  # no raise


def test_no_holdings_zero_beliefs_is_noop():
    # SWI-191 regression guard: a no-holdings day legitimately yields zero
    # position beliefs. EXPECTED_POSITION_AGENT_KEYS is always non-empty, but
    # expected_tickers is empty (no holdings) — the total-collapse raise must
    # NOT fire, or a healthy pipeline aborts.
    assert_belief_coverage(
        [],
        EXPECTED_POSITION_AGENT_KEYS,
        ensemble_label="positions",
        logger=_logger,
        expected_tickers=frozenset(),
    )  # no raise


def test_partial_aggregator_gap_does_not_raise(caplog):
    # Exactly one required key missing (< 2 threshold) → ERROR log only,
    # degrade-and-ship. Pins the partial-gap-ships-with-banner invariant.
    beliefs = [_belief("sector_technical")]
    with caplog.at_level(logging.ERROR, logger=_logger.name):
        assert_belief_coverage(
            beliefs,
            EXPECTED_SECTOR_AGENT_KEYS - frozenset({"sector_enrichment"}),
            ensemble_label="sector",
            logger=_logger,
        )  # no raise — one of {sector_technical, sector_news} missing
    assert any("SECTOR_BELIEF_COVERAGE_GAP" in r.getMessage() for r in caplog.records)


def test_single_missing_key_only_warns(caplog):
    beliefs = [
        _belief("sector_technical"),
        _belief("sector_news"),
        # sector_enrichment missing
    ]
    with caplog.at_level(logging.ERROR, logger=_logger.name):
        assert_belief_coverage(
            beliefs,
            EXPECTED_SECTOR_AGENT_KEYS,
            ensemble_label="sector",
            logger=_logger,
        )
    assert any("SECTOR_BELIEF_COVERAGE_GAP" in r.message for r in caplog.records)


def test_aggregator_only_absent_logs_error_no_raise(caplog):
    # Aggregators are now in OPTIONAL set — absence emits ERROR + counter
    # bump (so operators can grep + alert) but does NOT raise.
    beliefs = [
        _belief("sector_technical"),
        _belief("sector_news"),
        _belief("sector_enrichment"),
        # sector_aggregator missing
    ]
    with caplog.at_level(logging.ERROR, logger=_logger.name):
        assert_belief_coverage(
            beliefs,
            EXPECTED_SECTOR_AGENT_KEYS,
            ensemble_label="sector",
            logger=_logger,
            optional_keys=OPTIONAL_SECTOR_AGENT_KEYS,
        )  # no raise
    assert any("SECTOR_AGGREGATOR_BELIEF_GAP" in r.getMessage() for r in caplog.records)
    counters = observability.get_health_counters()
    assert counters["aggregator_belief_gap_count"] == 1
    assert "sector/sector_aggregator" in counters["aggregator_belief_gap_keys"]


def test_aggregator_plus_subagent_missing_still_raises():
    # 2+ EXPECTED missing must still raise even when an OPTIONAL is also
    # missing (the 04-17 co-occurring positions_aggregator + positions_value
    # case must not be masked).
    beliefs = [
        _belief("positions_technical"),
        # positions_value + positions_thesis (EXPECTED) missing
        # positions_aggregator (OPTIONAL) missing
    ]
    with pytest.raises(RuntimeError, match="POSITIONS_BELIEF_COVERAGE_GAP"):
        assert_belief_coverage(
            beliefs,
            EXPECTED_POSITION_AGENT_KEYS,
            ensemble_label="positions",
            logger=_logger,
            optional_keys=OPTIONAL_POSITION_AGENT_KEYS,
        )


def test_two_missing_keys_raises():
    beliefs = [
        _belief("sector_technical"),
        # sector_news + sector_enrichment missing
    ]
    with pytest.raises(RuntimeError, match="SECTOR_BELIEF_COVERAGE_GAP"):
        assert_belief_coverage(
            beliefs,
            EXPECTED_SECTOR_AGENT_KEYS,
            ensemble_label="sector",
            logger=_logger,
        )


def test_per_ticker_two_missing_raises():
    """SWI-141 / Fix 7a sufficient root: agent_key set is complete but 2+
    expected tickers have ZERO sub-agent beliefs. Replays the 2026-04-29
    incident shape — 11/35 tickers had no sector beliefs while all three
    sub-agent keys were observed in the population."""
    beliefs = [
        _belief("sector_technical", ticker="FPT"),
        _belief("sector_news", ticker="FPT"),
        _belief("sector_enrichment", ticker="FPT"),
        _belief("sector_technical", ticker="VHM"),
        _belief("sector_news", ticker="VHM"),
        _belief("sector_enrichment", ticker="VHM"),
    ]
    expected_tickers = frozenset({"FPT", "VHM", "ACB", "BID", "CTG"})
    with pytest.raises(RuntimeError, match="SECTOR_TICKER_COVERAGE_GAP"):
        assert_belief_coverage(
            beliefs,
            EXPECTED_SECTOR_AGENT_KEYS,
            ensemble_label="sector",
            logger=_logger,
            expected_tickers=expected_tickers,
        )


def test_per_ticker_one_missing_only_warns(caplog):
    beliefs = [
        _belief("sector_technical", ticker="FPT"),
        _belief("sector_news", ticker="FPT"),
        _belief("sector_enrichment", ticker="FPT"),
    ]
    expected_tickers = frozenset({"FPT", "VHM"})
    with caplog.at_level(logging.ERROR, logger=_logger.name):
        assert_belief_coverage(
            beliefs,
            EXPECTED_SECTOR_AGENT_KEYS,
            ensemble_label="sector",
            logger=_logger,
            expected_tickers=expected_tickers,
        )
    assert any("SECTOR_TICKER_COVERAGE_GAP" in r.getMessage() for r in caplog.records)


def test_per_ticker_full_coverage_silent():
    beliefs = [
        _belief("sector_technical", ticker="FPT"),
        _belief("sector_news", ticker="FPT"),
        _belief("sector_enrichment", ticker="FPT"),
    ]
    assert_belief_coverage(
        beliefs,
        EXPECTED_SECTOR_AGENT_KEYS,
        ensemble_label="sector",
        logger=_logger,
        expected_tickers=frozenset({"FPT"}),
    )  # no raise


def test_positions_ensemble_threshold_independent():
    beliefs = [_belief("positions_technical")]
    # 2 missing (positions_value + positions_thesis) → raises.
    with pytest.raises(RuntimeError, match="POSITIONS_BELIEF_COVERAGE_GAP"):
        assert_belief_coverage(
            beliefs,
            EXPECTED_POSITION_AGENT_KEYS,
            ensemble_label="positions",
            logger=_logger,
        )


def test_sector_coverage_universe_drops_holdings_pseudo_sector():
    """Regression: held tickers in the 'holdings' pseudo-sector must be
    excluded from the coverage-gate universe, since sector sub-agents never
    fan out to that bucket."""
    from shared.rules.belief_coverage import sector_coverage_universe

    sectors_for_phase2 = {
        "banks": ["VCB", "TCB"],
        "tech": ["FPT"],
        "holdings": ["ACV", "XYZ"],
    }
    universe = sector_coverage_universe(sectors_for_phase2)
    assert universe == frozenset({"VCB", "TCB", "FPT"})
    assert "ACV" not in universe
    assert "XYZ" not in universe


def test_sector_gate_no_longer_raises_for_unwatched_holds():
    """End-to-end shape from incident 25304801382: 35 watchlist tickers all
    have full beliefs; 3 held-but-unwatched tickers have no beliefs. After
    the fix, the per-ticker gate must NOT raise."""
    from shared.rules.belief_coverage import sector_coverage_universe

    watchlist_tickers = [f"T{i:02d}" for i in range(35)]
    sectors_for_phase2 = {
        "sector_a": watchlist_tickers[:18],
        "sector_b": watchlist_tickers[18:],
        "holdings": ["ACV", "FPT", "TCB"],
    }
    expected_tickers = sector_coverage_universe(sectors_for_phase2)
    assert expected_tickers == frozenset(watchlist_tickers)

    beliefs: list[dict] = []
    for t in watchlist_tickers:
        for k in EXPECTED_SECTOR_AGENT_KEYS:
            beliefs.append(_belief(k, ticker=t))

    assert_belief_coverage(
        beliefs,
        EXPECTED_SECTOR_AGENT_KEYS,
        ensemble_label="sector",
        logger=_logger,
        expected_tickers=expected_tickers,
    )  # must not raise
