#!/usr/bin/env python3
"""
Observability configuration using Pydantic Logfire.

Usage:
    from shared.observability import configure_observability, span

    # Call once at script startup
    configure_observability()

    # Use custom spans for phases
    with span("analyze_sector", sector="banking"):
        ...
"""

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Literal

# Module-level state
_configured = False
_logfire = None

# Per-pipeline-run health counters. Reset on pipeline entry via
# `reset_health_counters()`; emitted as a `pipeline_health_summary` span
# on exit via `emit_pipeline_health_summary()`. Pure in-memory; no DB.
_silent_provider_hang_count: int = 0
_aggregator_belief_gap_count: int = 0
_silent_provider_hang_agents: list[str] = []
_silent_provider_hang_providers: list[str] = []
_aggregator_belief_gap_keys: list[str] = []


def configure_observability(
    service_name: str = "swingy",
    environment: str | None = None,
) -> bool:
    """Configure Logfire observability.

    Args:
        service_name: Service name for Logfire
        environment: Environment name (defaults to LOGFIRE_ENVIRONMENT or "development")

    Returns:
        True if configured successfully, False if skipped (no token)
    """
    global _configured, _logfire

    if _configured:
        return True

    token = os.environ.get("LOGFIRE_TOKEN")
    if not token:
        return False

    try:
        import logfire

        _logfire = logfire

        logfire.configure(
            token=token,
            service_name=service_name,
            environment=environment or os.environ.get("LOGFIRE_ENVIRONMENT", "development"),
            send_to_logfire="if-token-present",
        )

        # Instrument PydanticAI globally (instruments all agents)
        logfire.instrument_pydantic_ai()

        _configured = True
        return True

    except Exception as e:
        print(f"Logfire configuration failed: {e}")
        return False


class _NoOpSpan:
    """No-op span for when Logfire is not configured."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass


@contextmanager
def span(name: str, **attributes: Any) -> Generator[Any, None, None]:
    """Create a trace span.

    If Logfire is not configured, returns a no-op context manager.

    Usage:
        with span("analyze_sector", sector="banking", ticker_count=5):
            ...
    """
    if _logfire is None:
        yield _NoOpSpan()
    else:
        with _logfire.span(name, **attributes) as s:
            yield s


def emit_ticker_drop_span(
    *,
    agent: str,
    expected: set[str],
    produced: set[str],
    logger: Any,
    **extra: Any,
) -> set[str]:
    """Emit a `llm_ticker_drop` span when an LLM aggregator silently drops
    expected tickers. Returns the dropped set (empty when nothing dropped).

    Callers pass pre-computed sets so the shape works for both structured
    aggregators (ticker sets from model output) and text writers (regex
    over markdown). `extra` adds attributes like `sector=...`.
    """
    dropped = expected - produced
    if not dropped:
        return set()
    dropped_sorted = sorted(dropped)
    with span(
        "llm_ticker_drop",
        agent=agent,
        dropped=dropped_sorted,
        input_n=len(expected),
        output_n=len(produced),
        **extra,
    ):
        logger.warning(
            "%s dropped %d of %d tickers: %s",
            agent,
            len(dropped),
            len(expected),
            dropped_sorted,
        )
    return dropped


def log_info(message: str, **attributes: Any) -> None:
    """Log an info message to Logfire."""
    if _logfire:
        _logfire.info(message, **attributes)


def log_warn(message: str, **attributes: Any) -> None:
    """Log a warning message to Logfire."""
    if _logfire:
        _logfire.warn(message, **attributes)


def log_error(message: str, **attributes: Any) -> None:
    """Log an error message to Logfire."""
    if _logfire:
        _logfire.error(message, **attributes)


def emit_belief_coverage_gap_span(
    *,
    scope: str,
    missing_count: int,
    missing_sample: list[tuple[str, str]],
    logger: Any,
) -> None:
    """Emit an alertable `belief_coverage_gap` span when sub-agents
    produced views but no matching beliefs (post A2, this means
    PydanticAI schema retry exhausted — never a benign null).

    Pipeline-review + alerting query `belief_coverage_gap` directly
    to detect belief persistence collapse in seconds.
    """
    with span(
        "belief_coverage_gap",
        scope=scope,
        missing_count=missing_count,
        missing_sample=[f"{agent_key}/{ticker}" for agent_key, ticker in missing_sample],
    ):
        logger.error(
            "BELIEF_COVERAGE_GAP scope=%s missing=%d",
            scope,
            missing_count,
        )


def emit_silent_provider_hang_span(
    *,
    agent: str,
    wall_s: int,
    exception_type: str,
    logger: Any,
    provider: str | None,
    downstream_provider: str | None = None,
    sector: str | None = None,
) -> None:
    """Emit an alertable `silent_provider_hang` span when an aggregator hits
    its phase wall with no response bytes (2026-04-13 silent-hang incident).

    Creates a dedicated trace span so pipeline-review + alerting can query
    `hang_type="silent_provider"` directly. Also bumps the per-run counter
    emitted by `emit_pipeline_health_summary()`.

    Two provider kwargs, deliberately distinct:

    * `provider` (required) — the model-author slug from
      `provider_slug_from_timeout(exc)`. Recorded on the span for
      observability; identifies the *model*, never excluded.
    * `downstream_provider` — the OpenRouter serving-upstream slug from
      `downstream_provider_from_timeout(exc)`. ONLY this feeds the
      session exclusion set: excluding a real upstream makes OpenRouter
      route around it, whereas excluding the author would kill the whole
      fleet when every agent shares one author (2026-05-15 incident).
      Structurally `None` on every hop-timeout path today (the wall fires
      before OpenRouter reports the upstream — see `HopTimeout` + SWI-370),
      so in practice nothing is excluded and the exclusion set stays empty
      for the hop-timeout class. The kwarg is kept as ready plumbing for a
      future producer.
    """
    global _silent_provider_hang_count
    _silent_provider_hang_count += 1
    _silent_provider_hang_agents.append(agent)
    # Only the OpenRouter serving-upstream slug is safe to exclude — the
    # author slug would take the whole fleet offline. A hop timeout fires
    # before any response byte, so `downstream_provider` is structurally
    # None on every timeout path today (SWI-370); this append is therefore
    # currently unreachable and kept only as ready plumbing — nothing is
    # added and routing is left untouched.
    if downstream_provider:
        _silent_provider_hang_providers.append(downstream_provider)
    span_kwargs: dict[str, Any] = {
        "agent": agent,
        "hang_type": "silent_provider",
        "wall_s": wall_s,
        "exception_type": exception_type,
        # Cumulative counter for this pipeline run — Logfire dashboards can
        # query this single attribute instead of aggregating spans
        # (MON-2026-04-21 Fix 2).
        "cumulative_count": _silent_provider_hang_count,
        "provider": provider,
        "downstream_provider": downstream_provider,
    }
    if sector is not None:
        span_kwargs["sector"] = sector
    with span("silent_provider_hang", **span_kwargs):
        logger.error(
            "SILENT_PROVIDER_HANG agent=%s wall=%ds exc=%s cumulative=%d provider=%s downstream=%s",
            agent,
            wall_s,
            exception_type,
            _silent_provider_hang_count,
            provider or "unknown",
            downstream_provider or "unknown",
        )


def emit_agent_near_ceiling_span(
    *,
    agent: str,
    output_tokens: int,
    max_tokens: int,
    logger: Any,
    **extra: Any,
) -> None:
    """Emit `agent_near_ceiling` span when output crosses 80% of `max_tokens`.

    WARNING at `output_tokens >= 0.8 * max_tokens`; ERROR at ceiling (truncation
    almost certain). Consumers decide severity from the emitted span.
    """
    if max_tokens <= 0 or output_tokens <= 0:
        return
    ratio = output_tokens / max_tokens
    if ratio < 0.8:
        return
    with span(
        "agent_near_ceiling",
        agent=agent,
        output_tokens=output_tokens,
        max_tokens=max_tokens,
        ratio=round(ratio, 3),
        truncated=output_tokens >= max_tokens,
        **extra,
    ):
        if output_tokens >= max_tokens:
            logger.error(
                "AGENT_NEAR_CEILING agent=%s out=%d/max=%d (truncation likely)",
                agent,
                output_tokens,
                max_tokens,
            )
        else:
            logger.warning(
                "AGENT_NEAR_CEILING agent=%s out=%d/max=%d (%.0f%%)",
                agent,
                output_tokens,
                max_tokens,
                ratio * 100,
            )


def observe_agent_output(
    *,
    agent: str,
    result: Any,
    max_tokens: int,
    logger: Any,
) -> None:
    """Extract output_tokens from a PydanticAI RunResult and emit the ceiling span.

    Swallows usage-extraction errors at DEBUG — a missing usage summary must
    never fail an agent run.
    """
    try:
        usage = result.usage()
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        emit_agent_near_ceiling_span(
            agent=agent,
            output_tokens=output_tokens,
            max_tokens=max_tokens,
            logger=logger,
        )
    except Exception as ceiling_err:  # noqa: BLE001
        logger.debug("ceiling-span emit skipped for %s: %s", agent, ceiling_err)


def emit_model_hop_timing_span(
    *,
    agent: str,
    model_id: str,
    hop: Literal["primary", "fallback"],
    duration_ms: int,
    outcome: Literal["success", "error", "timeout"],
    logger: Any,
    **extra: Any,
) -> None:
    """Emit a `model_hop_timing` span for each primary/fallback attempt.

    `hop` is one of "primary" | "fallback". `outcome` is "success" | "error" |
    "timeout". Surfaces in Logfire so the next silent-hang investigation can
    answer "which hop stalled?" from trace data alone — closes the diagnostic
    gap that cost 2 hours on the 2026-04-20 positions incident.
    """
    with span(
        "model_hop_timing",
        agent=agent,
        model_id=model_id,
        hop=hop,
        duration_ms=duration_ms,
        outcome=outcome,
        **extra,
    ):
        logger.info(
            "MODEL_HOP agent=%s model=%s hop=%s outcome=%s duration_ms=%d",
            agent,
            model_id,
            hop,
            outcome,
            duration_ms,
        )


def emit_model_hop_retry_span(
    *,
    agent: str,
    model_id: str,
    provider: str,
    attempt: int,
    backoff_ms: int,
    outcome: Literal["retry", "fail_fast_cluster_evidence"],
    logger: Any,
    **extra: Any,
) -> None:
    """Emit a `model_hop_retry` span when RetryModel decides.

    `outcome="retry"` means the wrapper slept `backoff_ms` and re-issued the
    request; `outcome="fail_fast_cluster_evidence"` means cluster evidence
    existed (provider slug already in session exclusion set) so the wrapper
    re-raised without retrying. Counts surface in the review collector so the
    next pipeline-review can separate transient flakes from hard hangs.
    """
    with span(
        "model_hop_retry",
        agent=agent,
        model_id=model_id,
        provider=provider,
        attempt=attempt,
        backoff_ms=backoff_ms,
        outcome=outcome,
        **extra,
    ):
        logger.info(
            "MODEL_HOP_RETRY agent=%s model=%s provider=%s attempt=%d outcome=%s backoff_ms=%d",
            agent,
            model_id,
            provider,
            attempt,
            outcome,
            backoff_ms,
        )


def record_aggregator_belief_gap(*, ensemble: str, agent_key: str) -> None:
    """Bump the per-run aggregator-gap counter.

    Called from `shared.rules.belief_coverage.assert_belief_coverage` when
    an OPTIONAL agent key (aggregator) is missing. No span is emitted here —
    the gap is already ERROR-logged at the call site, and the aggregated
    counter surfaces on the `pipeline_health_summary` span.
    """
    global _aggregator_belief_gap_count
    _aggregator_belief_gap_count += 1
    _aggregator_belief_gap_keys.append(f"{ensemble}/{agent_key}")


def reset_health_counters() -> None:
    """Reset per-run counters. Call at pipeline entry."""
    global _silent_provider_hang_count, _aggregator_belief_gap_count
    _silent_provider_hang_count = 0
    _aggregator_belief_gap_count = 0
    _silent_provider_hang_agents.clear()
    _silent_provider_hang_providers.clear()
    _aggregator_belief_gap_keys.clear()


def get_health_counters() -> dict[str, Any]:
    """Snapshot the current counters (used by tests + the summary span)."""
    return {
        "silent_provider_hang_count": _silent_provider_hang_count,
        "aggregator_belief_gap_count": _aggregator_belief_gap_count,
        "silent_provider_hang_agents": list(_silent_provider_hang_agents),
        "silent_provider_hang_providers": list(_silent_provider_hang_providers),
        "aggregator_belief_gap_keys": list(_aggregator_belief_gap_keys),
    }


def emit_pipeline_health_summary(
    *,
    scan_date: str,
    phase: str,
    logger: Any,
    warn_threshold: int = 5,
    **extra: Any,
) -> None:
    """Emit a `pipeline_health_summary` span at pipeline exit.

    Carries per-run counters so pipeline-review + alerting can query a
    single span instead of aggregating individual event spans. Logs a
    WARNING when either counter crosses `warn_threshold` — operators
    grep this to detect degraded runs that still completed.
    """
    counters = get_health_counters()
    with span(
        "pipeline_health_summary",
        scan_date=scan_date,
        phase=phase,
        **counters,
        **extra,
    ):
        if counters["silent_provider_hang_count"] >= warn_threshold:
            logger.warning(
                "PIPELINE_HEALTH_WARN silent_provider_hang_count=%d agents=%s",
                counters["silent_provider_hang_count"],
                counters["silent_provider_hang_agents"],
            )
        if counters["aggregator_belief_gap_count"] >= warn_threshold:
            logger.warning(
                "PIPELINE_HEALTH_WARN aggregator_belief_gap_count=%d keys=%s",
                counters["aggregator_belief_gap_count"],
                counters["aggregator_belief_gap_keys"],
            )

        # Silent-hang cluster Telegram notification (MON-2026-04-19-008).
        # Fires below the WARN threshold so operators see clustering before it
        # compounds. `maybe_emit_silent_hang_alert` is a no-op when the count
        # is below its own threshold.
        try:
            from shared.alerts import maybe_emit_silent_hang_alert

            maybe_emit_silent_hang_alert(
                scan_date=scan_date,
                phase=phase,
                hang_count=counters["silent_provider_hang_count"],
                hang_agents=counters["silent_provider_hang_agents"],
                suspected_providers=counters["silent_provider_hang_providers"],
            )
        except Exception as exc:
            logger.warning("SILENT_HANG_ALERT_DISPATCH_FAILED %s", exc)


def shutdown_observability() -> None:
    """Flush pending spans and shut down Logfire.

    Call in the finally block of pipeline entry points to ensure
    BatchSpanProcessor flushes before process exit.
    """
    if _logfire is not None:
        import contextlib

        with contextlib.suppress(Exception):
            _logfire.shutdown()
