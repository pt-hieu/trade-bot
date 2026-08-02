"""Unit tests for the broker validation-error classifier.

Covers the three pydantic error classes that surface in production logs:
``missing`` (missing required arg), ``unexpected_keyword_argument``, and
``literal_error``. Each class must produce a tailored hint distinct from the
others — a single shared hint is what mis-coached the 2026-04-28
positions_thesis loop into burning its request_limit.
"""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import ValidationError, validate_call

from agents.tools.broker.error_hints import (
    LITERAL_VALIDATION_HINT,
    classify_validation_error,
)


@validate_call
def _missing_arg_tool(tickers: list[str]) -> str:
    return ",".join(tickers)


@validate_call
def _zero_arg_tool() -> str:
    return "ok"


@validate_call
def _literal_tool(query: Literal["summary", "calibration"]) -> str:
    return query


@validate_call
def _list_arg_tool(tickers: list[str]) -> str:
    return ",".join(tickers)


def _force_validation_error(callable_, **kwargs) -> ValidationError:
    """Trigger and return the underlying ``ValidationError`` for assertions."""
    try:
        callable_(**kwargs)
    except ValidationError as exc:
        return exc
    raise AssertionError("Expected ValidationError but call succeeded")


class TestClassifyValidationError:
    def test_missing_argument_emits_arg_specific_hint(self):
        exc = _force_validation_error(_missing_arg_tool)
        result = classify_validation_error("portfolio.get_thesis", exc)
        assert result["error_type"] in {"missing", "missing_argument"}
        assert "tickers" in result["hint"]
        assert "args" in result["hint"]
        assert result["hint"] != LITERAL_VALIDATION_HINT
        assert "portfolio.get_thesis" in result["hint"]

    def test_unexpected_keyword_emits_kwarg_specific_hint(self):
        exc = _force_validation_error(_zero_arg_tool, tickers=["FPT"])
        result = classify_validation_error("enrichment.get_block_trades", exc)
        assert result["error_type"] == "unexpected_keyword_argument"
        assert "tickers" in result["hint"]
        assert "does not accept" in result["hint"]
        assert result["hint"] != LITERAL_VALIDATION_HINT

    def test_literal_error_keeps_legacy_hint(self):
        exc = _force_validation_error(_literal_tool, query="freeform")
        result = classify_validation_error("portfolio.get_learnings", exc)
        assert result["error_type"] in {"literal_error", "literal"}
        assert result["hint"] == LITERAL_VALIDATION_HINT

    def test_each_error_class_yields_a_distinct_hint(self):
        missing = classify_validation_error(
            "portfolio.get_thesis", _force_validation_error(_missing_arg_tool)
        )
        unexpected = classify_validation_error(
            "enrichment.get_block_trades",
            _force_validation_error(_zero_arg_tool, tickers=["FPT"]),
        )
        literal = classify_validation_error(
            "portfolio.get_learnings",
            _force_validation_error(_literal_tool, query="freeform"),
        )
        hints = {missing["hint"], unexpected["hint"], literal["hint"]}
        assert len(hints) == 3, "Each error class must surface a distinct hint"

    def test_payload_carries_pydantic_error_text(self):
        exc = _force_validation_error(_missing_arg_tool)
        result = classify_validation_error("portfolio.get_thesis", exc)
        assert "tickers" in result["pydantic_error"]
        assert result["error"] == "Invalid args for portfolio.get_thesis"


@pytest.mark.parametrize(
    "tool_name,arg_name",
    [
        ("portfolio.get_thesis", "tickers"),
        ("fundamental.get_full_analysis", "tickers"),
        ("technical.get_technicals", "tickers"),
    ],
)
def test_missing_arg_hint_calls_out_specific_arg_name(tool_name: str, arg_name: str) -> None:
    exc = _force_validation_error(_missing_arg_tool)
    result = classify_validation_error(tool_name, exc)
    assert tool_name in result["hint"]
    assert arg_name in result["hint"]


class TestListTypeHint:
    """SWI-NN (2026-05-14): coach the JSON-stringified-array shape failure.

    Replay: today's morning scan saw 18× narrative.get_active rejections from
    args={"tickers": "[\"VHM\",\"TCB\"]"} (the model emitted a JSON string of
    a list instead of a real list literal). SWI-180 user decision: no
    BeforeValidator coercer — sharpen the retry hint instead.
    """

    def test_stringified_array_returns_shape_hint(self):
        exc = _force_validation_error(_list_arg_tool, tickers='["VHM","TCB"]')
        result = classify_validation_error("narrative.get_active", exc)
        assert result["error_type"] == "list_type"
        assert 'tickers=["VHM"' in result["hint"]
        assert "JSON string" in result["hint"]
        assert "native Python types" in result["hint"]

    def test_list_type_generic_when_input_is_scalar(self):
        exc = _force_validation_error(_list_arg_tool, tickers=123)
        result = classify_validation_error("narrative.get_active", exc)
        assert result["error_type"] == "list_type"
        # Generic branch — no JSON-string mention because input is a number.
        assert "JSON string" not in result["hint"]
        assert "tickers" in result["hint"]
        assert "list" in result["hint"]

    def test_error_type_field_preserves_list_type(self):
        """The breaker debounces on (tool, error_type) — error_type must be
        the exact pydantic key so the same shape failure on the same tool
        trips the breaker after 3 retries."""
        exc = _force_validation_error(_list_arg_tool, tickers='["VHM"]')
        result = classify_validation_error("narrative.get_active", exc)
        assert result["error_type"] == "list_type"
