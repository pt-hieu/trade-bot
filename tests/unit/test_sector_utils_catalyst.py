"""log_catalyst_boosted_outside_watchlist scope-gate behaviour."""

from __future__ import annotations

import logging

from pipeline.sector_utils import log_catalyst_boosted_outside_watchlist
from shared.rules.catalyst_override import CatalystBoost


def _boost(ticker: str) -> CatalystBoost:
    return CatalystBoost(
        ticker=ticker,
        catalyst_key="ftse_2026",
        catalyst_event="FTSE upgrade",
        phase_lifecycle="APPROACHING_RESOLUTION",
        phase_name="immediate_shock",
        reason="upgrade approaching",
    )


def test_noop_when_boosted_tickers_already_in_sectors():
    sectors = {"Real Estate": ["VHM", "VIC", "VRE"], "Banking": ["VCB"]}
    boosted = {"VHM": _boost("VHM"), "VIC": _boost("VIC")}
    result = log_catalyst_boosted_outside_watchlist(sectors, boosted)
    assert result is sectors  # unchanged
    assert result["Real Estate"] == ["VHM", "VIC", "VRE"]


def test_logs_when_boosted_ticker_outside_watchlist(caplog):
    sectors = {"Real Estate": ["VHM", "VIC"]}
    boosted = {"SHB": _boost("SHB"), "VHM": _boost("VHM")}
    with caplog.at_level(logging.INFO, logger="pipeline.sector_utils"):
        result = log_catalyst_boosted_outside_watchlist(sectors, boosted)
    assert result is sectors
    assert any("SHB" in rec.message for rec in caplog.records)
    assert not any("VHM" in rec.message for rec in caplog.records)


def test_empty_boost_set_is_noop():
    sectors = {"Banking": ["VCB"]}
    assert log_catalyst_boosted_outside_watchlist(sectors, {}) is sectors
    assert log_catalyst_boosted_outside_watchlist(sectors, None) is sectors
