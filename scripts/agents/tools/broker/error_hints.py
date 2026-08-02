"""Pydantic ``ValidationError`` → tailored coaching hints for tool callers.

The broker wraps every tool implementation with ``pydantic.validate_call``, so
arg failures surface as ``ValidationError``. Returning a single generic hint
("check Literal values") for every error class teaches the LLM the wrong
remedy when the actual failure is a missing or unexpected argument — the model
then loops on identical broken signatures until ``request_limit`` is exhausted.

This module differentiates the three error classes that show up in production
logs and emits one tailored hint per class:

- ``missing_argument`` → tell the model exactly which arg is missing and how
  to pass it via ``call_tools`` ``args``.
- ``unexpected_keyword_argument`` → name the offending kwarg and point at
  ``get_tool_schemas`` for the declared signature.
- ``literal_error`` (and the older ``literal``) → keep the existing Literal
  hint so the model fetches allowed enum values.

Pure function (sync, no side effects) — unit-testable without async or
network. Consumed by ``native_tools._wrap_with_policy`` (SWI-180) — fed into
``ModelRetry`` so the LLM sees the classified hint on its retry.
"""

from __future__ import annotations

from typing import TypedDict

from pydantic import ValidationError

LITERAL_VALIDATION_HINT = "Check allowed Literal values with get_tool_schemas."

# Sentinel returned when no field-specific hint applies. Generic enough to
# always be honest about the failure surface, specific enough to point the
# model at the structured ``pydantic_error`` payload it already received.
_GENERIC_HINT = (
    "Read the pydantic_error field above for the failing field path. "
    "Call get_tool_schemas to see the expected argument shape before retrying."
)


class ClassifiedError(TypedDict):
    """Structured tool-error response surfaced to the LLM.

    ``error_type`` is the canonical key the broker uses for the
    error-signature breaker (3 same-(tool, error_type) retries → break).
    ``hint`` is what the LLM reads — one tailored sentence per class.
    """

    error: str
    pydantic_error: str
    hint: str
    error_type: str


def classify_validation_error(
    name: str,
    exc: ValidationError,
    *,
    tickers_in_scope: list[str] | None = None,
) -> ClassifiedError:
    """Map a pydantic ``ValidationError`` to a tailored coaching response.

    The classifier reads the *first* error from ``exc.errors()`` because
    pydantic batches all field failures but the LLM benefits from one focused
    message — chasing field-N hints when field-1 is broken sends it down the
    wrong remediation path.

    ``tickers_in_scope`` lets the broker anchor the missing-``tickers`` hint
    on the exact ticker set the agent already has in its context (positions
    holdings or sector members). Today's GLM-5 loop on positions_value /
    positions_thesis emitted ``args:{}`` 3× in a row because the previous
    hint named the field but not the values; anchoring on the in-scope list
    makes the next retry self-correcting on the first attempt.
    """
    errors = list(exc.errors())
    error_type = ""
    missing_field = ""
    unexpected_field = ""
    primary_input: object = None
    primary_loc = ""

    if errors:
        primary = errors[0]
        error_type = str(primary.get("type") or "")
        location = primary.get("loc") or ()
        primary_input = primary.get("input")
        primary_loc = _last_string(location)
        if error_type in {"missing", "missing_argument", "missing_keyword_only_argument"}:
            missing_field = primary_loc
        elif error_type == "unexpected_keyword_argument":
            unexpected_field = primary_loc

    hint = _hint_for(
        error_type,
        name,
        missing_field,
        unexpected_field,
        tickers_in_scope=tickers_in_scope,
        primary_input=primary_input,
        primary_loc=primary_loc,
    )
    return {
        "error": f"Invalid args for {name}",
        "pydantic_error": str(exc),
        "hint": hint,
        "error_type": error_type or "validation_error",
    }


def _last_string(location: tuple[object, ...] | list[object]) -> str:
    """Return the rightmost string segment from a pydantic error ``loc`` tuple."""
    for segment in reversed(list(location)):
        if isinstance(segment, str) and segment:
            return segment
    return ""


def _hint_for(
    error_type: str,
    tool_name: str,
    missing_field: str,
    unexpected_field: str,
    *,
    tickers_in_scope: list[str] | None = None,
    primary_input: object = None,
    primary_loc: str = "",
) -> str:
    """Produce one tailored hint sentence for the detected error class.

    When ``missing_field == "tickers"`` and ``tickers_in_scope`` is provided,
    the hint embeds the exact in-scope ticker list so the next call can copy
    them verbatim — eliminating the "guess what tickers" ambiguity that drove
    the 2026-04-28 positions_value / positions_thesis empty-args loop.
    """
    if error_type in {"missing", "missing_argument", "missing_keyword_only_argument"}:
        if missing_field:
            scope_suffix = ""
            if missing_field == "tickers" and tickers_in_scope:
                scope_suffix = f" In scope: {list(tickers_in_scope)}."
            return (
                f"Required argument `{missing_field}` is missing. Pass it inside "
                f'args, e.g. {{"name": "{tool_name}", "args": {{"{missing_field}": [...]}}}}. '
                f'Call get_tool_schemas(["{tool_name}"]) for the full signature.'
                f"{scope_suffix}"
            )
        return (
            f"A required argument is missing for {tool_name}. Call "
            f'get_tool_schemas(["{tool_name}"]) to see required fields, '
            "then resend with the full args dict."
        )
    if error_type == "unexpected_keyword_argument":
        if unexpected_field:
            return (
                f"Tool {tool_name} does not accept argument `{unexpected_field}`. "
                f'Call get_tool_schemas(["{tool_name}"]) and pass only declared '
                "arguments."
            )
        return (
            f"An unexpected argument was passed to {tool_name}. Call "
            f'get_tool_schemas(["{tool_name}"]) to see the declared signature.'
        )
    if error_type == "list_type":
        # Stringified-array case: agent passed args={"tickers": "[\"VHM\",\"TCB\"]"}
        # instead of args={"tickers": ["VHM","TCB"]}. Hit 19× in 2026-05-14
        # morning scan (18 narrative.get_active + 1 enrichment.get_flow). SWI-180
        # rejected the BeforeValidator coercer pattern — fix is to coach the
        # shape on retry instead.
        if isinstance(primary_input, str) and primary_input.lstrip().startswith("["):
            field = primary_loc or "the list field"
            return (
                f"Argument `{field}` must be a Python list literal, not a "
                f'JSON string. Pass `{field}=["VHM","TCB"]` (square brackets, '
                f'quoted strings), not `{field}="[VHM,TCB]"`. Tool params are '
                "native Python types — the broker does not parse JSON strings."
            )
        return (
            f"Argument `{primary_loc or 'list field'}` must be a list. "
            f"Pass it as `{primary_loc or 'field'}=[...]`, not a scalar or string."
        )
    # When adding a third list-shape case (set_type, dict_type, etc.), extract
    # _hint_for into a dispatch table keyed on error_type. Bag-of-cases cost
    # < refactor cost as of 2026-05-14.
    if error_type in {"literal_error", "literal"}:
        return LITERAL_VALIDATION_HINT
    return _GENERIC_HINT
