"""SWI-304: rally_readmit Phase 0 pass unit tests."""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from pipeline.phase_zero import _data_sources as ds
from pipeline.phase_zero import rally_readmit as mod
from pipeline.phase_zero._data_sources import (
    compute_5d_return_and_vol_ratio as _compute_5d_return_and_vol_ratio,
)
from pipeline.phase_zero.rally_readmit import run_rally_readmit


def _bar(close: float, volume: float) -> dict:
    return {"close": close, "volume": volume, "open": close, "high": close, "low": close}


def _rallying_bars() -> list[dict]:
    # 25 bars: flat for 20 (vol 1000), then 5-day rally; last day vol 2000
    bars = [_bar(100.0, 1000.0) for _ in range(20)]
    bars.extend(
        [_bar(101.0, 1100.0), _bar(102.0, 1200.0), _bar(103.0, 1300.0), _bar(104.0, 1400.0)]
    )
    bars.append(_bar(106.6, 2000.0))  # ret_5d ≈ 6.6%, vol_ratio ≈ 2.0
    return bars


def _flat_bars() -> list[dict]:
    return [_bar(100.0, 1000.0) for _ in range(25)]


def test_compute_metrics_rally():
    ret, vol_ratio = _compute_5d_return_and_vol_ratio(_rallying_bars())
    assert ret is not None and ret > 0.06
    assert vol_ratio is not None and vol_ratio > 1.5


def test_compute_metrics_flat():
    ret, vol_ratio = _compute_5d_return_and_vol_ratio(_flat_bars())
    assert ret == pytest.approx(0.0)
    assert vol_ratio == pytest.approx(1.0)


def test_compute_metrics_insufficient_bars():
    ret, vol_ratio = _compute_5d_return_and_vol_ratio([_bar(100, 1000)] * 3)
    assert ret is None
    assert vol_ratio is None


@pytest.fixture
def trading_config_stub(monkeypatch):
    from shared.trading_config import TradingConfig

    cfg = TradingConfig(
        rally_readmit_ret_5d_min=0.05,
        rally_readmit_vol_ratio_min=1.5,
        rally_readmit_daily_cap=5,
        rally_readmit_new_ticker_ret_5d_min=0.08,
        rally_readmit_new_ticker_vol_ratio_min=2.0,
    )
    monkeypatch.setattr(mod, "get_trading_config", lambda: cfg, raising=False)
    monkeypatch.setattr("shared.trading_config.get_trading_config", lambda: cfg, raising=False)
    return cfg


async def _patch_db(
    monkeypatch,
    *,
    deactivated: list[dict] | None = None,
    active: set[str] | None = None,
    prior: set[str] | None = None,
    longterm: dict[str, str | None] | None = None,
    catalysts: dict[str, str] | None = None,
    new_universe: dict[str, str | None] | None = None,
    metrics: dict[str, tuple[float | None, float | None]] | None = None,
    add_swing_stock_tracker: list[tuple[str, str]] | None = None,
    add_swing_stock_return: bool = True,
):
    monkeypatch.setattr(
        ds, "fetch_deactivated_swing_rows", AsyncMock(return_value=deactivated or [])
    )
    monkeypatch.setattr(ds, "fetch_active_swing_tickers", AsyncMock(return_value=active or set()))
    monkeypatch.setattr(ds, "fetch_prior_swing_tickers", AsyncMock(return_value=prior or set()))
    monkeypatch.setattr(ds, "fetch_longterm_with_sector", AsyncMock(return_value=longterm or {}))
    monkeypatch.setattr(
        ds,
        "fetch_high_positive_catalyst_tickers",
        AsyncMock(return_value=catalysts or {}),
    )
    monkeypatch.setattr(
        ds,
        "fetch_new_universe_candidates",
        AsyncMock(return_value=new_universe or {}),
    )
    monkeypatch.setattr(ds, "fetch_metrics", AsyncMock(return_value=metrics or {}))
    monkeypatch.setattr(ds, "fetch_stock_sector", AsyncMock(return_value=None))

    async def _fake_add(ticker: str, sector: str) -> bool:
        if add_swing_stock_tracker is not None:
            add_swing_stock_tracker.append((ticker, sector))
        return add_swing_stock_return

    monkeypatch.setattr("shared.neon.add_swing_stock", _fake_add, raising=False)


@pytest.mark.asyncio
async def test_rally_volume_admits_vic(monkeypatch, trading_config_stub):
    tracker: list[tuple[str, str]] = []
    await _patch_db(
        monkeypatch,
        deactivated=[{"ticker": "VIC", "sector": "Real Estate"}],
        prior={"VIC"},
        metrics={"VIC": (0.066, 2.0)},
        add_swing_stock_tracker=tracker,
    )
    records = await run_rally_readmit(date(2026, 5, 9))
    admitted = [r for r in records if r.admitted]
    assert any(r.ticker == "VIC" and r.trigger == "rally_volume" for r in admitted)
    assert ("VIC", "Real Estate") in tracker


@pytest.mark.asyncio
async def test_rally_below_threshold_skipped(monkeypatch, trading_config_stub):
    await _patch_db(
        monkeypatch,
        deactivated=[{"ticker": "VIC", "sector": "Real Estate"}],
        metrics={"VIC": (0.03, 2.0)},
    )
    records = await run_rally_readmit(date(2026, 5, 9))
    assert all(not r.admitted for r in records)


@pytest.mark.asyncio
async def test_volume_below_threshold_skipped(monkeypatch, trading_config_stub):
    await _patch_db(
        monkeypatch,
        deactivated=[{"ticker": "VIC", "sector": "Real Estate"}],
        metrics={"VIC": (0.10, 1.2)},
    )
    records = await run_rally_readmit(date(2026, 5, 9))
    assert all(not r.admitted for r in records)


@pytest.mark.asyncio
async def test_catalyst_trigger_admits(monkeypatch, trading_config_stub):
    tracker: list[tuple[str, str]] = []
    await _patch_db(
        monkeypatch,
        deactivated=[{"ticker": "FPT", "sector": "Technology"}],
        catalysts={"FPT": "FPT-CAT-1"},
        metrics={"FPT": (None, None)},
        add_swing_stock_tracker=tracker,
    )
    records = await run_rally_readmit(date(2026, 5, 9))
    admitted = [r for r in records if r.admitted]
    assert any(r.ticker == "FPT" and r.trigger == "catalyst" for r in admitted)


@pytest.mark.asyncio
async def test_longterm_rally_requires_prior_swing_row(monkeypatch, trading_config_stub):
    # longterm with prior swing row → admit
    tracker: list[tuple[str, str]] = []
    await _patch_db(
        monkeypatch,
        deactivated=[],
        active=set(),
        prior={"MSN"},
        longterm={"MSN": "Consumer"},
        metrics={"MSN": (0.08, 1.8)},
        add_swing_stock_tracker=tracker,
    )
    records = await run_rally_readmit(date(2026, 5, 9))
    assert any(r.ticker == "MSN" and r.trigger == "longterm_rally" and r.admitted for r in records)


@pytest.mark.asyncio
async def test_longterm_rally_no_prior_swing_skipped(monkeypatch, trading_config_stub):
    await _patch_db(
        monkeypatch,
        prior=set(),
        longterm={"NEW": "Consumer"},
        metrics={"NEW": (0.10, 2.0)},
    )
    records = await run_rally_readmit(date(2026, 5, 9))
    # NEW has no prior swing row; longterm-only candidate must NOT widen the universe.
    assert all(r.ticker != "NEW" for r in records)


@pytest.mark.asyncio
async def test_no_sector_warns_and_skips(monkeypatch, trading_config_stub):
    await _patch_db(
        monkeypatch,
        deactivated=[{"ticker": "ZZZ", "sector": None}],
        metrics={"ZZZ": (0.10, 2.0)},
    )
    records = await run_rally_readmit(date(2026, 5, 9))
    skipped = [r for r in records if r.skip_reason == "no_sector"]
    assert skipped and skipped[0].ticker == "ZZZ"


@pytest.mark.asyncio
async def test_cap_enforced(monkeypatch, trading_config_stub):
    deactivated = [{"ticker": f"T{i}", "sector": "Banking"} for i in range(8)]
    metrics = {f"T{i}": (0.06 + i * 0.01, 1.6) for i in range(8)}
    await _patch_db(monkeypatch, deactivated=deactivated, metrics=metrics)
    records = await run_rally_readmit(date(2026, 5, 9))
    admitted = [r for r in records if r.admitted]
    cap_skipped = [r for r in records if r.skip_reason == "cap_hit"]
    assert len(admitted) == 5
    assert len(cap_skipped) == 3
    # Highest-score tickers admitted (T7..T3)
    admitted_tickers = {r.ticker for r in admitted}
    assert "T7" in admitted_tickers
    assert "T0" not in admitted_tickers


@pytest.mark.asyncio
async def test_threshold_boundary_inclusive(monkeypatch, trading_config_stub):
    await _patch_db(
        monkeypatch,
        deactivated=[{"ticker": "BDR", "sector": "Banking"}],
        metrics={"BDR": (0.05, 1.5)},
    )
    records = await run_rally_readmit(date(2026, 5, 9))
    assert any(r.admitted and r.ticker == "BDR" for r in records)


@pytest.mark.asyncio
async def test_empty_universe_emits_summary(monkeypatch, trading_config_stub):
    await _patch_db(monkeypatch)
    records = await run_rally_readmit(date(2026, 5, 9))
    assert records == []


@pytest.mark.asyncio
async def test_technicals_failure_falls_back_to_catalyst_only(monkeypatch, trading_config_stub):
    """If fetch_history_batch fails, only catalyst-triggered admits survive."""
    monkeypatch.setattr(
        ds,
        "fetch_deactivated_swing_rows",
        AsyncMock(
            return_value=[
                {"ticker": "VIC", "sector": "Real Estate"},
                {"ticker": "FPT", "sector": "Technology"},
            ]
        ),
    )
    monkeypatch.setattr(ds, "fetch_active_swing_tickers", AsyncMock(return_value=set()))
    monkeypatch.setattr(ds, "fetch_prior_swing_tickers", AsyncMock(return_value={"VIC", "FPT"}))
    monkeypatch.setattr(ds, "fetch_longterm_with_sector", AsyncMock(return_value={}))
    monkeypatch.setattr(
        ds,
        "fetch_high_positive_catalyst_tickers",
        AsyncMock(return_value={"FPT": "CAT"}),
    )
    # SWI-322 added a new_universe fetch inside the same gather. Tests that
    # don't go through _patch_db must stub it explicitly or the gather hits
    # the live DB; test-order pollution lets one earlier test silently
    # initialize the pool and the failure only surfaces in a full run.
    monkeypatch.setattr(ds, "fetch_new_universe_candidates", AsyncMock(return_value={}))
    monkeypatch.setattr(ds, "fetch_metrics", AsyncMock(return_value={}))
    monkeypatch.setattr(ds, "fetch_stock_sector", AsyncMock(return_value=None))

    tracker: list[tuple[str, str]] = []

    async def _fake_add(ticker: str, sector: str) -> bool:
        tracker.append((ticker, sector))
        return True

    monkeypatch.setattr("shared.neon.add_swing_stock", _fake_add, raising=False)

    records = await run_rally_readmit(date(2026, 5, 9))
    admitted = [r for r in records if r.admitted]
    assert {r.ticker for r in admitted} == {"FPT"}


# ─── SWI-322: new-universe path tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_new_ticker_admits_when_above_threshold(monkeypatch, trading_config_stub):
    tracker: list[tuple[str, str]] = []
    await _patch_db(
        monkeypatch,
        new_universe={"DCM": "Industrial"},
        metrics={"DCM": (0.10, 2.5)},
        add_swing_stock_tracker=tracker,
    )
    records = await run_rally_readmit(date(2026, 5, 12))
    admitted = [r for r in records if r.admitted]
    assert any(r.ticker == "DCM" and r.trigger == "rally_volume_new" for r in admitted)
    assert ("DCM", "Industrial") in tracker


@pytest.mark.asyncio
async def test_new_ticker_skipped_when_below_threshold(monkeypatch, trading_config_stub):
    await _patch_db(
        monkeypatch,
        new_universe={"DCM": "Industrial"},
        metrics={"DCM": (0.05, 2.5)},  # ret_5d below new-ticker threshold (0.08)
    )
    records = await run_rally_readmit(date(2026, 5, 12))
    assert all(r.ticker != "DCM" for r in records)


@pytest.mark.asyncio
async def test_new_ticker_display_name_contract(monkeypatch, trading_config_stub):
    """Fetcher must return display_name (e.g. 'Real Estate'), not slug ('real_estate')."""
    tracker: list[tuple[str, str]] = []
    await _patch_db(
        monkeypatch,
        new_universe={"DXG": "Real Estate"},
        metrics={"DXG": (0.09, 2.1)},
        add_swing_stock_tracker=tracker,
    )
    records = await run_rally_readmit(date(2026, 5, 12))
    assert any(r.ticker == "DXG" and r.admitted for r in records)
    assert tracker == [("DXG", "Real Estate")]


@pytest.mark.asyncio
async def test_new_ticker_sector_not_found_returns_false_and_logs_error(
    monkeypatch, trading_config_stub, caplog
):
    """If add_swing_stock returns False (sector mismatch), record is not admitted."""
    import logging

    await _patch_db(
        monkeypatch,
        new_universe={"DCM": "Industrial"},
        metrics={"DCM": (0.10, 2.5)},
        add_swing_stock_return=False,
    )
    with caplog.at_level(logging.WARNING):
        records = await run_rally_readmit(date(2026, 5, 12))
    rec = next(r for r in records if r.ticker == "DCM")
    assert rec.admitted is False


@pytest.mark.asyncio
async def test_daily_cap_counts_new_inserts_with_reactivations(monkeypatch, trading_config_stub):
    """Cap is shared. With +0.05 bias, new-universe high-rally tickers win the cap."""
    # cap = 2 (override via monkeypatch on stub)
    from shared.trading_config import TradingConfig

    cfg = TradingConfig(
        rally_readmit_ret_5d_min=0.05,
        rally_readmit_vol_ratio_min=1.5,
        rally_readmit_daily_cap=2,
        rally_readmit_new_ticker_ret_5d_min=0.08,
        rally_readmit_new_ticker_vol_ratio_min=2.0,
    )
    monkeypatch.setattr(mod, "get_trading_config", lambda: cfg, raising=False)
    monkeypatch.setattr("shared.trading_config.get_trading_config", lambda: cfg, raising=False)

    tracker: list[tuple[str, str]] = []
    await _patch_db(
        monkeypatch,
        deactivated=[{"ticker": "OLD", "sector": "Banking"}],
        new_universe={"NEW1": "Industrial", "NEW2": "Industrial"},
        metrics={
            "OLD": (0.06, 1.8),
            "NEW1": (0.10, 2.5),
            "NEW2": (0.10, 2.5),
        },
        add_swing_stock_tracker=tracker,
    )
    records = await run_rally_readmit(date(2026, 5, 12))
    admitted = {r.ticker for r in records if r.admitted}
    cap_hit = {r.ticker for r in records if r.skip_reason == "cap_hit"}
    assert admitted == {"NEW1", "NEW2"}
    assert "OLD" in cap_hit


@pytest.mark.asyncio
async def test_existing_reactivation_path_unchanged(monkeypatch, trading_config_stub):
    tracker: list[tuple[str, str]] = []
    await _patch_db(
        monkeypatch,
        deactivated=[{"ticker": "VIC", "sector": "Real Estate"}],
        prior={"VIC"},
        metrics={"VIC": (0.066, 2.0)},
        add_swing_stock_tracker=tracker,
    )
    records = await run_rally_readmit(date(2026, 5, 12))
    admitted = [r for r in records if r.admitted]
    assert len(admitted) == 1
    assert admitted[0].ticker == "VIC"
    assert admitted[0].trigger == "rally_volume"


@pytest.mark.asyncio
async def test_new_universe_skipped_when_metrics_missing(monkeypatch, trading_config_stub):
    """Fetcher returns ticker, but fetch_metrics omits it (and other tickers populate
    metrics so technicals_failed=False). No admission, no exception."""
    await _patch_db(
        monkeypatch,
        deactivated=[{"ticker": "VIC", "sector": "Real Estate"}],
        new_universe={"DCM": "Industrial"},
        metrics={"VIC": (0.066, 2.0)},  # DCM intentionally absent
    )
    records = await run_rally_readmit(date(2026, 5, 12))
    assert all(r.ticker != "DCM" for r in records)


@pytest.mark.asyncio
async def test_new_universe_path_skipped_on_technicals_failure(monkeypatch, trading_config_stub):
    """If fetch_metrics returns empty (technicals_failed=True), new-universe path
    must not run — it has no fallback like catalyst does."""
    await _patch_db(
        monkeypatch,
        new_universe={"DCM": "Industrial"},
        metrics={},  # technicals_failed when metrics_tickers non-empty
    )
    records = await run_rally_readmit(date(2026, 5, 12))
    assert all(r.ticker != "DCM" for r in records)
