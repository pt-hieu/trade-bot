"""Tests for determine_entry_gate() — the pipeline's entry gate decision."""

import pytest

from shared.rules.entry_gates import (
    CRISIS_ENTRIES_BLOCKED_REASON,
    LOW_CASH_ENTRIES_BLOCKED_REASON,
    REALLOCATION_ENTRIES_BLOCKED_REASON,
    determine_entry_gate,
)


class TestNormalMode:
    """NORMAL mode with various regimes."""

    def test_normal_mode_no_regime_allows_entries(self):
        result = determine_entry_gate("NORMAL")
        assert result.entries_allowed is True
        assert result.entries_blocked_reason is None

    def test_normal_mode_calm_regime_allows_entries(self):
        result = determine_entry_gate("NORMAL", global_risk_regime="CALM")
        assert result.entries_allowed is True

    def test_normal_mode_cautious_regime_allows_entries(self):
        result = determine_entry_gate("NORMAL", global_risk_regime="CAUTIOUS")
        assert result.entries_allowed is True

    def test_normal_mode_elevated_regime_allows_entries(self):
        result = determine_entry_gate("NORMAL", global_risk_regime="ELEVATED")
        assert result.entries_allowed is True

    def test_normal_mode_risk_off_regime_allows_entries(self):
        result = determine_entry_gate("NORMAL", global_risk_regime="RISK_OFF")
        assert result.entries_allowed is True


class TestCrisisBlocking:
    """CRISIS regime blocks entries regardless of mode."""

    def test_crisis_blocks_normal_mode(self):
        result = determine_entry_gate("NORMAL", global_risk_regime="CRISIS")
        assert result.entries_allowed is False
        assert result.entries_blocked_reason == CRISIS_ENTRIES_BLOCKED_REASON

    def test_crisis_blocks_low_cash_mode(self):
        """CRISIS takes priority over LOW_CASH reason."""
        result = determine_entry_gate("LOW_CASH", global_risk_regime="CRISIS")
        assert result.entries_allowed is False
        assert "CRISIS" in (result.entries_blocked_reason or "")

    def test_crisis_blocks_reallocation_mode(self):
        """CRISIS takes priority over REALLOCATION reason."""
        result = determine_entry_gate("REALLOCATION", global_risk_regime="CRISIS")
        assert result.entries_allowed is False
        assert "CRISIS" in (result.entries_blocked_reason or "")


class TestCashModeBlocking:
    """Non-NORMAL modes block entries with reason strings."""

    def test_low_cash_blocks_entries(self):
        result = determine_entry_gate("LOW_CASH")
        assert result.entries_allowed is False
        assert result.entries_blocked_reason == LOW_CASH_ENTRIES_BLOCKED_REASON

    def test_low_cash_with_calm_regime(self):
        result = determine_entry_gate("LOW_CASH", global_risk_regime="CALM")
        assert result.entries_allowed is False
        assert "LOW_CASH" in (result.entries_blocked_reason or "")

    def test_reallocation_blocks_entries(self):
        result = determine_entry_gate("REALLOCATION")
        assert result.entries_allowed is False
        assert result.entries_blocked_reason == REALLOCATION_ENTRIES_BLOCKED_REASON

    def test_reallocation_with_elevated_regime(self):
        result = determine_entry_gate("REALLOCATION", global_risk_regime="ELEVATED")
        assert result.entries_allowed is False
        assert "REALLOCATION" in (result.entries_blocked_reason or "")


class TestTwoPhaseLifecycle:
    """Pre-Phase1 (no regime) vs Post-Phase1 (with regime)."""

    def test_pre_phase1_normal_allows(self):
        """Before regime is known, NORMAL mode allows entries."""
        result = determine_entry_gate("NORMAL", global_risk_regime=None)
        assert result.entries_allowed is True

    def test_post_phase1_crisis_overrides(self):
        """After Phase1 reveals CRISIS, entries are blocked."""
        pre = determine_entry_gate("NORMAL")
        assert pre.entries_allowed is True

        post = determine_entry_gate("NORMAL", global_risk_regime="CRISIS")
        assert post.entries_allowed is False


class TestDataclassProperties:
    """EntryGateResult is frozen and well-structured."""

    def test_result_is_frozen(self):
        result = determine_entry_gate("NORMAL")
        with pytest.raises(AttributeError):
            result.entries_allowed = False  # type: ignore[misc]

    def test_blocked_result_has_non_empty_reason(self):
        """Every blocked result must include a human-readable reason."""
        for mode in ("LOW_CASH", "REALLOCATION"):
            result = determine_entry_gate(mode)
            assert result.entries_blocked_reason is not None
            assert len(result.entries_blocked_reason) > 10

    def test_allowed_result_has_no_reason(self):
        result = determine_entry_gate("NORMAL", global_risk_regime="CALM")
        assert result.entries_blocked_reason is None
