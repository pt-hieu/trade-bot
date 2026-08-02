"""Shared httpx client + retry/headers/lifecycle for the vnstock API."""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

VNSTOCK_API_URL = os.environ.get("VNSTOCK_API_URL", "").strip()
VNSTOCK_API_KEY = os.environ.get("VNSTOCK_API_KEY", "").strip()

# Retry config for transient server errors
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # seconds — exponential: 2, 4, 8
RETRYABLE_STATUS_CODES = {500, 502, 503, 504}

# Lazy singleton client — created on first use, reuses connections
_client: httpx.AsyncClient | None = None


def _get_headers() -> dict:
    """Get headers with API key."""
    headers = {}
    if VNSTOCK_API_KEY:
        headers["X-API-Key"] = VNSTOCK_API_KEY
    return headers


def _check_configured():
    """Raise error if API is not configured."""
    if not VNSTOCK_API_URL:
        raise RuntimeError("VNSTOCK_API_URL environment variable not set")


def _get_client() -> httpx.AsyncClient:
    """Return module-level shared HTTP client (lazy init)."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(headers=_get_headers(), timeout=180.0)
    return _client


async def close_client():
    """Close the shared HTTP client. Call at end of pipeline."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


async def _request_with_retry(
    method: str,
    url: str,
    *,
    timeout: float = 30.0,
    max_retries: int = MAX_RETRIES,
    **kwargs: object,
) -> httpx.Response:
    """HTTP request with exponential backoff on transient server errors.

    Args:
        method: HTTP method (get, post, etc.)
        url: Full URL to request.
        timeout: Request timeout in seconds.
        max_retries: Max retry attempts for 5xx errors.
        **kwargs: Passed to httpx client request method.

    Returns:
        httpx.Response with successful status code.

    Raises:
        httpx.HTTPStatusError: After all retries exhausted, or on non-retryable error.
    """
    client = _get_client()
    last_error: httpx.HTTPStatusError | None = None

    for attempt in range(max_retries):
        response = await getattr(client, method)(
            url, timeout=timeout, headers=_get_headers(), **kwargs
        )
        if response.status_code not in RETRYABLE_STATUS_CODES:
            response.raise_for_status()
            return response

        last_error = httpx.HTTPStatusError(
            f"Server error '{response.status_code}' on attempt {attempt + 1}/{max_retries}",
            request=response.request,
            response=response,
        )
        delay = RETRY_BACKOFF_BASE * (2**attempt)
        logger.warning(
            "%s returned %d (attempt %d/%d), retrying in %.0fs",
            url.split("?")[0].split("/")[-1],
            response.status_code,
            attempt + 1,
            max_retries,
            delay,
        )
        await asyncio.sleep(delay)

    raise last_error  # type: ignore[misc]


async def check_health() -> dict:
    """Check if the API server is healthy."""
    _check_configured()

    client = _get_client()
    resp = await client.get(
        f"{VNSTOCK_API_URL}/health",
        headers=_get_headers(),
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()
