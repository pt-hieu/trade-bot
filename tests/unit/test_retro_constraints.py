"""Unit tests for retro constraint computation.

Tests call the real compute_retro_constraints() function with mocked DB responses.
DB thresholds come from mock_trading_config fixture (TradingConfig defaults).
"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from agents.tools.retro_constraints import _empty_constraints, compute_retro_constraints

# ---------------------------------------------------------------------------
# _empty_constraints — pure function, no mocks needed
# ---------------------------------------------------------------------------


class TestEmptyConstraints:
    def test_empty_constraints_structure(self):
        """Empty constraints should have correct keys with None/empty defaults."""
        constraint = _empty_constraints()
        assert constraint["max_entries"] is None
        assert constraint["scale_override"] is None
        assert constraint["avoid_actions"] == []
        assert isinstance(constraint["constraint_text"], str)
        assert constraint["win_rate"] is None

    def test_empty_constraints_reason(self):
        """Empty constraints reason should appear in constraint_text."""
        constraint = _empty_constraints("test reason")
        assert "test reason" in constraint["constraint_text"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_summary_row(overall_win_rate: float) -> dict:
    """Build a learnings_summary DB row with win rate on 0-100 scale."""
    return {"overall_win_rate": overall_win_rate, "total_recs": 50}


def _make_pattern_row(
    description: str,
    loss_rate: float,
    sample_size: int,
    avoid_rule: str,
) -> dict:
    return {
        "pattern_type": "losing",
        "pattern_description": description,
        "loss_rate": loss_rate,
        "sample_size": sample_size,
        "avoid_rule": avoid_rule,
    }


def _mock_db(summary_row=None, pattern_rows=None) -> AsyncMock:
    """Build an AsyncMock db with fetch_one / fetch_all configured."""
    db = AsyncMock()
    db.fetch_one = AsyncMock(return_value=summary_row)
    db.fetch_all = AsyncMock(return_value=pattern_rows or [])
    return db


# ---------------------------------------------------------------------------
# Win rate thresholds (defaults: severe=25%, moderate=35% on TradingConfig)
# ---------------------------------------------------------------------------


class TestWinRateConstraints:
    async def test_win_rate_below_severe_threshold(self, mock_trading_config):
        """Win rate below retro_severe_winrate → max_entries=1, scale=0.5, min_rr raised."""
        # Default severe threshold = 35% → win_rate of 20 (stored 0-100 scale) triggers severe
        summary = _make_summary_row(20.0)
        db = _mock_db(summary_row=summary)

        with patch("shared.database.get_db", return_value=db):
            result = await compute_retro_constraints(date(2026, 3, 31))

        assert result["max_entries"] == mock_trading_config.retro_severe_max_entries
        assert result["scale_override"] == mock_trading_config.retro_severe_scale
        assert result["min_rr_override"] == mock_trading_config.retro_severe_min_rr
        assert result["win_rate"] == pytest.approx(0.20)

    async def test_win_rate_between_severe_and_moderate(self, mock_trading_config):
        """Win rate between severe and moderate thresholds → max_entries=2, no scale override."""
        # Default: severe=35%, moderate=45% → 40% sits in moderate band
        summary = _make_summary_row(40.0)
        db = _mock_db(summary_row=summary)

        with patch("shared.database.get_db", return_value=db):
            result = await compute_retro_constraints(date(2026, 3, 31))

        assert result["max_entries"] == mock_trading_config.retro_moderate_max_entries
        assert result["scale_override"] is None
        assert result["min_rr_override"] == mock_trading_config.retro_moderate_min_rr
        assert result["win_rate"] == pytest.approx(0.40)

    async def test_win_rate_above_moderate_threshold(self, mock_trading_config):
        """Win rate above moderate threshold → no constraints, max_entries/scale both None."""
        # 50% is well above moderate=35%
        summary = _make_summary_row(50.0)
        db = _mock_db(summary_row=summary)

        with patch("shared.database.get_db", return_value=db):
            result = await compute_retro_constraints(date(2026, 3, 31))

        assert result["max_entries"] is None
        assert result["scale_override"] is None
        assert result["min_rr_override"] is None
        assert result["win_rate"] == pytest.approx(0.50)

    async def test_no_win_rate_data(self, mock_trading_config):
        """No summary row → empty-like constraints with reason, no DB crash."""
        db = _mock_db(summary_row=None)

        with patch("shared.database.get_db", return_value=db):
            result = await compute_retro_constraints(date(2026, 3, 31))

        assert result["max_entries"] is None
        assert result["scale_override"] is None
        assert result["win_rate"] is None
        assert "No win rate data" in result["constraint_text"]

    async def test_win_rate_stored_as_0_1_scale_normalizes(self, mock_trading_config):
        """Win rate stored as 0-1 (e.g. 0.40) should be treated as 40%, not 0.4%."""
        # overall_win_rate=0.40 → already ≤1 → kept as 0.40 (40%), which is in moderate band
        summary = _make_summary_row(0.40)
        db = _mock_db(summary_row=summary)

        with patch("shared.database.get_db", return_value=db):
            result = await compute_retro_constraints(date(2026, 3, 31))

        # 0.40 is between severe(0.35) and moderate(0.45) → moderate constraints
        assert result["max_entries"] == mock_trading_config.retro_moderate_max_entries
        assert result["win_rate"] == pytest.approx(0.40)


# ---------------------------------------------------------------------------
# Avoid actions from high-loss patterns
# ---------------------------------------------------------------------------


class TestAvoidActions:
    async def test_high_loss_pattern_generates_avoid_action(self, mock_trading_config):
        """Pattern with loss_rate >= 70% and sample >= 3 should populate avoid_actions."""
        summary = _make_summary_row(50.0)
        patterns = [
            _make_pattern_row("BUY in RISK_OFF", 0.80, 5, "avoid_buy_risk_off"),
        ]
        db = _mock_db(summary_row=summary, pattern_rows=patterns)

        with patch("shared.database.get_db", return_value=db):
            result = await compute_retro_constraints(date(2026, 3, 31))

        assert "avoid_buy_risk_off" in result["avoid_actions"]
        assert len(result["avoid_actions"]) == 1

    async def test_multiple_high_loss_patterns_all_included(self, mock_trading_config):
        """Multiple qualifying patterns should all appear in avoid_actions."""
        summary = _make_summary_row(50.0)
        patterns = [
            _make_pattern_row("BUY in RISK_OFF", 0.80, 5, "avoid_buy_risk_off"),
            _make_pattern_row("Chasing breakout", 0.75, 4, "avoid_breakout_chase"),
        ]
        db = _mock_db(summary_row=summary, pattern_rows=patterns)

        with patch("shared.database.get_db", return_value=db):
            result = await compute_retro_constraints(date(2026, 3, 31))

        assert "avoid_buy_risk_off" in result["avoid_actions"]
        assert "avoid_breakout_chase" in result["avoid_actions"]
        assert len(result["avoid_actions"]) == 2

    async def test_pattern_without_avoid_rule_skipped(self, mock_trading_config):
        """Pattern row with empty/None avoid_rule should not add to avoid_actions."""
        summary = _make_summary_row(50.0)
        patterns = [
            _make_pattern_row("Some pattern", 0.80, 5, ""),
        ]
        db = _mock_db(summary_row=summary, pattern_rows=patterns)

        with patch("shared.database.get_db", return_value=db):
            result = await compute_retro_constraints(date(2026, 3, 31))

        assert result["avoid_actions"] == []

    async def test_no_patterns_empty_avoid_actions(self, mock_trading_config):
        """No pattern rows → avoid_actions is empty list."""
        summary = _make_summary_row(50.0)
        db = _mock_db(summary_row=summary, pattern_rows=[])

        with patch("shared.database.get_db", return_value=db):
            result = await compute_retro_constraints(date(2026, 3, 31))

        assert result["avoid_actions"] == []


# ---------------------------------------------------------------------------
# Constraint text content
# ---------------------------------------------------------------------------


class TestConstraintText:
    async def test_severe_constraint_text_mentions_threshold(self, mock_trading_config):
        """Severe regime: constraint text should mention entry count and threshold."""
        summary = _make_summary_row(20.0)
        db = _mock_db(summary_row=summary)

        with patch("shared.database.get_db", return_value=db):
            result = await compute_retro_constraints(date(2026, 3, 31))

        text = result["constraint_text"]
        assert "RETRO CONSTRAINTS" in text
        assert "20%" in text
        assert (
            str(mock_trading_config.retro_severe_winrate) in text
            or f"{mock_trading_config.retro_severe_winrate:.0f}%" in text
        )

    async def test_normal_constraint_text_says_normal_constraints(self, mock_trading_config):
        """Normal win rate: constraint text should say 'normal constraints apply'."""
        summary = _make_summary_row(60.0)
        db = _mock_db(summary_row=summary)

        with patch("shared.database.get_db", return_value=db):
            result = await compute_retro_constraints(date(2026, 3, 31))

        assert "normal constraints apply" in result["constraint_text"]

    async def test_avoid_lines_included_in_constraint_text(self, mock_trading_config):
        """High-loss pattern description and loss rate should appear in constraint text."""
        summary = _make_summary_row(50.0)
        patterns = [
            _make_pattern_row("BUY in RISK_OFF", 0.80, 5, "avoid_buy_risk_off"),
        ]
        db = _mock_db(summary_row=summary, pattern_rows=patterns)

        with patch("shared.database.get_db", return_value=db):
            result = await compute_retro_constraints(date(2026, 3, 31))

        text = result["constraint_text"]
        assert "BUY in RISK_OFF" in text
        assert "80%" in text
        assert "avoid_buy_risk_off" in text

    async def test_scale_override_mentioned_in_severe_text(self, mock_trading_config):
        """Severe constraints: scale override value should appear in constraint text."""
        summary = _make_summary_row(15.0)
        db = _mock_db(summary_row=summary)

        with patch("shared.database.get_db", return_value=db):
            result = await compute_retro_constraints(date(2026, 3, 31))

        text = result["constraint_text"]
        assert str(mock_trading_config.retro_severe_scale) in text


# ---------------------------------------------------------------------------
# DB failure fallback
# ---------------------------------------------------------------------------


class TestDbFailureFallback:
    async def test_db_exception_returns_empty_constraints(self, mock_trading_config):
        """DB error in get_db should return empty constraints dict with reason."""
        with patch(
            "shared.database.get_db",
            side_effect=Exception("connection refused"),
        ):
            result = await compute_retro_constraints(date(2026, 3, 31))

        assert result["max_entries"] is None
        assert result["scale_override"] is None
        assert result["avoid_actions"] == []
        assert result["win_rate"] is None
        assert "DB query failed" in result["constraint_text"]
        assert "connection refused" in result["constraint_text"]
