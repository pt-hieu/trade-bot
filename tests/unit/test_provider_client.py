"""Fix A regression guard (SWI-375/378): disable the OpenAI SDK's hidden double-retry.

The OpenAI SDK defaults to `max_retries=2`, so a stalled/timed-out hop is silently
retried twice INSIDE one `request()` call (~2xN s) before HopTimingModel's per-hop
wall and RetryModel/FallbackModel — which own the retry budget by design — ever see
it. `_get_provider` must build the AsyncOpenAI client with `max_retries=0` so a stall
surfaces promptly to those guards.
"""

from __future__ import annotations

import pytest


def _fresh_resolvers(monkeypatch):
    """Import resolvers with a clean provider cache and a fake API key."""
    from agents.model import resolvers

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    resolvers._provider_cache.clear()
    return resolvers


def test_provider_client_disables_sdk_retries(monkeypatch):
    resolvers = _fresh_resolvers(monkeypatch)

    provider = resolvers._get_provider()

    assert provider.client.max_retries == 0, (
        "AsyncOpenAI client must be built with max_retries=0 so a stalled hop "
        "surfaces to the per-hop wall / FallbackModel instead of being silently "
        "retried twice inside one request()."
    )


def test_provider_client_preserves_attribution_headers(monkeypatch):
    """The `openai_client` overload drops OpenRouter attribution headers; we set them
    ourselves from the same env vars the prior http_client construction read, so the
    switch to a pre-built client introduces no attribution regression.
    """
    resolvers = _fresh_resolvers(monkeypatch)
    monkeypatch.setenv("OPENROUTER_APP_URL", "https://swingy.example")
    monkeypatch.setenv("OPENROUTER_APP_TITLE", "Swingy")

    provider = resolvers._get_provider()
    headers = provider.client.default_headers

    assert headers.get("HTTP-Referer") == "https://swingy.example"
    assert headers.get("X-Title") == "Swingy"


def test_provider_missing_api_key_raises(monkeypatch):
    """`_get_provider` owns the missing-key error contract explicitly (it builds the
    client itself now), so a misconfigured deploy fails loudly with a clear message
    rather than an opaque SDK auth error downstream.
    """
    from agents.model import resolvers

    resolvers._provider_cache.clear()
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        resolvers._get_provider()
