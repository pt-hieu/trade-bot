"""Unit tests for midday/helpers.py — big_movers and position_alerts."""

from midday.helpers import compute_big_movers, compute_position_alerts


class TestComputeBigMovers:
    """Tests for compute_big_movers with prev_close support."""

    def test_uses_prev_close_when_available(self):
        """Gap-down should appear as big mover using prev_close."""
        prices = {
            "VHM": {"prev_close": 108, "open": 102.5, "close": 104.2},
        }
        movers = compute_big_movers(prices, threshold=3.0)
        assert len(movers) == 1
        assert movers[0]["ticker"] == "VHM"
        # (104.2 - 108) / 108 = -3.5%
        assert movers[0]["change_pct"] == -3.5
        assert movers[0]["direction"] == "DOWN"

    def test_falls_back_to_open_when_no_prev_close(self):
        """Without prev_close, use open as base."""
        prices = {
            "FPT": {"open": 90, "close": 94},
        }
        movers = compute_big_movers(prices, threshold=3.0)
        assert len(movers) == 1
        # (94 - 90) / 90 = 4.4%
        assert movers[0]["change_pct"] == 4.4

    def test_gap_down_not_hidden(self):
        """VHM-like scenario: open->close = +1.7% but prev_close->close = -3.5%."""
        prices = {
            "VHM": {"prev_close": 108, "open": 102.5, "close": 104.2},
        }
        # With 3% threshold, this SHOULD appear (3.5% from prev_close)
        movers = compute_big_movers(prices, threshold=3.0)
        assert len(movers) == 1
        # Without prev_close fix, (104.2-102.5)/102.5 = 1.7% → would be missed
        assert abs(movers[0]["change_pct"]) >= 3.0

    def test_below_threshold_excluded(self):
        """Small moves excluded."""
        prices = {
            "TCB": {"prev_close": 36, "open": 35.5, "close": 35.8},
        }
        movers = compute_big_movers(prices, threshold=3.0)
        assert len(movers) == 0

    def test_skips_error_entries(self):
        """Entries with 'error' key are skipped."""
        prices = {
            "BAD": {"error": "no data"},
        }
        movers = compute_big_movers(prices)
        assert len(movers) == 0

    def test_none_prev_close_falls_back(self):
        """prev_close=None should fall back to open."""
        prices = {
            "FPT": {"prev_close": None, "open": 90, "close": 94},
        }
        movers = compute_big_movers(prices, threshold=3.0)
        assert len(movers) == 1
        assert movers[0]["change_pct"] == 4.4


class TestComputePositionAlerts:
    """Tests for compute_position_alerts with stop breach detection."""

    def test_stop_breached_at_open(self):
        """VHM-like: stop at 106k, low at 102.5k → STOP_INTRADAY_TOUCH."""
        recs = [{"ticker": "VHM", "stop_price": 106_000, "target_price": None}]
        prices = {"VHM": {"close": 104.2, "low": 102.5}}
        alerts = compute_position_alerts(recs, prices)
        assert len(alerts) == 1
        assert alerts[0]["level_type"] == "STOP_INTRADAY_TOUCH"
        assert alerts[0]["urgency"] == "critical"

    def test_near_stop_still_works(self):
        """Price near stop but not breached → STOP with threshold urgency."""
        recs = [{"ticker": "FPT", "stop_price": 89_000, "target_price": None}]
        prices = {"FPT": {"close": 90.5, "low": 90.0}}
        alerts = compute_position_alerts(recs, prices)
        assert len(alerts) == 1
        assert alerts[0]["level_type"] == "STOP"
        assert alerts[0]["urgency"] in ("high", "medium")

    def test_stop_far_away_no_alert(self):
        """Price well above stop → no alert."""
        recs = [{"ticker": "FPT", "stop_price": 80_000, "target_price": None}]
        prices = {"FPT": {"close": 90, "low": 89}}
        alerts = compute_position_alerts(recs, prices)
        assert len(alerts) == 0

    def test_target_near_still_works(self):
        """Target proximity alerts unchanged."""
        recs = [{"ticker": "FPT", "stop_price": None, "target_price": 95_000}]
        prices = {"FPT": {"close": 94, "low": 93}}
        alerts = compute_position_alerts(recs, prices)
        assert len(alerts) == 1
        assert alerts[0]["level_type"] == "TARGET"

    def test_stop_breached_with_bounce(self):
        """Low breached stop but current bounced above → still STOP_INTRADAY_TOUCH."""
        recs = [{"ticker": "VHM", "stop_price": 106_000, "target_price": None}]
        # Low was 100k (below 106k stop), but current bounced to 107k
        prices = {"VHM": {"close": 107, "low": 100}}
        alerts = compute_position_alerts(recs, prices)
        assert len(alerts) == 1
        assert alerts[0]["level_type"] == "STOP_INTRADAY_TOUCH"
