"""SWI-140 / SWI-137 — VND normalization for midday RecommendationOverride.

Covers all three revised_* fields, the dropped-zeros pattern, and the
penny-stock edge case.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from shared.rules.midday_override_planning import infer_plan_type  # noqa: E402
from shared.rules.vnd_price_clamp import normalize_vnd_price  # noqa: E402


class TestNormalizeVndPrice:
    def test_none_input_returns_none(self) -> None:
        assert normalize_vnd_price(None, "stop at 44,910", agent="midday_override") is None

    def test_in_range_integer_returned_as_int(self) -> None:
        assert normalize_vnd_price(44910, "stop at 44,910", agent="midday_override") == 44910

    def test_in_range_float_rounded_to_int(self) -> None:
        assert normalize_vnd_price(44910.4, "stop at 44,910", agent="midday_override") == 44910

    def test_dropped_zeros_with_corroborating_reason_scaled(self) -> None:
        # SWI-140 today: revised_stop=44.91, reason cites 44,910.
        result = normalize_vnd_price(
            44.91, "Cancelling on stop break — stop at 44,910", agent="midday_override"
        )
        assert result == 44910

    def test_dropped_zeros_with_unformatted_5digit_reason_scaled(self) -> None:
        result = normalize_vnd_price(44.91, "Stop hit at 44910 today", agent="midday_override")
        assert result == 44910

    def test_sub_1000_with_no_corroborating_reason_raises(self) -> None:
        with pytest.raises(ValueError, match="no 5-digit price"):
            normalize_vnd_price(44.91, "thesis broken, exit position", agent="midday_override")

    def test_sub_1000_with_no_reason_raises(self) -> None:
        with pytest.raises(ValueError, match="no 5-digit price"):
            normalize_vnd_price(44.91, None, agent="midday_override")

    def test_above_max_raises(self) -> None:
        with pytest.raises(ValueError, match="exceeds max"):
            normalize_vnd_price(2_000_000, "any reason", agent="midday_override")

    def test_zero_value_raises(self) -> None:
        with pytest.raises(ValueError, match="non-positive"):
            normalize_vnd_price(0, "stop at 44,910", agent="midday_override")

    def test_negative_value_raises(self) -> None:
        with pytest.raises(ValueError, match="non-positive"):
            normalize_vnd_price(-100, "stop at 44,910", agent="midday_override")

    def test_in_range_value_with_5digit_reason_no_scale_applied(self) -> None:
        # 9999 is already in-range — no ×1000 scaling even when reason
        # text contains a 5-digit price token.
        assert normalize_vnd_price(9999, "Stop at 99990 hit", agent="midday_override") == 9999


class TestInferPlanType:
    def test_dual_listed_no_scope_returns_both(self) -> None:
        assert infer_plan_type("FPT", frozenset({"FPT", "VHM"})) == "BOTH"

    def test_dual_listed_with_swing_scope_returns_swing(self) -> None:
        assert infer_plan_type("FPT", frozenset({"FPT"}), "SWING") == "SWING"

    def test_dual_listed_with_long_term_scope_returns_long_term(self) -> None:
        assert infer_plan_type("FPT", frozenset({"FPT"}), "LONG_TERM") == "LONG_TERM"

    def test_legacy_longterm_alias_canonicalized(self) -> None:
        assert infer_plan_type("FPT", frozenset({"FPT"}), "LONGTERM") == "LONG_TERM"

    def test_single_listed_default_swing(self) -> None:
        assert infer_plan_type("ACV", frozenset({"FPT"})) == "SWING"

    def test_case_insensitive_ticker(self) -> None:
        assert infer_plan_type("fpt", frozenset({"FPT"})) == "BOTH"


class TestRecommendationOverrideIntegration:
    """End-to-end: pydantic model picks up the normalizer."""

    def test_revised_stop_unit_shift_normalized(self) -> None:
        from agents.midday import RecommendationOverride

        override = RecommendationOverride(
            ticker="ACV",
            morning_action="HOLD",
            midday_status="CANCEL",
            reason="Cancelling on stop break — stop at 44,910",
            revised_stop=44.91,
        )
        assert override.revised_stop == 44910

    def test_all_three_fields_normalized(self) -> None:
        from agents.midday import RecommendationOverride

        override = RecommendationOverride(
            ticker="ACV",
            morning_action="HOLD",
            midday_status="ADJUST",
            reason="Revising entry to 41,000 stop 39,500 target 47,500",
            revised_entry=41.0,
            revised_stop=39.5,
            revised_target=47.5,
        )
        assert override.revised_entry == 41000
        assert override.revised_stop == 39500
        assert override.revised_target == 47500

    def test_in_range_values_preserved(self) -> None:
        from agents.midday import RecommendationOverride

        override = RecommendationOverride(
            ticker="ACV",
            morning_action="HOLD",
            midday_status="ADJUST",
            reason="Revising entry to 41,000",
            revised_entry=41000,
            revised_stop=39500,
            revised_target=47500,
        )
        assert override.revised_entry == 41000
        assert override.revised_stop == 39500
        assert override.revised_target == 47500
