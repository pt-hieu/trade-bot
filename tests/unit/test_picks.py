"""Tests for pick action determination (BUY vs LIMIT_BUY)."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

import agents.picks  # noqa: F401 — registers `picks` submodule so `patch("agents.picks.…")` resolves


def _base_setup(
    entry=30000,
    stop=29400,
    target=42000,
    close=31000,
    risk_reward=4.0,
    valid=True,
    target_basis="conservative",
    rr_stretch=None,
    swing_high=45000,
    market_setup=None,
):
    """Build a mock compute_trade_setup_async return value."""
    result = {
        "ticker": "TPB",
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk_reward": risk_reward,
        "risk_reward_gross": risk_reward + 0.2,  # gross slightly higher than net
        "risk_per_share": entry - stop,
        "shares": 100,
        "position_vnd": entry * 100,
        "valid": valid,
        "close": close,
        "levels_used": {
            "nearest_support": entry,
            "swing_low": stop + 400,
            "nearest_resistance": target,
            "swing_high": swing_high,
            "range_20d_low": entry,
            "range_20d_high": swing_high,
        },
        "target_basis": target_basis,
        "rr_stretch": rr_stretch,
    }
    if market_setup:
        result["market_setup"] = market_setup
    return result


def _base_tech_data():
    """Minimal tech data for strategy classification."""
    return {
        "ticker": "TPB",
        "close": 31000,
        "rsi": 45.0,
        "levels": {},
        "trend": {"trend": "SIDEWAYS", "strength": "weak", "momentum": "neutral"},
    }


def _buy_signal(ticker="TPB"):
    return {"ticker": ticker, "signal": "BUY", "note": "Strong setup", "sector": "banking"}


class _BatchFixture:
    """Adapter exposing a `setup` mock whose return value becomes the batch `trade_setup`.

    Tests written for the old `compute_trade_setup_async` mock (`mock_deps["setup"].return_value =
    _base_setup(...)`) still work unchanged — the fixture builds a matching batch response on
    each call via the side_effect hook.
    """

    def __init__(self, mock_batch: AsyncMock):
        self._mock_batch = mock_batch
        self.setup_mock = AsyncMock()

        async def _batch_side_effect(tickers, scan_date=None, risk_regime=None):
            result: dict[str, dict] = {}
            for ticker in tickers:
                upper = ticker.upper()
                setup_value = await self.setup_mock(upper, scan_date)
                tech = {**_base_tech_data(), "ticker": upper}
                tech["trade_setup"] = setup_value
                result[upper] = tech
            return result

        self._mock_batch.side_effect = _batch_side_effect


@pytest.fixture
def mock_deps():
    """Mock get_batch_ticker_data_async and external deps.

    Exposes a `setup` AsyncMock that controls the embedded `trade_setup` dict per ticker —
    preserves the calling convention of the pre-batch tests.
    """
    with (
        patch("agents.picks.get_batch_ticker_data_async", new_callable=AsyncMock) as mock_batch,
        patch("agents.picks.classify_strategy") as mock_strategy,
        patch("agents.picks.simulate_trade") as mock_sim,
        patch("agents.picks.compute_exit_plan") as mock_exit,
        patch("agents.picks.get_rsi_at_swing_low_date", new_callable=AsyncMock) as mock_rsi,
        # SWI-305 added a parallel ``get_daily_flow_batch`` call inside
        # extract_top_picks. Without this stub the test env tries to hit
        # the live vnstock API ("VNSTOCK_API_URL environment variable not
        # set"); the gather still returns a value (exception is captured),
        # but the live attempt logs a noisy traceback. Stubbing keeps the
        # output clean and matches the airgapped intent of the fixture.
        patch(
            "shared.api.enrichment.get_daily_flow_batch",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        fixture = _BatchFixture(mock_batch)

        # Default strategy classification
        from agents.tools.strategy_classifier import StrategyClassification

        mock_strategy.return_value = StrategyClassification(
            strategy="BOUNCE", confidence=0.8, matched_signals=["support_bounce"]
        )

        # Default simulation
        from unittest.mock import MagicMock

        sim_result = MagicMock()
        sim_result.expected_return_pct = 3.5
        sim_result.p_target = 0.6
        sim_result.p_stop = 0.3
        sim_result.recommended_action = "BUY"
        mock_sim.return_value = sim_result

        # Default exit plan
        mock_exit.return_value = {"legs": []}

        yield {
            "setup": fixture.setup_mock,
            "batch": mock_batch,
            "strategy": mock_strategy,
            "sim": mock_sim,
            "exit": mock_exit,
            "rsi": mock_rsi,
        }


@pytest.mark.usefixtures("mock_trading_config")
class TestPickActionDetermination:
    """BUY vs LIMIT_BUY action based on market_setup validity."""

    @pytest.mark.asyncio
    async def test_near_support_produces_buy(self, mock_deps):
        """No market_setup (price near support) → BUY at support."""
        mock_deps["setup"].return_value = _base_setup(entry=30000, close=30200, market_setup=None)

        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[_buy_signal()],
            scan_date=date(2026, 3, 26),
            min_rr=3.0,
        )

        assert len(picks) == 1
        assert picks[0]["action"] == "BUY"
        assert picks[0]["entry"] == 30000  # support level

    @pytest.mark.asyncio
    async def test_valid_market_produces_buy_at_market_price(self, mock_deps):
        """Gap > 1.5%, market R:R >= min_rr → BUY at current close."""
        market_setup = {
            "entry": 35000,
            "stop": 29400,
            "target": 42000,
            "risk_reward": 3.5,
            "shares": 80,
            "position_vnd": 2800000,
            "valid": True,
            "gap_from_support_pct": 4.2,
        }
        mock_deps["setup"].return_value = _base_setup(
            entry=30000, close=35000, market_setup=market_setup
        )

        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[_buy_signal()],
            scan_date=date(2026, 3, 26),
            min_rr=3.0,
        )

        assert len(picks) == 1
        assert picks[0]["action"] == "BUY"
        assert picks[0]["entry"] == 35000  # market price, NOT support

    @pytest.mark.asyncio
    async def test_invalid_market_produces_limit_buy(self, mock_deps):
        """Gap > 1.5%, market R:R < min_rr → LIMIT_BUY at support.

        min_rr=1.5 (not 3.0): the inline-pullback RR for (entry=33950,
        stop=29400, target=42000) lands around 1.77, so a 3.0 floor would
        correctly filter the LIMIT_BUY post-SWI-125. We test the synthesis
        path itself, not the floor — pick a floor below the inline RR so
        the pullback survives the post-filter.
        """
        market_setup = {
            "entry": 35000,
            "stop": 29400,
            "target": 42000,
            "risk_reward": 0.3,
            "shares": 80,
            "position_vnd": 2800000,
            "valid": False,
            "gap_from_support_pct": 6.0,
        }
        mock_deps["setup"].return_value = _base_setup(
            entry=30000, close=35000, market_setup=market_setup
        )

        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[_buy_signal()],
            scan_date=date(2026, 3, 26),
            min_rr=1.5,
        )

        assert len(picks) == 1
        assert picks[0]["action"] == "LIMIT_BUY"
        # Blind spot fix: inline pullback generated instead of unreachable support
        # entry = close * (1 - max_entry_gap_pct/100) = 35000 * 0.97 = 33950
        assert picks[0]["entry"] == 33950.0
        assert picks[0]["pullback_entry"] is True
        assert picks[0]["market_rr"] == 0.3

    @pytest.mark.asyncio
    async def test_market_rr_below_min_rr_produces_limit_buy(self, mock_deps):
        """Market R:R = 2.5, min_rr = 3.0 → LIMIT_BUY despite valid flag."""
        market_setup = {
            "entry": 32000,
            "stop": 29400,
            "target": 42000,
            "risk_reward": 2.5,
            "shares": 90,
            "position_vnd": 2880000,
            "valid": True,  # valid by 3.0 default, but below min_rr
            "gap_from_support_pct": 3.0,
        }
        mock_deps["setup"].return_value = _base_setup(
            entry=30000, close=32000, market_setup=market_setup
        )

        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[_buy_signal()],
            scan_date=date(2026, 3, 26),
            min_rr=3.0,
        )

        assert len(picks) == 1
        assert picks[0]["action"] == "LIMIT_BUY"

    @pytest.mark.asyncio
    async def test_pick_carries_target_basis_no_dual_rr(self, mock_deps):
        """Picks expose target_basis (not dual rr fields)."""
        mock_deps["setup"].return_value = _base_setup(
            entry=30000,
            close=30200,
            risk_reward=4.2,
            target_basis="aggressive",
            rr_stretch=None,
        )

        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[_buy_signal()],
            scan_date=date(2026, 3, 26),
            min_rr=3.0,
        )
        assert len(picks) == 1
        pick = picks[0]
        assert pick["target_basis"] == "aggressive"
        # Verdict derived deterministically from target_basis
        assert pick["verdict"] == "partial_size"
        # No dual rr fields surface up to the pick dict
        for dead in (
            "conservative_rr",
            "aggressive_rr",
            "conservative_target",
            "aggressive_target",
        ):
            assert dead not in pick
        # risk_reward stays a raw float (not pre-rounded)
        assert isinstance(pick["risk_reward"], float)

    @pytest.mark.asyncio
    async def test_borderline_rr_blocked_when_below_floor(self, mock_deps):
        """R:R outside the soft-band tolerance (10%) is rejected outright.

        rr=3.0 vs min_rr=3.5 → 14.3% miss > 10% tolerance → hard reject.
        """
        mock_deps["setup"].return_value = _base_setup(entry=30000, close=30200, risk_reward=3.0)
        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[_buy_signal()],
            scan_date=date(2026, 3, 26),
            min_rr=3.5,
        )
        assert picks == []

    @pytest.mark.asyncio
    async def test_borderline_rr_passes_when_at_floor(self, mock_deps):
        """Raw float 3.50 must pass min_rr=3.5 exactly."""
        mock_deps["setup"].return_value = _base_setup(entry=30000, close=30200, risk_reward=3.50)
        from agents.picks import extract_top_picks

        picks = await extract_top_picks(
            sector_signals=[_buy_signal()],
            scan_date=date(2026, 3, 26),
            min_rr=3.5,
        )
        assert len(picks) == 1

    @pytest.mark.asyncio
    async def test_atr_trail_pick_emits_buy_with_null_target_and_rr(self, mock_deps):
        """ATR_TRAIL strategy: action=BUY, target/risk_reward=None, exit_family=ATR_TRAIL."""
        # Strategy classifier returns a TREND_FOLLOW strategy (which dispatches to ATR_TRAIL).
        from agents.tools.strategy_classifier import StrategyClassification

        mock_deps["strategy"].return_value = StrategyClassification(
            strategy="MOMENTUM", confidence=0.8, matched_signals=["above_sma20", "rsi_strong"]
        )
        # Setup with ATR_TRAIL artifacts already stamped (mimics apply_exit_strategy mutating).
        # In the real path, apply_exit_strategy mutates setup; here we simulate via fixture +
        # patch resolve_exit_strategy to return a pass-through.
        setup = _base_setup(entry=30000, close=30200, risk_reward=4.0)
        mock_deps["setup"].return_value = setup

        # Stub the dispatch so it returns ATR_TRAIL pass.
        from unittest.mock import patch as _patch

        def fake_apply(**kwargs):
            s = kwargs["setup"]
            s["entry"] = 30000
            s["stop"] = 28500
            s["target"] = None
            s["risk_reward"] = None
            s["exit_family"] = "ATR_TRAIL"
            s["exit_state"] = {"strategy": "MOMENTUM"}
            return True, "ATR_TRAIL", 0.0

        # Tech data needs momentum_signals to satisfy trend gate; bypass by stubbing
        # buy_trend_follow_eligible.
        with (
            _patch("agents.picks.apply_exit_strategy", side_effect=fake_apply),
            _patch("agents.picks.buy_trend_follow_eligible", return_value=(True, "ok")),
        ):
            from agents.picks import extract_top_picks

            picks = await extract_top_picks(
                sector_signals=[_buy_signal()],
                scan_date=date(2026, 5, 5),
                min_rr=3.0,
            )

        assert len(picks) == 1
        pick = picks[0]
        assert pick["action"] == "BUY"
        assert pick["target"] is None
        assert pick["risk_reward"] is None
        assert pick["exit_family"] == "ATR_TRAIL"

    @pytest.mark.asyncio
    async def test_atr_trail_does_not_break_sort(self, mock_deps):
        """Mixed list: ATR_TRAIL (None RR) + FIXED_TARGET sorts deterministically."""
        from unittest.mock import patch as _patch

        from agents.tools.strategy_classifier import StrategyClassification

        def strategy_side_effect(*args, **kwargs):
            return StrategyClassification(
                strategy="BOUNCE", confidence=0.8, matched_signals=["support_bounce"]
            )

        mock_deps["strategy"].side_effect = strategy_side_effect

        def setup_side_effect(ticker, scan_date=None):
            return _base_setup(entry=30000, close=30200, risk_reward=4.0)

        mock_deps["setup"].side_effect = setup_side_effect

        call_count = {"n": 0}

        def fake_apply(**kwargs):
            s = kwargs["setup"]
            call_count["n"] += 1
            if call_count["n"] == 1:
                s["exit_family"] = "ATR_TRAIL"
                s["target"] = None
                s["risk_reward"] = None
                return True, "ATR_TRAIL", 0.0
            s["exit_family"] = "FIXED_TARGET"
            s["rr_flag"] = "pass"
            return True, "FIXED_TARGET", 4.0

        with (
            _patch("agents.picks.apply_exit_strategy", side_effect=fake_apply),
            _patch("agents.picks.buy_trend_follow_eligible", return_value=(True, "ok")),
        ):
            from agents.picks import extract_top_picks

            picks = await extract_top_picks(
                sector_signals=[_buy_signal("AAA"), _buy_signal("BBB")],
                scan_date=date(2026, 5, 5),
                min_rr=3.0,
            )

        # Should not raise on sort; both BUYs survive.
        assert len(picks) == 2
        assert all(p["action"] == "BUY" for p in picks)

    @pytest.mark.asyncio
    async def test_buy_sorted_before_limit_buy(self, mock_deps):
        """BUY picks appear before LIMIT_BUY picks of same R:R."""

        def side_effect(ticker, scan_date=None):
            if ticker == "AAA":
                # Near support → BUY
                return _base_setup(entry=30000, close=30200, risk_reward=4.0)
            else:
                # Far from support, bad market R:R → LIMIT_BUY
                return _base_setup(
                    entry=30000,
                    close=35000,
                    risk_reward=4.0,
                    market_setup={
                        "entry": 35000,
                        "stop": 29400,
                        "target": 42000,
                        "risk_reward": 0.5,
                        "shares": 80,
                        "position_vnd": 2800000,
                        "valid": False,
                        "gap_from_support_pct": 6.0,
                    },
                )

        mock_deps["setup"].side_effect = side_effect

        from agents.picks import extract_top_picks

        # min_rr=1.5 because BBB's inline-pullback RR lands ~1.77 (see
        # test_invalid_market_produces_limit_buy); a 3.0 floor would filter
        # the LIMIT_BUY via _passes_rr_floor (SWI-125) and the test would
        # only see AAA. We're testing sort order, not the RR gate.
        picks = await extract_top_picks(
            sector_signals=[_buy_signal("AAA"), _buy_signal("BBB")],
            scan_date=date(2026, 3, 26),
            min_rr=1.5,
        )

        assert len(picks) == 2
        assert picks[0]["action"] == "BUY"
        assert picks[0]["ticker"] == "AAA"
        assert picks[1]["action"] == "LIMIT_BUY"
        assert picks[1]["ticker"] == "BBB"
