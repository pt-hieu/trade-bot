"""Shared exception classes + caught-exception reporter.

`report_caught` is the canonical way to log a caught-but-not-reraised
exception. Use it instead of `except Exception: print(...)` so silent
collapses surface as FAILED tasks in Logfire while preserving the
caller's `(name, Exception)` tuple contract.
"""

from __future__ import annotations

import logging
from typing import Any

import logfire


class ProviderUnavailable(RuntimeError):
    """Raised when an LLM provider cannot be used and fallback is disabled.

    Nested-Pydantic agents disable the MiniMax M2.7 fallback to avoid schema
    retry storms; when the primary is unhealthy for such an agent,
    resolve_model_with_fallback raises this instead of silently routing
    through the known-bad fallback.
    """


def report_caught(name: str, exc: BaseException, **attrs: Any) -> None:
    """Report a caught exception to logger.error + a Logfire span.

    Emits `logger.error(..., exc_info=True)` (full traceback) and a
    `task_exception` span so silent-swallow sites surface in stderr AND
    the Logfire trace UI. Do NOT replace a `raise` with this — preserve
    re-raise branches; this only replaces the swallow-and-return pattern.

    Args:
        name: Task identifier, shared across logger name and span
            `task_name` attr so both views key off the same label.
        exc: The caught exception instance.
        **attrs: Extra span attributes (ticker, scan_date, phase, ...).
    """
    logger_name = name.split(".")[0] if "." in name else name
    logger = logging.getLogger(logger_name)
    logger.error("[%s] %s: %s", name, type(exc).__name__, exc, exc_info=True)

    with logfire.span(
        "task_exception",
        task_name=name,
        exception_type=type(exc).__name__,
        exception_message=str(exc)[:500],
        **attrs,
    ):
        pass


__all__ = ["ProviderUnavailable", "report_caught"]
