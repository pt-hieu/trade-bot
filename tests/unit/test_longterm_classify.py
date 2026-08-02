"""Tests for deterministic longterm status classification."""

from agents.longterm import classify_longterm_status


class TestClassifyLongtermStatus:
    """gap_pct + status from price vs entry zone."""

    def test_buy_zone_below_entry(self):
        gap_pct, status = classify_longterm_status(price=90000, entry_zone=95000)
        assert status == "BUY ZONE"
        assert gap_pct < 0

    def test_buy_zone_at_entry(self):
        gap_pct, status = classify_longterm_status(price=95000, entry_zone=95000)
        assert status == "BUY ZONE"
        assert gap_pct == 0.0

    def test_near_entry_1pct(self):
        gap_pct, status = classify_longterm_status(price=95950, entry_zone=95000)
        assert status == "NEAR ENTRY"
        assert 0 < gap_pct <= 5

    def test_near_entry_boundary_5pct(self):
        gap_pct, status = classify_longterm_status(price=99750, entry_zone=95000)
        assert status == "NEAR ENTRY"
        assert gap_pct == 5.0

    def test_watch_6pct(self):
        gap_pct, status = classify_longterm_status(price=100700, entry_zone=95000)
        assert status == "WATCH"
        assert 5 < gap_pct <= 15

    def test_watch_boundary_15pct(self):
        gap_pct, status = classify_longterm_status(price=109250, entry_zone=95000)
        assert status == "WATCH"
        assert gap_pct == 15.0

    def test_wait_above_15pct(self):
        gap_pct, status = classify_longterm_status(price=120000, entry_zone=95000)
        assert status == "WAIT"
        assert gap_pct > 15

    def test_zero_entry_zone(self):
        gap_pct, status = classify_longterm_status(price=95000, entry_zone=0)
        assert status == "WAIT"
        assert gap_pct == 0.0

    def test_negative_entry_zone(self):
        gap_pct, status = classify_longterm_status(price=95000, entry_zone=-1)
        assert status == "WAIT"

    def test_gap_pct_precision(self):
        gap_pct, _ = classify_longterm_status(price=96333, entry_zone=95000)
        # Should be rounded to 1 decimal
        assert gap_pct == round(gap_pct, 1)
