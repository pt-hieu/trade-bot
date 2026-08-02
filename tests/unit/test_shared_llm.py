"""Tests for shared.llm module-level client config and timeout handling."""

from unittest.mock import MagicMock, patch

import pytest
from openai import APITimeoutError


class TestOpenAIClientTimeout:
    """Verify the shared OpenAI client is constructed with a bounded HTTP timeout."""

    def test_http_timeout_constant_is_60s(self):
        import shared.llm as llm_module

        assert llm_module._HTTP_TIMEOUT_SECONDS == 60.0

    def test_client_constructor_receives_timeout(self, monkeypatch):
        import shared.llm as llm_module

        # Reset singleton so the next call rebuilds with our patched OpenAI
        monkeypatch.setattr(llm_module, "_openai_client", None)
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        captured: dict = {}

        def fake_openai(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        monkeypatch.setattr(llm_module, "OpenAI", fake_openai)

        llm_module._get_openai_client()

        assert captured.get("timeout") == 60.0
        assert captured.get("api_key") == "test-key"

    @patch("shared.llm.time.sleep")
    @patch("shared.llm._get_openai_client")
    @patch("shared.llm.is_dry_run", return_value=False)
    def test_api_timeout_error_triggers_retry_loop(self, _dry, mock_client_fn, mock_sleep):
        """APITimeoutError (raised when HTTP timeout fires) must hit the existing retry loop."""
        from shared.llm import _RETRY_DELAYS, call_llm

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        successful_response = MagicMock()
        successful_response.choices = [MagicMock(message=MagicMock(content="ok-after-timeout"))]

        fake_request = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            APITimeoutError(request=fake_request),
            APITimeoutError(request=fake_request),
            successful_response,
        ]

        result = call_llm("system", "user")
        assert result == "ok-after-timeout"
        assert mock_client.chat.completions.create.call_count == 3
        # Two retries with the first two delays
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(_RETRY_DELAYS[0])
        mock_sleep.assert_any_call(_RETRY_DELAYS[1])

    @patch("shared.llm.time.sleep")
    @patch("shared.llm._get_openai_client")
    @patch("shared.llm.is_dry_run", return_value=False)
    def test_api_timeout_error_exhausts_and_raises(self, _dry, mock_client_fn, mock_sleep):
        from shared.llm import call_llm

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        fake_request = MagicMock()
        mock_client.chat.completions.create.side_effect = APITimeoutError(request=fake_request)

        with pytest.raises(APITimeoutError):
            call_llm("system", "user")

        assert mock_client.chat.completions.create.call_count == 3
