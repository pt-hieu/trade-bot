"""Tests for shared.rules.plan_shape.coerce_plan_shape_for_check (SWI-NN).

Mirrors the Postgres CHECK `daily_recs_plan_shape_action_chk` (migration 342):

    plan_shape IS NULL OR plan_shape = 'NONE' OR
    (action::text IN ('WATCH','WAIT') AND trigger_price_vnd IS NOT NULL)

Strict mode raises so non-prod (CI/dev) catches producer bugs at the source;
non-strict mode coerces to 'NONE' + log_warn so production stays smooth even
if a new producer slips an invariant violation.
"""

from __future__ import annotations

import pytest

from shared.rules.plan_shape import coerce_plan_shape_for_check


class TestCoerceFourCorners:
    """All 4 (action × trigger) corners under default (non-strict, prod-like) mode."""

    @pytest.mark.parametrize(
        "plan_shape,action,trigger_vnd,expected",
        [
            # WATCH + trigger present → keep shape
            ("BREAKOUT", "WATCH", 50000, "BREAKOUT"),
            ("PULLBACK", "WAIT", 50000, "PULLBACK"),
            # WATCH + missing trigger → coerce
            ("BREAKOUT", "WATCH", None, "NONE"),
            ("PULLBACK", "WAIT", 0, "NONE"),
            # BUY + trigger present → coerce (action not WATCH/WAIT)
            ("BREAKOUT", "BUY", 50000, "NONE"),
            ("PULLBACK", "ADD", 50000, "NONE"),
            # BUY + missing trigger → coerce
            ("BREAKOUT", "BUY", None, "NONE"),
            # NONE input is a no-op regardless of action
            ("NONE", "BUY", None, "NONE"),
            ("NONE", "WATCH", 50000, "NONE"),
            # None input → None (NULL allowed by CHECK)
            (None, "BUY", None, None),
            (None, "WATCH", 50000, None),
        ],
    )
    def test_corners_lenient_mode(self, plan_shape, action, trigger_vnd, expected):
        result = coerce_plan_shape_for_check(plan_shape, action, trigger_vnd, strict=False)
        assert result == expected


class TestStrictModeRaises:
    """Non-prod / CI must raise on producer-side invariant violations."""

    def test_strict_raises_on_buy_with_shape(self):
        with pytest.raises(AssertionError):
            coerce_plan_shape_for_check("BREAKOUT", "BUY", None, strict=True)

    def test_strict_raises_on_watch_without_trigger(self):
        with pytest.raises(AssertionError):
            coerce_plan_shape_for_check("BREAKOUT", "WATCH", None, strict=True)

    def test_strict_passes_on_valid_watch(self):
        result = coerce_plan_shape_for_check("BREAKOUT", "WATCH", 50000, strict=True)
        assert result == "BREAKOUT"

    def test_strict_passes_on_none_shape(self):
        result = coerce_plan_shape_for_check("NONE", "BUY", None, strict=True)
        assert result == "NONE"


class TestEnvGatedDefault:
    """strict=None reads SWINGY_ENV: production → coerce, else → raise."""

    def test_default_in_production_coerces(self, monkeypatch):
        monkeypatch.setenv("SWINGY_ENV", "production")
        result = coerce_plan_shape_for_check("BREAKOUT", "BUY", None)
        assert result == "NONE"

    def test_default_in_development_raises(self, monkeypatch):
        monkeypatch.setenv("SWINGY_ENV", "development")
        with pytest.raises(AssertionError):
            coerce_plan_shape_for_check("BREAKOUT", "BUY", None)

    def test_default_unset_raises(self, monkeypatch):
        monkeypatch.delenv("SWINGY_ENV", raising=False)
        with pytest.raises(AssertionError):
            coerce_plan_shape_for_check("BREAKOUT", "BUY", None)


class TestCaseNormalization:
    """Lowercase input still satisfies the CHECK after coercion."""

    def test_lowercase_action_treated_as_uppercase(self):
        result = coerce_plan_shape_for_check("BREAKOUT", "watch", 50000, strict=False)
        assert result == "BREAKOUT"

    def test_lowercase_shape_normalized(self):
        # Shape uppercase happens at builder; rule still treats provided value
        # as authoritative — case insensitivity is the caller's job. Document
        # this here so a future change does not silently widen the contract.
        result = coerce_plan_shape_for_check("none", "BUY", None, strict=False)
        assert result == "NONE"
