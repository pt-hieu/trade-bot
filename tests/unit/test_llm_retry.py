"""Tests for call_llm retry logic."""

from unittest.mock import MagicMock, patch

import pytest
from openai import InternalServerError


class TestCallLlmRetry:
    """Verify call_llm retries transient errors with backoff."""

    @patch("shared.llm.time.sleep")
    @patch("shared.llm._get_openai_client")
    @patch("shared.llm.is_dry_run", return_value=False)
    def test_succeeds_after_transient_503(self, _dry, mock_client_fn, mock_sleep):
        from shared.llm import call_llm

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        error_response = MagicMock()
        error_response.status_code = 503
        error_response.json.return_value = {"error": {"message": "Service unavailable"}}
        error_response.headers = {}
        error_response.text = "Service unavailable"

        successful_response = MagicMock()
        successful_response.choices = [MagicMock(message=MagicMock(content="ok"))]

        mock_client.chat.completions.create.side_effect = [
            InternalServerError("503", response=error_response, body=None),
            InternalServerError("503", response=error_response, body=None),
            successful_response,
        ]

        result = call_llm("system", "user")
        assert result == "ok"
        assert mock_client.chat.completions.create.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(2)
        mock_sleep.assert_any_call(5)

    @patch("shared.llm.time.sleep")
    @patch("shared.llm._get_openai_client")
    @patch("shared.llm.is_dry_run", return_value=False)
    def test_raises_after_all_retries_exhausted(self, _dry, mock_client_fn, mock_sleep):
        from shared.llm import call_llm

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        error_response = MagicMock()
        error_response.status_code = 503
        error_response.json.return_value = {"error": {"message": "Service unavailable"}}
        error_response.headers = {}
        error_response.text = "Service unavailable"

        mock_client.chat.completions.create.side_effect = InternalServerError(
            "503", response=error_response, body=None
        )

        with pytest.raises(InternalServerError):
            call_llm("system", "user")

        assert mock_client.chat.completions.create.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("shared.llm.time.sleep")
    @patch("shared.llm._get_openai_client")
    @patch("shared.llm.is_dry_run", return_value=False)
    def test_no_retry_on_non_transient_error(self, _dry, mock_client_fn, mock_sleep):
        from openai import BadRequestError

        from shared.llm import call_llm

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        error_response = MagicMock()
        error_response.status_code = 400
        error_response.json.return_value = {"error": {"message": "Bad request"}}
        error_response.headers = {}
        error_response.text = "Bad request"

        mock_client.chat.completions.create.side_effect = BadRequestError(
            "400", response=error_response, body=None
        )

        with pytest.raises(BadRequestError):
            call_llm("system", "user")

        assert mock_client.chat.completions.create.call_count == 1
        assert mock_sleep.call_count == 0

    @patch("shared.llm._get_openai_client")
    @patch("shared.llm.is_dry_run", return_value=False)
    def test_succeeds_on_first_attempt(self, _dry, mock_client_fn):
        from shared.llm import call_llm

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        successful_response = MagicMock()
        successful_response.choices = [MagicMock(message=MagicMock(content="result"))]
        mock_client.chat.completions.create.return_value = successful_response

        result = call_llm("system", "user")
        assert result == "result"
        assert mock_client.chat.completions.create.call_count == 1
