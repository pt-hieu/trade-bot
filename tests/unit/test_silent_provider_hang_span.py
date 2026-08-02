"""Tests for silent-provider-hang span emission (MON-2026-04-13-002).

The span helper replaces a bare `logger.error` line that pipeline-review
could only catch via a tokens=None/None heuristic. We verify the helper
is structurally correct in both logfire-unconfigured (no-op span) and
logfire-configured modes, and passes through the expected attributes.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from shared import observability
from shared.observability import emit_silent_provider_hang_span


def test_no_op_when_logfire_unconfigured(monkeypatch):
    """With no LOGFIRE_TOKEN, the helper must not crash and must still
    call logger.error so the incident leaves a log-line trail."""
    monkeypatch.setattr(observability, "_logfire", None)
    logger = MagicMock(spec=logging.Logger)

    emit_silent_provider_hang_span(
        agent="sector_aggregator",
        wall_s=120,
        exception_type="TimeoutError",
        logger=logger,
        provider="z-ai",
        downstream_provider=None,
        sector="banking",
    )

    logger.error.assert_called_once()
    args, _ = logger.error.call_args
    assert "SILENT_PROVIDER_HANG" in args[0]
    assert "sector_aggregator" in args


def test_emits_span_when_logfire_configured(monkeypatch):
    """When logfire is configured, the helper opens a span named
    'silent_provider_hang' with the agent + hang_type + wall_s attrs."""
    fake_logfire = MagicMock()
    fake_span = MagicMock()
    fake_span.__enter__ = MagicMock(return_value=fake_span)
    fake_span.__exit__ = MagicMock(return_value=None)
    fake_logfire.span.return_value = fake_span

    monkeypatch.setattr(observability, "_logfire", fake_logfire)

    logger = MagicMock(spec=logging.Logger)
    emit_silent_provider_hang_span(
        agent="positions_aggregator",
        wall_s=120,
        exception_type="TimeoutError",
        logger=logger,
        provider=None,
        downstream_provider=None,
    )

    fake_logfire.span.assert_called_once()
    call_kwargs = fake_logfire.span.call_args.kwargs
    assert fake_logfire.span.call_args.args[0] == "silent_provider_hang"
    assert call_kwargs["agent"] == "positions_aggregator"
    assert call_kwargs["hang_type"] == "silent_provider"
    assert call_kwargs["wall_s"] == 120
    assert call_kwargs["exception_type"] == "TimeoutError"
    assert call_kwargs["downstream_provider"] is None
    logger.error.assert_called_once()


def test_author_slug_never_enters_exclusion_set(monkeypatch):
    """2026-05-15 fleet kill-switch regression guard.

    The exclusion set is consumed by OpenRouter's `provider.ignore` and by
    RetryModel's fail-fast check. When the whole fleet shares one model
    author, excluding that author slug takes every agent offline. Only the
    downstream serving-upstream slug is safe to exclude — and on the common
    silent-hang shape it is `None`, so nothing is excluded.
    """
    monkeypatch.setattr(observability, "_logfire", None)
    observability.reset_health_counters()
    logger = MagicMock(spec=logging.Logger)

    # Author slug supplied, downstream unknown — exclusion set stays empty.
    emit_silent_provider_hang_span(
        agent="sector_aggregator",
        wall_s=120,
        exception_type="HopTimeout",
        logger=logger,
        provider="moonshotai",
        downstream_provider=None,
    )
    counters = observability.get_health_counters()
    assert counters["silent_provider_hang_count"] == 1
    assert counters["silent_provider_hang_providers"] == []

    # Downstream upstream identified — that slug IS safe to exclude.
    emit_silent_provider_hang_span(
        agent="sector_technical",
        wall_s=120,
        exception_type="HopTimeout",
        logger=logger,
        provider="moonshotai",
        downstream_provider="together",
    )
    counters = observability.get_health_counters()
    assert counters["silent_provider_hang_providers"] == ["together"]
    observability.reset_health_counters()
