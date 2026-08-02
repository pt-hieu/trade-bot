"""Plan shape canonical values + downstream subset invariants (SWI-269)."""

from __future__ import annotations

from shared.rules.plan_shape import PLAN_SHAPE_VALUES


def test_plan_shape_values_canonical() -> None:
    assert {
        "BREAKOUT",
        "PULLBACK",
        "TREND_PULLBACK",
        "BOUNCE",
        "MEAN_REVERT",
        "NONE",
    } == PLAN_SHAPE_VALUES


def test_strategy_to_shape_subset() -> None:
    from pipeline.recommendation_builder import _STRATEGY_TO_SHAPE

    assert set(_STRATEGY_TO_SHAPE.values()) <= PLAN_SHAPE_VALUES


def test_price_below_shapes_subset() -> None:
    from pipeline.conditional_alerts import _PRICE_BELOW_SHAPES

    assert _PRICE_BELOW_SHAPES <= PLAN_SHAPE_VALUES
