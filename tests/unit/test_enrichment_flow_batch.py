"""SWI-125 Surface 5b: typed EnrichmentTimeout + non-timeout swallow logging.

Previously `get_daily_flow_batch` swallowed every exception with
`return dict.fromkeys(normalized)`. Timeout-class failures were invisible
to observability and to the model-hop wall wrapper (SWI-115). Now timeouts
raise `EnrichmentTimeout` and non-timeout transient failures still take
the empty-dict fallback but log with `exc_info=True`.
"""

from __future__ import annotations

import pytest

from shared.api import enrichment
from shared.api.enrichment import EnrichmentTimeout, get_daily_flow_batch


@pytest.mark.asyncio
async def test_timeout_propagates_as_enrichment_timeout(monkeypatch) -> None:
    async def _raise_timeout(**_kwargs):
        raise TimeoutError("upstream wall exceeded")

    monkeypatch.setattr(enrichment, "_fetch_enrichment", _raise_timeout)
    with pytest.raises(EnrichmentTimeout) as excinfo:
        await get_daily_flow_batch(["FPT", "TCB"])
    assert "2 tickers" in str(excinfo.value)


@pytest.mark.asyncio
async def test_builtin_timeout_error_propagates_as_enrichment_timeout(monkeypatch) -> None:
    async def _raise(**_kwargs):
        raise TimeoutError("client timeout")

    monkeypatch.setattr(enrichment, "_fetch_enrichment", _raise)
    with pytest.raises(EnrichmentTimeout):
        await get_daily_flow_batch(["FPT"])


@pytest.mark.asyncio
async def test_generic_exception_logs_and_returns_fallback(monkeypatch, caplog) -> None:
    async def _raise(**_kwargs):
        raise RuntimeError("503 from upstream")

    monkeypatch.setattr(enrichment, "_fetch_enrichment", _raise)
    caplog.set_level("WARNING", logger="shared.api.enrichment")
    result = await get_daily_flow_batch(["FPT", "TCB"])
    assert result == {"FPT": None, "TCB": None}
    assert any("503 from upstream" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_happy_path_returns_parsed_flow(monkeypatch) -> None:
    async def _ok(**_kwargs):
        return {
            "FPT": {
                "flow": [{"fr_net_value": 1_000_000}],
                "prop": [{"prop_buy_value": 500_000, "prop_sell_value": 200_000}],
                "orders": [{"buy_orders": 10, "sell_orders": 5}],
            }
        }

    monkeypatch.setattr(enrichment, "_fetch_enrichment", _ok)
    result = await get_daily_flow_batch(["FPT"])
    assert result["FPT"] is not None
    assert result["FPT"]["foreign_net"] == 1_000_000


@pytest.mark.asyncio
async def test_premarket_placeholder_row_does_not_zero_foreign_net(monkeypatch) -> None:
    """SWI-299: a current-day pre-market placeholder row (all foreign values 0)
    is sorted ahead of the latest real trading day. Reading the latest row by
    date pegged foreign_net to 0 on 100% of morning-scan candidates. The latest
    row with ACTUAL foreign activity must win instead."""

    async def _ok(**_kwargs):
        return {
            "VHM": {
                "flow": [
                    # Latest by date — pre-market placeholder, no trading yet.
                    {
                        "time": "2026-05-08T00:00:00",
                        "fr_net_value": 0,
                        "fr_buy_value": 0,
                        "fr_sell_value": 0,
                    },
                    # Previous trading day — real net foreign selling.
                    {
                        "time": "2026-05-07T00:00:00",
                        "fr_net_value": -648_810_000,
                        "fr_buy_value": 0,
                        "fr_sell_value": 648_810_000,
                    },
                ]
            }
        }

    monkeypatch.setattr(enrichment, "_fetch_enrichment", _ok)
    result = await get_daily_flow_batch(["VHM"])
    assert result["VHM"]["foreign_net"] == -648_810_000


@pytest.mark.asyncio
async def test_balanced_real_day_keeps_zero_net(monkeypatch) -> None:
    """A genuine balanced trading day (buy & sell both non-zero, net 0) is
    real activity and must be retained, not filtered as a placeholder."""

    async def _ok(**_kwargs):
        return {
            "VCB": {
                "flow": [
                    {
                        "time": "2026-05-08T00:00:00",
                        "fr_net_value": 0,
                        "fr_buy_value": 500_000,
                        "fr_sell_value": 500_000,
                    },
                ]
            }
        }

    monkeypatch.setattr(enrichment, "_fetch_enrichment", _ok)
    result = await get_daily_flow_batch(["VCB"])
    assert result["VCB"]["foreign_net"] == 0
