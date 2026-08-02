"""Tests for the pattern merging logic in retrospective."""

from retro_helpers.learnings import _merge_patterns


class TestMergePatterns:
    def test_new_patterns_appended(self):
        existing = [{"pattern": "Pattern A", "win_rate": 0.5, "sample_size": 10}]
        new = [{"pattern": "Pattern B", "win_rate": 0.7, "sample_size": 5}]
        result = _merge_patterns(existing, new)
        assert len(result) == 2
        names = {p["pattern"] for p in result}
        assert names == {"Pattern A", "Pattern B"}

    def test_matching_patterns_updated(self):
        existing = [
            {
                "pattern": "AVOID weak stocks",
                "win_rate": 0.3,
                "sample_size": 20,
                "actionable_rule": "old rule",
                "avoid_rule": "",
            }
        ]
        new = [
            {
                "pattern": "AVOID weak stocks",
                "win_rate": 0.25,
                "sample_size": 48,
                "actionable_rule": "",
                "avoid_rule": "new avoid rule",
            }
        ]
        result = _merge_patterns(existing, new)
        assert len(result) == 1
        assert result[0]["sample_size"] == 48  # updated
        assert result[0]["win_rate"] == 0.25  # updated
        assert result[0]["avoid_rule"] == "new avoid rule"  # updated (non-empty)

    def test_case_insensitive_dedup(self):
        existing = [{"pattern": "HOLD in volatile markets", "win_rate": 0.4, "sample_size": 15}]
        new = [{"pattern": "hold in volatile markets", "win_rate": 0.35, "sample_size": 19}]
        result = _merge_patterns(existing, new)
        assert len(result) == 1

    def test_max_patterns_enforced(self):
        existing = [
            {"pattern": f"Pattern {i}", "win_rate": 0.5, "sample_size": 100 - i} for i in range(5)
        ]
        new = [{"pattern": "New pattern", "win_rate": 0.8, "sample_size": 2}]
        result = _merge_patterns(existing, new, max_patterns=5)
        assert len(result) == 5
        # New pattern has smallest sample_size, should be dropped
        names = {p["pattern"] for p in result}
        assert "New pattern" not in names

    def test_new_pattern_with_large_sample_replaces_smallest(self):
        existing = [
            {"pattern": f"Pattern {i}", "win_rate": 0.5, "sample_size": 10 + i} for i in range(5)
        ]
        new = [{"pattern": "Big new pattern", "win_rate": 0.9, "sample_size": 50}]
        result = _merge_patterns(existing, new, max_patterns=5)
        assert len(result) == 5
        names = {p["pattern"] for p in result}
        assert "Big new pattern" in names
        assert "Pattern 0" not in names  # smallest, dropped

    def test_empty_existing(self):
        result = _merge_patterns([], [{"pattern": "First", "win_rate": 0.5, "sample_size": 10}])
        assert len(result) == 1

    def test_empty_new(self):
        existing = [{"pattern": "Existing", "win_rate": 0.5, "sample_size": 10}]
        result = _merge_patterns(existing, [])
        assert len(result) == 1

    def test_preserves_non_empty_actionable_rule(self):
        """When new pattern has empty actionable_rule, keep existing."""
        existing = [
            {
                "pattern": "P1",
                "win_rate": 0.5,
                "sample_size": 10,
                "actionable_rule": "do this",
                "avoid_rule": "",
            }
        ]
        new = [
            {
                "pattern": "P1",
                "win_rate": 0.6,
                "sample_size": 15,
                "actionable_rule": "",
                "avoid_rule": "",
            }
        ]
        result = _merge_patterns(existing, new)
        assert result[0]["actionable_rule"] == "do this"  # preserved

    def test_empty_existing_and_new(self):
        result = _merge_patterns([], [])
        assert result == []

    def test_duplicate_patterns_in_new(self):
        """Two identical patterns in new list — last one wins."""
        new = [
            {"pattern": "BUY on bounce", "win_rate": 0.5, "sample_size": 10},
            {"pattern": "BUY on bounce", "win_rate": 0.7, "sample_size": 15},
        ]
        result = _merge_patterns([], new)
        assert len(result) == 1
        assert result[0]["win_rate"] == 0.7
