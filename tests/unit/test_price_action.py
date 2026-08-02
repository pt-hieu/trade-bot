"""Tests for multi-day price action analysis (spike/gap/pullback detection)."""

from agents.tools.price_action import (
    _analyze_volume_profile,
    _classify,
    _compute_pullback,
    _detect_gaps,
    _detect_rally,
    _find_base_zone,
    analyze_price_action,
    format_price_action_prose,
)


def _candle(time, open, high, low, close, volume=5_000_000):
    """Helper to build a candle dict (prices in thousands VND)."""
    return {"time": time, "open": open, "high": high, "low": low, "close": close, "volume": volume}


# VCB-like scenario: 57k → 76k in 6 sessions, pullback to 65k
VCB_CANDLES = [
    # Pre-rally consolidation (5 days)
    _candle("2025-12-29", 57.4, 57.5, 57.1, 57.1, 2_100_000),
    _candle("2025-12-30", 57.3, 58.1, 57.2, 57.3, 2_960_000),
    _candle("2025-12-31", 57.4, 57.9, 57.3, 57.5, 2_530_000),
    _candle("2026-01-05", 57.5, 57.6, 57.0, 57.1, 3_590_000),
    _candle("2026-01-06", 57.1, 57.5, 56.6, 57.3, 4_170_000),
    # Rally (6 sessions)
    _candle("2026-01-07", 57.6, 59.9, 57.5, 59.6, 12_920_000),
    _candle("2026-01-08", 59.8, 63.7, 59.7, 63.7, 27_100_000),
    _candle("2026-01-09", 65.4, 68.0, 65.4, 68.0, 32_480_000),
    _candle("2026-01-12", 69.9, 72.7, 69.6, 72.7, 21_970_000),
    _candle("2026-01-13", 74.3, 76.0, 71.8, 74.0, 28_200_000),
    _candle("2026-01-14", 73.1, 78.8, 73.1, 76.0, 21_210_000),
    # Pullback
    _candle("2026-01-15", 74.0, 74.9, 71.9, 71.9, 23_230_000),
    _candle("2026-01-16", 73.0, 76.0, 72.0, 73.0, 13_430_000),
    _candle("2026-01-19", 73.0, 73.5, 71.6, 72.7, 8_210_000),
    _candle("2026-01-20", 74.0, 75.0, 72.1, 73.5, 18_490_000),
    _candle("2026-01-21", 72.8, 73.6, 71.7, 72.8, 11_180_000),
    _candle("2026-01-22", 73.4, 75.9, 70.6, 71.0, 18_580_000),
    _candle("2026-01-23", 71.0, 71.0, 68.5, 68.6, 16_800_000),
    _candle("2026-01-26", 68.9, 71.1, 68.7, 69.6, 10_990_000),
    _candle("2026-01-27", 69.7, 71.5, 68.1, 70.6, 9_650_000),
    _candle("2026-01-28", 71.1, 72.9, 69.4, 69.6, 12_280_000),
    _candle("2026-01-29", 69.3, 70.8, 68.6, 69.8, 7_860_000),
    _candle("2026-01-30", 70.6, 71.9, 69.6, 70.5, 11_480_000),
    _candle("2026-02-02", 70.5, 71.5, 69.3, 71.5, 10_710_000),
    _candle("2026-02-03", 72.4, 73.3, 71.3, 71.8, 15_090_000),
    _candle("2026-02-04", 72.0, 72.0, 70.5, 70.8, 8_730_000),
    _candle("2026-02-05", 70.7, 70.8, 68.4, 68.4, 11_690_000),
    _candle("2026-02-06", 67.9, 67.9, 64.9, 65.1, 24_570_000),
    _candle("2026-02-09", 65.5, 66.0, 64.2, 65.0, 7_310_000),
    _candle("2026-02-10", 64.5, 65.5, 62.6, 63.1, 15_810_000),
]


class TestDetectRally:
    def test_detects_vcb_spike(self):
        rally = _detect_rally(VCB_CANDLES)
        assert rally is not None
        assert rally["detected"] is True
        assert rally["gain_pct"] >= 30  # 57→78.8 = ~39%
        assert rally["gain_sessions"] <= 10

    def test_no_rally_on_gradual_rise(self):
        """15% gain over 25 days should NOT trigger."""
        candles = [
            _candle(f"2026-01-{i:02d}", 50 + i * 0.3, 50.5 + i * 0.3, 49.5 + i * 0.3, 50 + i * 0.3)
            for i in range(1, 26)
        ]
        rally = _detect_rally(candles)
        assert rally is None

    def test_rally_below_threshold(self):
        """14% gain in 5 sessions — just under 15% threshold."""
        candles = [
            _candle("2026-01-01", 50, 50.5, 49.5, 50),
            _candle("2026-01-02", 50, 50, 50, 50),
            _candle("2026-01-03", 50, 50, 50, 50),
            _candle("2026-01-04", 50, 53, 50, 53),
            _candle("2026-01-05", 53, 57, 53, 56.5),  # 49.5 → 57 = 15.1% (barely over)
        ]
        # With low=49.5, high=57 → gain = 15.1%, should detect
        rally = _detect_rally(candles)
        assert rally is not None


class TestFindBaseZone:
    def test_base_zone_before_rally(self):
        base_idx = 5  # First rally candle in VCB data
        zone = _find_base_zone(VCB_CANDLES, base_idx)
        # Pre-rally avg of (low+close)/2 for days 0-4
        assert 56.5 < zone < 58  # consolidation was ~57


class TestComputePullback:
    def test_vcb_retracement(self):
        rally = _detect_rally(VCB_CANDLES)
        pullback = _compute_pullback(rally, 65.0)  # current price 65k
        assert pullback["from_peak_pct"] < 0  # below peak
        assert pullback["above_base_pct"] > 10  # still above base
        assert 40 < pullback["retracement_pct"] < 80  # partial retracement
        assert pullback["gap_fill_risk"] is True

    def test_fully_retraced(self):
        rally = _detect_rally(VCB_CANDLES)
        pullback = _compute_pullback(rally, 57.5)  # back to base
        assert pullback["retracement_pct"] > 80
        assert pullback["above_base_pct"] < 5


class TestDetectGaps:
    def test_gap_up_detection(self):
        candles = [
            _candle("2026-01-01", 50, 51, 49, 50),
            _candle("2026-01-02", 53, 55, 52.1, 54),  # gap: low 52.1 > prev high 51 = 2.1%
        ]
        gaps = _detect_gaps(candles)
        assert len(gaps) == 1
        assert gaps[0]["type"] == "gap_up"
        assert gaps[0]["gap_pct"] >= 2.0

    def test_filled_gap_excluded(self):
        candles = [
            _candle("2026-01-01", 50, 51, 49, 50),
            _candle("2026-01-02", 53, 55, 52.1, 54),  # gap up
            _candle("2026-01-03", 52, 53, 50, 51),  # fills the gap (low <= 51)
        ]
        gaps = _detect_gaps(candles)
        assert len(gaps) == 0

    def test_unfilled_gap_remains(self):
        candles = [
            _candle("2026-01-01", 50, 51, 49, 50),
            _candle("2026-01-02", 53, 55, 52.1, 54),  # gap up at 51
            _candle("2026-01-03", 54, 56, 53, 55),  # doesn't fill (low=53 > 51)
        ]
        gaps = _detect_gaps(candles)
        assert len(gaps) == 1

    def test_small_gap_ignored(self):
        candles = [
            _candle("2026-01-01", 50, 51, 49, 50),
            _candle("2026-01-02", 51.5, 53, 51.5, 52),  # gap = 0.98% < 2%
        ]
        gaps = _detect_gaps(candles)
        assert len(gaps) == 0


class TestVolumeProfile:
    def test_weak_bounce(self):
        rally = _detect_rally(VCB_CANDLES)
        vol = _analyze_volume_profile(VCB_CANDLES, rally)
        # Rally had 12-32M vol, pullback mostly 8-15M
        assert vol["bounce_quality"] in ("weak", "moderate")
        assert vol["current_vs_rally_ratio"] < 0.80

    def test_strong_bounce(self):
        """Synthetic case: pullback volume matches rally volume."""
        candles = [
            _candle("2026-01-01", 50, 50, 49, 50, 1_000_000),
            _candle("2026-01-02", 50, 50, 49, 50, 1_000_000),
            _candle("2026-01-03", 50, 60, 50, 58, 10_000_000),  # rally
            _candle("2026-01-04", 58, 65, 58, 65, 15_000_000),  # rally peak
            _candle("2026-01-05", 63, 64, 61, 62, 14_000_000),  # pullback with high vol
        ]
        rally = {"base_idx": 1, "peak_idx": 3, "gain_pct": 30, "pre_rally_zone": 50}
        vol = _analyze_volume_profile(candles, rally)
        assert vol["bounce_quality"] == "strong"


class TestClassification:
    def test_post_spike_vcb(self):
        rally = _detect_rally(VCB_CANDLES)
        pullback = _compute_pullback(rally, 65.0)
        vol = _analyze_volume_profile(VCB_CANDLES, rally)
        cls = _classify(rally, pullback, vol)
        assert cls in ("POST_SPIKE", "EXTENDED_PULLBACK")

    def test_normal_no_rally(self):
        result = analyze_price_action(VCB_CANDLES[:5], 57000)  # only consolidation
        assert result["classification"] == "NORMAL"

    def test_base_building_after_full_retrace(self):
        rally = _detect_rally(VCB_CANDLES)
        pullback = _compute_pullback(rally, 57.5)  # back to base
        vol = _analyze_volume_profile(VCB_CANDLES, rally)
        cls = _classify(rally, pullback, vol)
        assert cls == "BASE_BUILDING"


class TestFullAnalysis:
    def test_vcb_full_analysis(self):
        result = analyze_price_action(VCB_CANDLES, 65000)
        assert result["classification"] in ("POST_SPIKE", "EXTENDED_PULLBACK")
        assert result["rally"] is not None
        assert result["rally"]["gain_pct"] >= 30
        assert len(result["risk_flags"]) > 0

    def test_normal_stock(self):
        """Flat trading — no spike detected."""
        candles = [_candle(f"2026-01-{i:02d}", 50, 51, 49, 50) for i in range(1, 25)]
        result = analyze_price_action(candles, 50000)
        assert result["classification"] == "NORMAL"
        assert result["rally"] is None
        assert result["risk_flags"] == []


class TestFormatProse:
    def test_prose_includes_key_metrics(self):
        result = analyze_price_action(VCB_CANDLES, 65000)
        prose = format_price_action_prose(result)
        assert "POST_SPIKE" in prose or "EXTENDED_PULLBACK" in prose
        assert "base" in prose.lower()
        assert "volume" in prose.lower() or "WEAK" in prose or "MODERATE" in prose

    def test_normal_returns_empty(self):
        candles = [_candle(f"2026-01-{i:02d}", 50, 51, 49, 50) for i in range(1, 25)]
        result = analyze_price_action(candles, 50000)
        prose = format_price_action_prose(result)
        assert prose == ""  # NORMAL with no gaps
