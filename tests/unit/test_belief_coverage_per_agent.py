"""SWI-116 / SWI-126: per-agent ticker coverage + aggregator-zero surfacing."""

from __future__ import annotations

from shared.rules.belief_coverage import (
    EXPECTED_SECTOR_AGENT_KEYS,
    aggregator_persistence_zero,
    coverage_degraded_agents,
    per_agent_ticker_coverage,
)


def _belief(agent_key: str, ticker: str, sector_key: str | None = None) -> dict:
    return {"agent_key": agent_key, "ticker": ticker, "sector_key": sector_key}


def test_per_agent_ticker_coverage_returns_missing_tickers() -> None:
    expected_tickers = frozenset({"FPT", "VHM", "TCB", "ACV"})
    beliefs = [
        _belief("sector_technical", "FPT"),
        _belief("sector_technical", "VHM"),
        _belief("sector_news", "FPT"),
        _belief("sector_news", "VHM"),
        _belief("sector_news", "TCB"),
        _belief("sector_news", "ACV"),
        _belief("sector_enrichment", "FPT"),
        _belief("sector_enrichment", "VHM"),
        _belief("sector_enrichment", "TCB"),
        _belief("sector_enrichment", "ACV"),
    ]
    missing = per_agent_ticker_coverage(beliefs, EXPECTED_SECTOR_AGENT_KEYS, expected_tickers)
    assert missing == {"sector_technical": ["ACV", "TCB"]}


def test_coverage_degraded_agents_flags_below_floor() -> None:
    expected_tickers = frozenset({f"T{i:02d}" for i in range(49)})
    per_agent_missing = {
        "sector_technical": [f"T{i:02d}" for i in range(2)],  # 47/49 ≈ 0.959 — OK
        "sector_news": [f"T{i:02d}" for i in range(19)],  # 30/49 ≈ 0.612 — DEGRADED
    }
    degraded = coverage_degraded_agents(per_agent_missing, expected_tickers)
    assert degraded == ["sector_news"]


def test_coverage_degraded_agents_respects_custom_floor() -> None:
    expected = frozenset({"A", "B", "C", "D"})
    missing = {"sector_news": ["A"]}  # 75% coverage
    assert coverage_degraded_agents(missing, expected, ratio_floor=0.8) == ["sector_news"]
    assert coverage_degraded_agents(missing, expected, ratio_floor=0.7) == []


def test_aggregator_persistence_zero_flags_silent_failure() -> None:
    beliefs = [
        _belief("sector_technical", "FPT", "banking_1"),
        _belief("sector_news", "VHM", "banking_2"),
    ]
    sectors_attempted = frozenset({"banking_1", "banking_2"})
    zero = aggregator_persistence_zero(beliefs, "sector_aggregator", sectors_attempted)
    assert zero == ["banking_1", "banking_2"]


def test_aggregator_persistence_zero_silent_when_all_persisted() -> None:
    beliefs = [
        _belief("sector_aggregator", "FPT", "banking_1"),
        _belief("sector_aggregator", "VHM", "banking_2"),
    ]
    sectors_attempted = frozenset({"banking_1", "banking_2"})
    assert aggregator_persistence_zero(beliefs, "sector_aggregator", sectors_attempted) == []
