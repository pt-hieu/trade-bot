"""Tests for deterministic trading mode determination."""

import pytest

from agents.trading_mode import determine_mode


@pytest.mark.usefixtures("mock_trading_config")
class TestDetermineMode:
    """Mode from deployable cash — pure deterministic."""

    def test_normal_healthy_cash(self):
        assert determine_mode(10_000_000) == "NORMAL"

    def test_normal_boundary(self):
        """5,000,001 VND → NORMAL."""
        assert determine_mode(5_000_001) == "NORMAL"

    def test_low_cash_boundary(self):
        """Exactly 5M → LOW_CASH (not > 5M)."""
        assert determine_mode(5_000_000) == "LOW_CASH"

    def test_low_cash_small(self):
        assert determine_mode(1_000_000) == "LOW_CASH"

    def test_low_cash_1_vnd(self):
        assert determine_mode(1) == "LOW_CASH"

    def test_reallocation_zero(self):
        assert determine_mode(0) == "REALLOCATION"

    def test_reallocation_negative(self):
        """Negative deployable (shouldn't happen, but defensive)."""
        assert determine_mode(-100_000) == "REALLOCATION"
