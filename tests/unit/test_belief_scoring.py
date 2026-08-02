"""Unit tests for Brier score computation and direction classification."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from agents.retro.belief_scoring import (
    DIRECTION_THRESHOLD_PCT,
    classify_actual_direction,
    compute_brier_score,
    resolve_mature_beliefs,
)


class TestBrierScore:
    def test_perfect_prediction_bullish(self):
        """Perfect prediction: agent said 100% bull and it was bullish."""
        score = compute_brier_score(1.0, 0.0, 0.0, "BULLISH")
        assert score == 0.0

    def test_perfect_prediction_bearish(self):
        score = compute_brier_score(0.0, 0.0, 1.0, "BEARISH")
        assert score == 0.0

    def test_worst_prediction(self):
        """Maximally wrong: said 100% bull but it was bearish."""
        score = compute_brier_score(1.0, 0.0, 0.0, "BEARISH")
        assert score == 2.0

    def test_uniform_prediction_bullish(self):
        """Uniform 33/33/33 — should score ~0.667."""
        score = compute_brier_score(1 / 3, 1 / 3, 1 / 3, "BULLISH")
        assert abs(score - 2 / 3) < 0.01

    def test_moderate_prediction(self):
        """60/25/15 when actual is bullish — should be low but not zero."""
        score = compute_brier_score(0.60, 0.25, 0.15, "BULLISH")
        # (0.6-1)^2 + (0.25-0)^2 + (0.15-0)^2 = 0.16 + 0.0625 + 0.0225 = 0.245
        assert abs(score - 0.245) < 0.001

    def test_moderate_prediction_wrong(self):
        """60/25/15 when actual is bearish — should be high."""
        score = compute_brier_score(0.60, 0.25, 0.15, "BEARISH")
        # (0.6-0)^2 + (0.25-0)^2 + (0.15-1)^2 = 0.36 + 0.0625 + 0.7225 = 1.145
        assert abs(score - 1.145) < 0.001

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError, match="Invalid direction"):
            compute_brier_score(0.5, 0.3, 0.2, "UP")

    def test_score_range(self):
        """All valid scores should be in [0, 2]."""
        for bull in [0.0, 0.25, 0.5, 0.75, 1.0]:
            for base in [0.0, 0.25, 0.5]:
                bear = 1.0 - bull - base
                if bear < 0:
                    continue
                for direction in ["BULLISH", "NEUTRAL", "BEARISH"]:
                    score = compute_brier_score(bull, base, bear, direction)
                    assert 0.0 <= score <= 2.0, f"Score {score} out of range"


class TestDirectionClassification:
    def test_bullish_above_threshold(self):
        result = classify_actual_direction(100000, 104000, threshold_pct=3.0)
        assert result == "BULLISH"

    def test_bearish_below_threshold(self):
        result = classify_actual_direction(100000, 96000, threshold_pct=3.0)
        assert result == "BEARISH"

    def test_neutral_within_threshold(self):
        result = classify_actual_direction(100000, 102000, threshold_pct=3.0)
        assert result == "NEUTRAL"

    def test_exactly_at_threshold_is_neutral(self):
        result = classify_actual_direction(100000, 103000, threshold_pct=3.0)
        assert result == "NEUTRAL"

    def test_just_above_threshold_is_bullish(self):
        result = classify_actual_direction(100000, 103001, threshold_pct=3.0)
        assert result == "BULLISH"

    def test_zero_entry_returns_neutral(self):
        result = classify_actual_direction(0, 100000)
        assert result == "NEUTRAL"

    def test_no_change(self):
        result = classify_actual_direction(50000, 50000)
        assert result == "NEUTRAL"

    def test_custom_threshold(self):
        result = classify_actual_direction(100000, 106000, threshold_pct=5.0)
        assert result == "BULLISH"

    def test_custom_threshold_neutral(self):
        result = classify_actual_direction(100000, 104000, threshold_pct=5.0)
        assert result == "NEUTRAL"


class TestDirectionClassification1_5Pct:
    """Tests for the default 1.5% threshold (VN market 5-day horizon)."""

    def test_default_threshold_is_1_5(self):
        assert DIRECTION_THRESHOLD_PCT == 1.5

    def test_bullish_above_1_5_pct(self):
        """1.6% up → BULLISH at default threshold."""
        result = classify_actual_direction(100000, 101600)
        assert result == "BULLISH"

    def test_bearish_below_1_5_pct(self):
        """1.6% down → BEARISH at default threshold."""
        result = classify_actual_direction(100000, 98400)
        assert result == "BEARISH"

    def test_neutral_within_1_5_pct(self):
        """1.0% up → NEUTRAL at default threshold."""
        result = classify_actual_direction(100000, 101000)
        assert result == "NEUTRAL"

    def test_exactly_at_1_5_pct_is_neutral(self):
        """Exactly 1.5% → NEUTRAL (strict > not >=)."""
        result = classify_actual_direction(100000, 101500)
        assert result == "NEUTRAL"


def _belief(
    *,
    belief_id: int,
    ticker: str,
    record_date: date,
    timeframe_days: int,
    direction: str = "BULLISH",
    bull: float = 0.6,
    base: float = 0.3,
    bear: float = 0.1,
) -> dict:
    return {
        "id": belief_id,
        "ticker": ticker,
        "agent_key": "sector",
        "record_date": record_date,
        "timeframe_days": timeframe_days,
        "direction": direction,
        "bull_probability": bull,
        "base_probability": base,
        "bear_probability": bear,
        "price_target_vnd": None,
    }


class TestResolveMatureBeliefs:
    """Trading-day-aware belief horizon resolution.

    A belief's calendar_horizon = record_date + timeframe_days. The outcome_date
    used for scoring must be the FIRST trading day at-or-after that horizon —
    not the most recent trading day before it (the prior get_price_on_date
    lookback shortened the prediction window).
    """

    @pytest.mark.asyncio
    async def test_weekend_horizon_rolls_forward(self):
        """record_date Apr 20 + 5d = Apr 25 (Sat) → outcome_date Apr 27 (Mon).

        2026-04-27 is Hung Kings' Day (holiday) so next trading day is Apr 28.
        Adjust expectation: weekend that rolls into a holiday → next trading.
        """
        belief = _belief(
            belief_id=1,
            ticker="FPT",
            record_date=date(2026, 4, 20),
            timeframe_days=5,
        )
        scan_date = date(2026, 4, 28)
        captured_outcome_dates: list[date] = []

        async def fake_get_price_on_date(ticker: str, target_date: date) -> dict:
            captured_outcome_dates.append(target_date)
            return {"close": 100.0}

        with (
            patch(
                "shared.neon.get_unresolved_beliefs",
                AsyncMock(return_value=[belief]),
            ),
            patch(
                "shared.vnstock_client.get_price_on_date",
                side_effect=fake_get_price_on_date,
            ),
            patch("shared.neon.resolve_beliefs", AsyncMock(return_value=1)),
            patch("shared.neon.get_stale_beliefs", AsyncMock(return_value=[])),
            patch("shared.neon.tombstone_beliefs", AsyncMock(return_value=0)),
        ):
            result = await resolve_mature_beliefs(scan_date)

        assert result.unresolved_found == 1
        assert date(2026, 4, 28) in captured_outcome_dates
        assert date(2026, 4, 25) not in captured_outcome_dates

    @pytest.mark.asyncio
    async def test_holiday_horizon_rolls_forward(self):
        """record_date Apr 22 + 5d = Apr 27 (holiday) → outcome_date Apr 28."""
        belief = _belief(
            belief_id=2,
            ticker="VCB",
            record_date=date(2026, 4, 22),
            timeframe_days=5,
        )
        scan_date = date(2026, 4, 28)
        captured_outcome_dates: list[date] = []

        async def fake_get_price_on_date(ticker: str, target_date: date) -> dict:
            captured_outcome_dates.append(target_date)
            return {"close": 100.0}

        with (
            patch(
                "shared.neon.get_unresolved_beliefs",
                AsyncMock(return_value=[belief]),
            ),
            patch(
                "shared.vnstock_client.get_price_on_date",
                side_effect=fake_get_price_on_date,
            ),
            patch("shared.neon.resolve_beliefs", AsyncMock(return_value=1)),
            patch("shared.neon.get_stale_beliefs", AsyncMock(return_value=[])),
            patch("shared.neon.tombstone_beliefs", AsyncMock(return_value=0)),
        ):
            result = await resolve_mature_beliefs(scan_date)

        assert result.unresolved_found == 1
        assert date(2026, 4, 28) in captured_outcome_dates
        assert date(2026, 4, 27) not in captured_outcome_dates

    @pytest.mark.asyncio
    async def test_trading_day_horizon_unchanged(self):
        """record_date Apr 20 + 2d = Apr 22 (Wed, trading) → outcome_date Apr 22."""
        belief = _belief(
            belief_id=3,
            ticker="HPG",
            record_date=date(2026, 4, 20),
            timeframe_days=2,
        )
        scan_date = date(2026, 4, 28)
        captured_outcome_dates: list[date] = []

        async def fake_get_price_on_date(ticker: str, target_date: date) -> dict:
            captured_outcome_dates.append(target_date)
            return {"close": 100.0}

        with (
            patch(
                "shared.neon.get_unresolved_beliefs",
                AsyncMock(return_value=[belief]),
            ),
            patch(
                "shared.vnstock_client.get_price_on_date",
                side_effect=fake_get_price_on_date,
            ),
            patch("shared.neon.resolve_beliefs", AsyncMock(return_value=1)),
            patch("shared.neon.get_stale_beliefs", AsyncMock(return_value=[])),
            patch("shared.neon.tombstone_beliefs", AsyncMock(return_value=0)),
        ):
            result = await resolve_mature_beliefs(scan_date)

        assert result.unresolved_found == 1
        assert date(2026, 4, 22) in captured_outcome_dates

    @pytest.mark.asyncio
    async def test_not_yet_mature_is_skipped(self):
        """trading_horizon > scan_date → goes to skipped_not_yet_mature, not scored."""
        # record_date Apr 26 (Sun) + 1d = Apr 27 (holiday) → trading_horizon Apr 28.
        # scan_date Apr 27 → trading_horizon (Apr 28) > scan_date → skip as not-yet-mature.
        belief = _belief(
            belief_id=4,
            ticker="MWG",
            record_date=date(2026, 4, 26),
            timeframe_days=1,
        )
        scan_date = date(2026, 4, 27)

        get_price_mock = AsyncMock()

        with (
            patch(
                "shared.neon.get_unresolved_beliefs",
                AsyncMock(return_value=[belief]),
            ),
            patch(
                "shared.vnstock_client.get_price_on_date",
                get_price_mock,
            ),
            patch("shared.neon.resolve_beliefs", AsyncMock(return_value=0)),
            patch("shared.neon.get_stale_beliefs", AsyncMock(return_value=[])),
            patch("shared.neon.tombstone_beliefs", AsyncMock(return_value=0)),
        ):
            result = await resolve_mature_beliefs(scan_date)

        assert result.unresolved_found == 1
        assert "sector/MWG" in result.skipped_not_yet_mature
        assert "sector/MWG" not in result.skipped_missing_outcome_price
        assert get_price_mock.await_count == 0
