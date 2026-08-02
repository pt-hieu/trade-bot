"""Tests for shared.llm.call_llm_with_json_parse helper.

Covers the caller shapes we migrated to it:
- articles_intl / articles_vn: max_attempts=2, backoff_seconds=5
- sector_rotation: max_attempts=1 (default, no retry)
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from shared.llm import call_llm_with_json_parse

SCHEMA: dict = {"type": "json_schema", "json_schema": {"name": "x", "schema": {}}}


def _fixed(responses: list[str]):
    """Build a side_effect callable that returns queued responses in order."""
    queue = list(responses)

    def _call(*args, **kwargs):
        return queue.pop(0)

    return _call


def test_success_on_first_attempt_returns_parsed_dict():
    with patch(
        "shared.llm.call_llm",
        side_effect=_fixed(['{"scores": [{"index": 0, "score": 8}]}']),
    ):
        result = call_llm_with_json_parse("sys", "user", SCHEMA)
    assert result == {"scores": [{"index": 0, "score": 8}]}


def test_default_single_attempt_raises_on_first_failure():
    with (
        patch("shared.llm.call_llm", side_effect=RuntimeError("boom")),
        pytest.raises(RuntimeError, match="boom"),
    ):
        call_llm_with_json_parse("sys", "user", SCHEMA)


def test_max_attempts_two_retries_after_transient_failure():
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return '{"ok": true}'

    with (
        patch("shared.llm.call_llm", side_effect=flaky),
        patch("shared.llm.time.sleep") as sleep_mock,
    ):
        result = call_llm_with_json_parse(
            "sys",
            "user",
            SCHEMA,
            max_attempts=2,
            backoff_seconds=5,
        )
    assert result == {"ok": True}
    assert calls["n"] == 2
    sleep_mock.assert_called_once_with(5)


def test_max_attempts_exhausted_raises_last_error():
    with (
        patch("shared.llm.call_llm", side_effect=RuntimeError("persistent")),
        patch("shared.llm.time.sleep"),
        pytest.raises(RuntimeError, match="persistent"),
    ):
        call_llm_with_json_parse("sys", "user", SCHEMA, max_attempts=2, backoff_seconds=5)


def test_on_attempt_error_fires_per_failed_attempt():
    events: list[tuple[int, str]] = []

    def record(attempt: int, error: Exception) -> None:
        events.append((attempt, str(error)))

    with (
        patch("shared.llm.call_llm", side_effect=RuntimeError("flake")),
        patch("shared.llm.time.sleep"),
        pytest.raises(RuntimeError),
    ):
        call_llm_with_json_parse(
            "sys",
            "user",
            SCHEMA,
            max_attempts=3,
            backoff_seconds=1,
            on_attempt_error=record,
        )
    assert [index for index, _ in events] == [0, 1, 2]


def test_decode_fallback_rescues_multi_object_response():
    # Model emits two JSON objects joined by newline; fallback keeps first line.
    multi = '{"articles": [{"index": 0, "tickers": ["FPT"]}]}\n{"articles": []}'

    def fallback(response: str) -> dict:
        first_line = response.strip().split("\n", 1)[0]
        return json.loads(first_line)

    with patch("shared.llm.call_llm", side_effect=_fixed([multi])):
        result = call_llm_with_json_parse("sys", "user", SCHEMA, decode_fallback=fallback)
    assert result == {"articles": [{"index": 0, "tickers": ["FPT"]}]}


def test_decode_fallback_absent_raises_json_decode_error():
    with (
        patch("shared.llm.call_llm", side_effect=_fixed(["not-json"])),
        pytest.raises(json.JSONDecodeError),
    ):
        call_llm_with_json_parse("sys", "user", SCHEMA)


def test_non_dict_parsed_result_raises_valueerror():
    # Model returns valid JSON but a list — caller contract requires dict.
    with (
        patch("shared.llm.call_llm", side_effect=_fixed(["[1, 2, 3]"])),
        pytest.raises(ValueError, match="expected dict"),
    ):
        call_llm_with_json_parse("sys", "user", SCHEMA)


def test_backoff_not_applied_after_final_attempt():
    with (
        patch("shared.llm.call_llm", side_effect=RuntimeError("x")),
        patch("shared.llm.time.sleep") as sleep_mock,
        pytest.raises(RuntimeError),
    ):
        call_llm_with_json_parse("sys", "user", SCHEMA, max_attempts=2, backoff_seconds=5)
    # One sleep between the 2 attempts, not after the final one.
    assert sleep_mock.call_count == 1
