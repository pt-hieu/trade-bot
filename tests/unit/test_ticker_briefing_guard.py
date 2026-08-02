"""Tests for INSUFFICIENT TECHNICAL DATA marker in ticker briefings."""

from pipeline.context_blocks_ticker import format_ticker_briefing


class TestTickerBriefingGuard:
    """Verify N/A data guard when technicals is None."""

    def test_insufficient_data_marker_when_technicals_none(self):
        result = format_ticker_briefing(ticker="FPT", technicals=None)
        assert "[INSUFFICIENT TECHNICAL DATA" in result
        assert "FPT" in result

    def test_na_price_when_technicals_none(self):
        result = format_ticker_briefing(ticker="FPT", technicals=None)
        assert "N/A VND" in result

    def test_no_marker_when_technicals_present(self):
        technicals = {"close": 76100, "rsi": 34.9}
        result = format_ticker_briefing(ticker="FPT", technicals=technicals)
        assert "INSUFFICIENT TECHNICAL DATA" not in result
        assert "76.1k VND" in result

    def test_marker_when_technicals_empty_dict(self):
        """Empty dict is falsy — should show marker."""
        result = format_ticker_briefing(ticker="TCB", technicals={})
        # Empty dict is falsy, so close_price = 0 → N/A
        assert "N/A VND" in result
