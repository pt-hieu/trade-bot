"""
Unit tests for compute_trailing_stop() in scripts/agents/tools/trailing_stops.py.

All tests are pure (no DB, no async) — relies on mock_trading_config fixture
to seed TradingConfig with defaults so get_trading_config() works without a DB.

Default config values used throughout:
    longterm_catastrophic_pct  = 20.0   → floor = entry * 0.80
    longterm_review_weight_pct = 30.0
    breakeven_gain_pct         = 10.0   → [0, 10) → breakeven stop
    half_trail_gain_pct        = 15.0   → [10, 15) → 50% trail
    tight_current_floor_pct    = 95.0   → current * 0.95
    tight_gain_lock_pct        = 75.0   → entry + gain * 0.75
"""

import pytest

from agents.tools.trailing_stops import compute_trailing_stop

# ──────────────────────────────────────────────────────────────────────────────
# LONGTERM
# ──────────────────────────────────────────────────────────────────────────────


class TestLongtermStop:
    """LONGTERM plan_type: thesis-based, no technical stop."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_trading_config):
        self.cfg = mock_trading_config

    def test_stop_is_none(self):
        result = compute_trailing_stop(
            entry=100_000, current=120_000, plan_type="LONGTERM", weight_pct=10.0
        )
        assert result["stop"] is None

    def test_stop_type_is_thesis_based(self):
        result = compute_trailing_stop(
            entry=100_000, current=120_000, plan_type="LONGTERM", weight_pct=10.0
        )
        assert result["stop_type"] == "thesis_based"

    def test_action_hint_hold_when_below_review_threshold(self):
        # weight_pct=25 < longterm_review_weight_pct=30
        result = compute_trailing_stop(
            entry=100_000, current=120_000, plan_type="LONGTERM", weight_pct=25.0
        )
        assert result["action_hint"] == "HOLD"

    def test_thesis_checkpoints_always_present(self):
        result = compute_trailing_stop(
            entry=100_000, current=120_000, plan_type="LONGTERM", weight_pct=10.0
        )
        assert isinstance(result["thesis_checkpoints"], list)
        assert len(result["thesis_checkpoints"]) > 0

    def test_catastrophic_stop_equals_entry_times_floor(self):
        # catastrophic_floor = 1 - 20/100 = 0.80 → 100_000 * 0.80 = 80_000.0
        result = compute_trailing_stop(
            entry=100_000, current=120_000, plan_type="LONGTERM", weight_pct=10.0
        )
        assert result["catastrophic_stop"] == pytest.approx(80_000.0, abs=1)

    def test_catastrophic_stop_rounded_to_one_decimal(self):
        # entry=93_500 → 93_500 * 0.80 = 74_800.0 (exact)
        result = compute_trailing_stop(
            entry=93_500, current=100_000, plan_type="LONGTERM", weight_pct=10.0
        )
        assert result["catastrophic_stop"] == pytest.approx(74_800.0, abs=1)

    def test_catastrophic_stop_none_when_entry_zero(self):
        result = compute_trailing_stop(
            entry=0, current=50_000, plan_type="LONGTERM", weight_pct=10.0
        )
        assert result["catastrophic_stop"] is None

    @pytest.mark.parametrize(
        "weight_pct,expected_hint",
        [
            (30.0, "HOLD"),  # boundary: exactly at threshold → still HOLD
            (30.1, "REVIEW_CONCENTRATION"),  # just above → triggers review
            (50.0, "REVIEW_CONCENTRATION"),  # well above
        ],
    )
    def test_review_concentration_boundary(self, weight_pct, expected_hint):
        result = compute_trailing_stop(
            entry=100_000, current=120_000, plan_type="LONGTERM", weight_pct=weight_pct
        )
        assert result["action_hint"] == expected_hint

    def test_review_concentration_note_contains_weight(self):
        result = compute_trailing_stop(
            entry=100_000, current=120_000, plan_type="LONGTERM", weight_pct=45.0
        )
        assert "45.0%" in result["note"]

    def test_old_stop_ignored_for_longterm(self):
        # LONGTERM never uses old_stop — stop stays None
        result = compute_trailing_stop(
            entry=100_000, current=120_000, plan_type="LONGTERM", weight_pct=10.0, old_stop=50_000
        )
        assert result["stop"] is None


# ──────────────────────────────────────────────────────────────────────────────
# SWING — negative gain
# ──────────────────────────────────────────────────────────────────────────────


class TestSwingNegativeGain:
    """SWING when current < entry (position under water)."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_trading_config):
        self.cfg = mock_trading_config

    def test_stop_is_none(self):
        result = compute_trailing_stop(
            entry=100_000, current=90_000, plan_type="SWING", weight_pct=20.0
        )
        assert result["stop"] is None

    def test_stop_type_is_technical(self):
        result = compute_trailing_stop(
            entry=100_000, current=90_000, plan_type="SWING", weight_pct=20.0
        )
        assert result["stop_type"] == "technical"

    def test_action_hint_is_use_levels(self):
        result = compute_trailing_stop(
            entry=100_000, current=90_000, plan_type="SWING", weight_pct=20.0
        )
        assert result["action_hint"] == "USE_LEVELS"

    def test_at_entry_exactly_uses_breakeven_tier(self):
        # gain_pct = 0, which is NOT < 0 → falls into breakeven tier
        result = compute_trailing_stop(
            entry=100_000, current=100_000, plan_type="SWING", weight_pct=20.0
        )
        assert result["stop_type"] == "breakeven"


class TestSwingNegativeGainWithBreakevenFloor:
    """SWI-157 (2026-05-14): underwater SWING with a holding-record
    `breakeven_stop` returns a `breakeven_floor` row instead of `stop=None`.

    Replay: ACV (open SWING, breakeven=44,910 VND, currently 44,500) shipped
    with no morning stop alert because the underwater branch returned None
    and the upsert in pipeline/trailing_stops.py skipped the row."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_trading_config):
        self.cfg = mock_trading_config

    def test_breakeven_floor_returns_int_stop(self):
        result = compute_trailing_stop(
            entry=46_000,
            current=44_500,
            plan_type="SWING",
            weight_pct=10.0,
            breakeven_stop=44_910,
        )
        assert result["stop"] == 44_910

    def test_breakeven_floor_stop_type(self):
        result = compute_trailing_stop(
            entry=46_000,
            current=44_500,
            plan_type="SWING",
            weight_pct=10.0,
            breakeven_stop=44_910,
        )
        assert result["stop_type"] == "breakeven_floor"

    def test_breakeven_floor_action_hint(self):
        result = compute_trailing_stop(
            entry=46_000,
            current=44_500,
            plan_type="SWING",
            weight_pct=10.0,
            breakeven_stop=44_910,
        )
        assert result["action_hint"] == "USE_BREAKEVEN"

    def test_no_breakeven_stop_provided_falls_back_to_technical(self):
        result = compute_trailing_stop(
            entry=100_000, current=90_000, plan_type="SWING", weight_pct=20.0
        )
        assert result["stop"] is None
        assert result["stop_type"] == "technical"

    def test_zero_breakeven_stop_falls_back_to_technical(self):
        result = compute_trailing_stop(
            entry=100_000,
            current=90_000,
            plan_type="SWING",
            weight_pct=20.0,
            breakeven_stop=0,
        )
        assert result["stop"] is None
        assert result["stop_type"] == "technical"

    def test_in_profit_swing_ignores_breakeven_stop(self):
        # gain_pct > 0 → standard breakeven/trailing tier; breakeven_stop arg
        # is only consulted in the underwater branch.
        result = compute_trailing_stop(
            entry=100_000,
            current=105_000,
            plan_type="SWING",
            weight_pct=10.0,
            breakeven_stop=99_000,
        )
        assert result["stop_type"] == "breakeven"
        assert result["stop"] == 100_000  # entry, not breakeven_stop


# ──────────────────────────────────────────────────────────────────────────────
# SWING — breakeven tier  [0, breakeven_gain_pct)
# ──────────────────────────────────────────────────────────────────────────────


class TestSwingBreakevenTier:
    """SWING when 0 <= gain_pct < breakeven_gain_pct (default 10%)."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_trading_config):
        self.cfg = mock_trading_config

    @pytest.mark.parametrize("gain_pct", [0, 1, 5, 9.99])
    def test_stop_equals_entry(self, gain_pct):
        entry = 100_000
        current = entry * (1 + gain_pct / 100)
        result = compute_trailing_stop(
            entry=entry, current=current, plan_type="SWING", weight_pct=20.0
        )
        assert result["stop"] == entry

    def test_stop_type_is_breakeven(self):
        result = compute_trailing_stop(
            entry=100_000, current=105_000, plan_type="SWING", weight_pct=20.0
        )
        assert result["stop_type"] == "breakeven"

    def test_action_hint_is_hold(self):
        result = compute_trailing_stop(
            entry=100_000, current=105_000, plan_type="SWING", weight_pct=20.0
        )
        assert result["action_hint"] == "HOLD"

    def test_boundary_at_exactly_breakeven_gain(self):
        # gain_pct = 10.0 (== breakeven_gain_pct=10.0) → NOT in breakeven tier,
        # falls to 50% trail tier
        entry = 100_000
        current = 110_000  # exactly 10% gain
        result = compute_trailing_stop(
            entry=entry, current=current, plan_type="SWING", weight_pct=20.0
        )
        assert result["stop_type"] == "trailing_50pct"


# ──────────────────────────────────────────────────────────────────────────────
# SWING — 50% trail tier  [breakeven_gain_pct, half_trail_gain_pct)
# ──────────────────────────────────────────────────────────────────────────────


class TestSwingHalfTrailTier:
    """SWING when breakeven_gain_pct <= gain_pct < half_trail_gain_pct (10–15%)."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_trading_config):
        self.cfg = mock_trading_config

    def test_stop_is_midpoint_of_entry_to_current(self):
        # entry=100_000, current=112_000 → gain=12% → stop = 100k + (12k)*0.5 = 106_000
        entry = 100_000
        current = 112_000
        result = compute_trailing_stop(
            entry=entry, current=current, plan_type="SWING", weight_pct=20.0
        )
        expected_stop = round(entry + (current - entry) * 0.5)
        assert result["stop"] == expected_stop

    def test_stop_type_is_trailing_50pct(self):
        result = compute_trailing_stop(
            entry=100_000, current=112_000, plan_type="SWING", weight_pct=20.0
        )
        assert result["stop_type"] == "trailing_50pct"

    def test_action_hint_is_hold(self):
        result = compute_trailing_stop(
            entry=100_000, current=112_000, plan_type="SWING", weight_pct=20.0
        )
        assert result["action_hint"] == "HOLD"

    def test_boundary_exactly_at_half_trail_gain_threshold(self):
        # gain_pct = 15.0 == half_trail_gain_pct → exits into tight tier
        entry = 100_000
        current = 115_000  # exactly 15% gain
        result = compute_trailing_stop(
            entry=entry, current=current, plan_type="SWING", weight_pct=20.0
        )
        assert result["stop_type"] == "trailing_tight"

    @pytest.mark.parametrize(
        "entry,current",
        [
            (100_000, 110_000),  # 10% gain — boundary
            (100_000, 112_000),  # 12% gain — middle
            (50_000, 57_000),  # 14% gain — different scale
        ],
    )
    def test_stop_formula_across_prices(self, entry, current):
        result = compute_trailing_stop(
            entry=entry, current=current, plan_type="SWING", weight_pct=20.0
        )
        expected = round(entry + (current - entry) * 0.5)
        assert result["stop"] == expected


# ──────────────────────────────────────────────────────────────────────────────
# SWING — tight trail tier  (gain >= half_trail_gain_pct)
# ──────────────────────────────────────────────────────────────────────────────


class TestSwingTightTrailTier:
    """SWING when gain_pct >= half_trail_gain_pct (default 15%)."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_trading_config):
        self.cfg = mock_trading_config

    def _expected_tight_stop(self, entry: float, current: float) -> int:
        floor_pct = 95.0 / 100
        lock_pct = 75.0 / 100
        trail = max(current * floor_pct, entry + (current - entry) * lock_pct)
        return round(trail)

    def test_stop_type_is_trailing_tight(self):
        result = compute_trailing_stop(
            entry=100_000, current=120_000, plan_type="SWING", weight_pct=20.0
        )
        assert result["stop_type"] == "trailing_tight"

    def test_action_hint_is_trim_or_trail(self):
        result = compute_trailing_stop(
            entry=100_000, current=120_000, plan_type="SWING", weight_pct=20.0
        )
        assert result["action_hint"] == "TRIM_OR_TRAIL"

    @pytest.mark.parametrize(
        "entry,current",
        [
            (100_000, 120_000),  # 20% gain — floor=114k, lock=115k → lock wins
            (100_000, 140_000),  # 40% gain — floor=133k, lock=130k → floor wins
            (50_000, 65_000),  # 30% gain — floor=61.75k, lock=61.25k → floor wins
        ],
    )
    def test_stop_equals_max_of_floor_and_lock(self, entry, current):
        result = compute_trailing_stop(
            entry=entry, current=current, plan_type="SWING", weight_pct=20.0
        )
        expected = self._expected_tight_stop(entry, current)
        assert result["stop"] == expected

    def test_current_floor_dominates_when_large_gain(self):
        # With very large gain, current*0.95 > entry + gain*0.75
        # entry=100k, current=200k → floor=190k, lock=100k+75k=175k → floor wins
        entry = 100_000
        current = 200_000
        result = compute_trailing_stop(
            entry=entry, current=current, plan_type="SWING", weight_pct=20.0
        )
        assert result["stop"] == round(current * 0.95)

    def test_gain_lock_dominates_when_small_tight_gain(self):
        # entry=100k, current=116k (16% gain)
        # floor=110.2k, lock=100k+12k=112k → lock wins
        entry = 100_000
        current = 116_000
        result = compute_trailing_stop(
            entry=entry, current=current, plan_type="SWING", weight_pct=20.0
        )
        expected_lock = round(entry + (current - entry) * 0.75)
        expected_floor = round(current * 0.95)
        assert result["stop"] == max(expected_lock, expected_floor)


# ──────────────────────────────────────────────────────────────────────────────
# Ratchet behavior — stop never moves down
# ──────────────────────────────────────────────────────────────────────────────


class TestRatchetBehavior:
    """old_stop should never be overridden downward."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_trading_config):
        self.cfg = mock_trading_config

    def test_half_trail_ratchets_up_to_old_stop(self):
        # gain=12% → computed stop = 106k, old_stop=108k → should keep 108k
        entry = 100_000
        current = 112_000
        old_stop = 108_000
        result = compute_trailing_stop(
            entry=entry, current=current, plan_type="SWING", weight_pct=20.0, old_stop=old_stop
        )
        assert result["stop"] == old_stop

    def test_half_trail_uses_computed_when_higher_than_old_stop(self):
        # gain=12% → computed=106k, old_stop=104k → computed wins
        entry = 100_000
        current = 112_000
        old_stop = 104_000
        result = compute_trailing_stop(
            entry=entry, current=current, plan_type="SWING", weight_pct=20.0, old_stop=old_stop
        )
        expected = round(entry + (current - entry) * 0.5)
        assert result["stop"] == expected
        assert result["stop"] > old_stop

    def test_tight_trail_ratchets_up_to_old_stop(self):
        # gain=20% → computed=115k, old_stop=117k → keeps 117k
        entry = 100_000
        current = 120_000
        old_stop = 117_000
        result = compute_trailing_stop(
            entry=entry, current=current, plan_type="SWING", weight_pct=20.0, old_stop=old_stop
        )
        assert result["stop"] == old_stop

    def test_tight_trail_uses_computed_when_higher_than_old_stop(self):
        # gain=20% → computed stop > old_stop=110k → computed wins
        entry = 100_000
        current = 120_000
        old_stop = 110_000
        result = compute_trailing_stop(
            entry=entry, current=current, plan_type="SWING", weight_pct=20.0, old_stop=old_stop
        )
        floor_pct = 95.0 / 100
        lock_pct = 75.0 / 100
        expected = round(max(current * floor_pct, entry + (current - entry) * lock_pct))
        assert result["stop"] == expected
        assert result["stop"] > old_stop

    def test_no_ratchet_when_old_stop_none(self):
        # Baseline: old_stop=None should not raise and computes normally
        entry = 100_000
        current = 112_000
        result_no_old = compute_trailing_stop(
            entry=entry, current=current, plan_type="SWING", weight_pct=20.0, old_stop=None
        )
        result_with_old = compute_trailing_stop(
            entry=entry, current=current, plan_type="SWING", weight_pct=20.0, old_stop=100_000
        )
        # old_stop=100k < computed → computed wins → both should be equal
        assert result_no_old["stop"] == result_with_old["stop"]

    def test_breakeven_tier_no_ratchet_applied(self):
        # Breakeven tier always returns entry regardless of old_stop
        # (ratchet is not applied in this tier by design)
        entry = 100_000
        current = 105_000
        old_stop = 99_000  # lower than entry — does not raise stop
        result = compute_trailing_stop(
            entry=entry, current=current, plan_type="SWING", weight_pct=20.0, old_stop=old_stop
        )
        assert result["stop"] == entry  # always entry, old_stop not used


# ──────────────────────────────────────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases: zero entry, zero weight, large positions."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_trading_config):
        self.cfg = mock_trading_config

    def test_zero_entry_gain_pct_treated_as_zero(self):
        # entry=0 → gain_pct=0 → falls into breakeven tier (0 < 10)
        result = compute_trailing_stop(entry=0, current=50_000, plan_type="SWING", weight_pct=20.0)
        # gain_pct=0, which is not < 0 → breakeven tier → stop=entry=0
        assert result["stop_type"] == "breakeven"
        assert result["stop"] == 0

    def test_zero_weight_pct_longterm_stays_hold(self):
        result = compute_trailing_stop(
            entry=100_000, current=120_000, plan_type="LONGTERM", weight_pct=0.0
        )
        assert result["action_hint"] == "HOLD"

    def test_very_large_gain_swing(self):
        # 100% gain — should be in tight tier, no exception
        entry = 100_000
        current = 200_000
        result = compute_trailing_stop(
            entry=entry, current=current, plan_type="SWING", weight_pct=20.0
        )
        assert result["stop_type"] == "trailing_tight"
        assert result["stop"] is not None
        assert result["stop"] > entry

    def test_swing_result_has_expected_keys(self):
        required_keys = {"stop", "stop_type", "action_hint"}
        result = compute_trailing_stop(
            entry=100_000, current=112_000, plan_type="SWING", weight_pct=20.0
        )
        assert required_keys.issubset(result.keys())

    def test_longterm_result_has_expected_keys(self):
        required_keys = {
            "stop",
            "stop_type",
            "action_hint",
            "catastrophic_stop",
            "thesis_checkpoints",
        }
        result = compute_trailing_stop(
            entry=100_000, current=120_000, plan_type="LONGTERM", weight_pct=10.0
        )
        assert required_keys.issubset(result.keys())
