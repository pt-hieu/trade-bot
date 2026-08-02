"""Value-parity + emit-presence tests for normalize_vnd_price (SWI-206)."""

from __future__ import annotations

import pytest

from shared.rules.vnd_price_clamp import normalize_vnd_price


def test_in_range_passthrough(capture_emits: list[dict]) -> None:
    assert normalize_vnd_price(44910, "stop at 44,910", agent="midday_override") == 44910
    assert capture_emits == []


def test_unit_shift_correction(capture_emits: list[dict]) -> None:
    assert normalize_vnd_price(44.91, "stop at 44,910", agent="midday_override") == 44910
    coerced = [e for e in capture_emits if e["outcome"] == "coerced"]
    assert len(coerced) == 1
    assert coerced[0]["reason"] == "unit_shift_x1000"
    assert coerced[0]["boundary"] == "validator"


def test_above_max_raises(capture_emits: list[dict]) -> None:
    with pytest.raises(ValueError):
        normalize_vnd_price(2_000_000, "stop at 2000000", agent="midday_override")
    rejected = [e for e in capture_emits if e["outcome"] == "rejected"]
    assert any(e["reason"] == "above_max" for e in rejected)


def test_sub_1000_no_reason_raises(capture_emits: list[dict]) -> None:
    with pytest.raises(ValueError):
        normalize_vnd_price(44.91, "no price here", agent="midday_override")
    assert any(e["reason"] == "sub_1000_unjustified" for e in capture_emits)


def test_non_finite_raises(capture_emits: list[dict]) -> None:
    with pytest.raises(ValueError):
        normalize_vnd_price(float("inf"), "stop at 44,910", agent="midday_override")
    assert any(e["reason"] == "non_finite" for e in capture_emits)


def test_non_positive_raises(capture_emits: list[dict]) -> None:
    with pytest.raises(ValueError):
        normalize_vnd_price(-100, "stop", agent="midday_override")
    assert any(e["reason"] == "non_positive" for e in capture_emits)


def test_persistence_boundary_tag(capture_emits: list[dict]) -> None:
    normalize_vnd_price(44.91, "stop at 44,910", boundary="persistence", agent="midday_override")
    coerced = [e for e in capture_emits if e["outcome"] == "coerced"]
    assert coerced[0]["boundary"] == "persistence"


def test_none_passthrough(capture_emits: list[dict]) -> None:
    assert normalize_vnd_price(None, "stop", agent="midday_override") is None
    assert capture_emits == []
