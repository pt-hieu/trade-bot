# ruff: noqa: F821
# Template uses placeholder identifiers (function_under_test, expected_value,
# async_function_under_test) that are filled in when the template is copied
# into a real test module. Suppress F821 here so the template itself lints.
"""
Tests for <module_name>.

Run: uv run pytest tests/unit/test_<module_name>.py -v --tb=short
"""

from unittest.mock import AsyncMock, patch

import pytest

# --- Pure function tests (no mocking needed) ---


class TestPureFunctionName:
    """Tests for <function_name>."""

    def test_basic_case(self):
        # Arrange
        input_val = 100_000

        # Act
        result = function_under_test(input_val)

        # Assert
        assert result == expected_value

    @pytest.mark.parametrize(
        "input_val,expected",
        [
            (0, "EDGE_CASE_1"),
            (5_000_000, "BOUNDARY"),  # exact boundary
            (5_000_001, "ABOVE"),  # just above
            (None, "NONE_HANDLING"),
        ],
    )
    def test_multiple_cases(self, input_val, expected):
        assert function_under_test(input_val) == expected


# --- Async tests with mocking ---


class TestAsyncFunction:
    """Tests for <async_function>."""

    @pytest.fixture
    def mock_data_source(self):
        with patch(
            "agents.tools.module.get_data_async",  # patch where it's USED
            new_callable=AsyncMock,
        ) as mock:
            mock.return_value = {"ticker": "FPT", "close": 135000}
            yield mock

    @pytest.mark.asyncio
    async def test_returns_expected_shape(self, mock_data_source):
        result = await async_function_under_test("FPT")

        assert "ticker" in result
        assert isinstance(result["close"], (int, float))  # native types, not numpy

    @pytest.mark.asyncio
    async def test_handles_empty_data(self, mock_data_source):
        mock_data_source.return_value = {}

        result = await async_function_under_test("INVALID")

        assert result is None or result == {}


# --- Edge cases checklist ---
# Always test: None, [], {}, 0, "", exact boundaries, just above/below
