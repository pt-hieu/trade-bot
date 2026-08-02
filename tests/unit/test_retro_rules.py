"""Tests for retro rule key generation and actionable rule computation."""

from agents.retro.rules import build_avoid_rule_key, compute_actionable_rules

# ============================================================================
# build_avoid_rule_key — stable key generation
# ============================================================================


class TestBuildAvoidRuleKey:
    """Key must be stable regardless of volatile percentage data."""

    def test_analysis_error(self):
        assert build_avoid_rule_key("HOLD", "ANALYSIS_ERROR") == "avoid:HOLD:ANALYSIS_ERROR"

    def test_execution_error(self):
        assert build_avoid_rule_key("BUY", "EXECUTION_ERROR") == "avoid:BUY:EXECUTION_ERROR"

    def test_calibration_error(self):
        assert (
            build_avoid_rule_key("LIMIT_BUY", "CALIBRATION_ERROR")
            == "avoid:LIMIT_BUY:CALIBRATION_ERROR"
        )

    def test_na_maps_to_general(self):
        assert build_avoid_rule_key("HOLD", "N/A") == "avoid:HOLD:GENERAL"

    def test_unknown_action_fallback(self):
        assert build_avoid_rule_key("UNKNOWN", "ANALYSIS_ERROR") == "avoid:UNKNOWN:ANALYSIS_ERROR"

    def test_key_independent_of_percentage(self):
        """Two runs with different loss rates must produce the same key."""
        key_run_1 = build_avoid_rule_key("HOLD", "ANALYSIS_ERROR")
        key_run_2 = build_avoid_rule_key("HOLD", "ANALYSIS_ERROR")
        assert key_run_1 == key_run_2

    def test_different_actions_produce_different_keys(self):
        assert build_avoid_rule_key("HOLD", "GENERAL") != build_avoid_rule_key("BUY", "GENERAL")

    def test_different_errors_produce_different_keys(self):
        assert build_avoid_rule_key("HOLD", "ANALYSIS_ERROR") != build_avoid_rule_key(
            "HOLD", "EXECUTION_ERROR"
        )

    def test_key_fits_varchar_100(self):
        """Longest plausible key must fit VARCHAR(100)."""
        longest_key = build_avoid_rule_key("LIMIT_BUY", "CALIBRATION_ERROR")
        assert len(longest_key) <= 100


# ============================================================================
# compute_actionable_rules — action threading
# ============================================================================


class TestComputeActionableRulesActionType:
    """Verify action flows from pattern to rule output."""

    def test_action_present_in_output(self):
        losing_patterns = [
            {
                "action": "HOLD",
                "avoid_rule": "HOLD signals failing at 85% — reduce size or skip",
                "sample_size": 12,
                "loss_rate": 0.85,
                "dominant_error": "ANALYSIS_ERROR",
                "error_breakdown": {
                    "ANALYSIS_ERROR": 8,
                    "EXECUTION_ERROR": 2,
                    "CALIBRATION_ERROR": 0,
                    "VARIANCE": 2,
                },
            }
        ]
        rules = compute_actionable_rules(losing_patterns)
        assert len(rules) == 1
        assert rules[0]["action"] == "HOLD"

    def test_missing_action_defaults_to_unknown(self):
        losing_patterns = [
            {
                "avoid_rule": "MYSTERY signals failing at 90% — reduce size or skip",
                "sample_size": 10,
                "loss_rate": 0.90,
                "dominant_error": "ANALYSIS_ERROR",
                "error_breakdown": {
                    "ANALYSIS_ERROR": 7,
                    "EXECUTION_ERROR": 1,
                    "CALIBRATION_ERROR": 0,
                    "VARIANCE": 2,
                },
            }
        ]
        rules = compute_actionable_rules(losing_patterns)
        assert len(rules) == 1
        assert rules[0]["action"] == "UNKNOWN"

    def test_variance_dominated_skipped(self):
        losing_patterns = [
            {
                "action": "HOLD",
                "avoid_rule": "HOLD signals failing at 80% — reduce size or skip",
                "sample_size": 10,
                "loss_rate": 0.80,
                "dominant_error": "VARIANCE",
                "error_breakdown": {
                    "ANALYSIS_ERROR": 1,
                    "EXECUTION_ERROR": 1,
                    "CALIBRATION_ERROR": 0,
                    "VARIANCE": 8,
                },
            }
        ]
        rules = compute_actionable_rules(losing_patterns)
        assert len(rules) == 0
