"""Tests for PENDING evaluation resolution over multi-day holding period."""

import pytest

from agents.retro.resolve_pending import resolve_pending_evaluations


def _make_eval(
    eval_id: str = "eval-1",
    ticker: str = "FPT",
    entry_price: int = 80000,
    stop_price: int = 76000,
    target_price: int = 88000,
) -> dict:
    return {
        "id": eval_id,
        "ticker": ticker,
        "entry_price_vnd": entry_price,
        "stop_price_vnd": stop_price,
        "target_price_vnd": target_price,
        "record_date": "2026-04-05",
    }


def _make_day(date: str, high: int, low: int, close: int = 0) -> dict:
    return {"date": date, "open": low, "high": high, "low": low, "close": close or high}


class TestResolvePending:
    def test_target_hit_resolves_to_win(self):
        evals = [_make_eval(target_price=85000)]
        prices = {"FPT": [_make_day("2026-04-06", high=86000, low=79000)]}

        result = resolve_pending_evaluations(evals, prices)

        assert len(result) == 1
        eval_id, status, pnl = result[0]
        assert status == "WIN"
        assert pnl == pytest.approx(6.25, abs=0.01)  # (85000-80000)/80000*100

    def test_stop_hit_resolves_to_loss(self):
        evals = [_make_eval(stop_price=76000)]
        prices = {"FPT": [_make_day("2026-04-06", high=82000, low=75000)]}

        result = resolve_pending_evaluations(evals, prices)

        assert len(result) == 1
        _, status, pnl = result[0]
        assert status == "LOSS"
        assert pnl == pytest.approx(-5.0, abs=0.01)  # (76000-80000)/80000*100

    def test_stop_before_target_same_day(self):
        """When both stop and target hit same day, LOSS wins (stop-before-target priority)."""
        evals = [_make_eval(stop_price=76000, target_price=85000)]
        # Both stop (low=75000 <= 76000) and target (high=86000 >= 85000) hit
        prices = {"FPT": [_make_day("2026-04-06", high=86000, low=75000)]}

        result = resolve_pending_evaluations(evals, prices)

        assert len(result) == 1
        _, status, _ = result[0]
        assert status == "LOSS"

    def test_target_hit_on_day_3(self):
        """Target hit on day 3 of holding period."""
        evals = [_make_eval(target_price=85000)]
        prices = {
            "FPT": [
                _make_day("2026-04-06", high=82000, low=79000),  # Day 1: no hit
                _make_day("2026-04-07", high=83000, low=80000),  # Day 2: no hit
                _make_day("2026-04-08", high=86000, low=81000),  # Day 3: target hit
            ]
        }

        result = resolve_pending_evaluations(evals, prices)

        assert len(result) == 1
        _, status, _ = result[0]
        assert status == "WIN"

    def test_no_resolution_stays_pending(self):
        """Neither stop nor target hit within holding period."""
        evals = [_make_eval(stop_price=76000, target_price=88000)]
        prices = {
            "FPT": [
                _make_day("2026-04-06", high=82000, low=79000),
                _make_day("2026-04-07", high=83000, low=78000),
                _make_day("2026-04-08", high=81000, low=77000),
            ]
        }

        result = resolve_pending_evaluations(evals, prices)

        assert len(result) == 0  # Still PENDING

    def test_no_price_data_skipped(self):
        evals = [_make_eval(ticker="VHM")]
        prices = {}  # No price data for VHM

        result = resolve_pending_evaluations(evals, prices)

        assert len(result) == 0

    def test_multiple_evals_different_tickers(self):
        evals = [
            _make_eval(eval_id="e1", ticker="FPT", target_price=85000),
            _make_eval(
                eval_id="e2", ticker="TCB", entry_price=30000, stop_price=28000, target_price=33000
            ),
        ]
        prices = {
            "FPT": [_make_day("2026-04-06", high=86000, low=79000)],  # Target hit
            "TCB": [_make_day("2026-04-06", high=31000, low=27000)],  # Stop hit
        }

        result = resolve_pending_evaluations(evals, prices)

        assert len(result) == 2
        results_by_id = {r[0]: r for r in result}
        assert results_by_id["e1"][1] == "WIN"
        assert results_by_id["e2"][1] == "LOSS"

    def test_no_entry_price_skipped(self):
        evals = [_make_eval(entry_price=0)]
        prices = {"FPT": [_make_day("2026-04-06", high=90000, low=70000)]}

        result = resolve_pending_evaluations(evals, prices)

        assert len(result) == 0

    def test_max_holding_days_respected(self):
        """Only checks first MAX_HOLDING_DAYS (5) days."""
        evals = [_make_eval(target_price=90000)]
        # 6 days of data, target only hit on day 6
        prices = {
            "FPT": [_make_day(f"2026-04-{6 + i:02d}", high=82000, low=79000) for i in range(5)]
            + [_make_day("2026-04-11", high=91000, low=80000)]
        }

        result = resolve_pending_evaluations(evals, prices)

        assert len(result) == 0  # Day 6 is beyond MAX_HOLDING_DAYS=5
