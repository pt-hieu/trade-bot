"""Shared utilities for neon DB result processing.

Decimal("0.0") from asyncpg is falsy in Python, so the common pattern
``float(row["x"]) if row["x"] else default`` silently converts valid
zero values to the default. Use ``safe_float`` instead.
"""

from __future__ import annotations

import json


def json_for_jsonb_cast(value: object) -> str | None:
    """Pre-serialize a Python value for a ``$N::jsonb`` text-bound parameter.

    Paired with an explicit ``::jsonb`` cast in the SQL. Without the cast the
    asyncpg jsonb codec runs ``json.dumps`` again and double-encodes the
    value — the bug migration 307 cleaned up. Returns ``None`` unchanged so
    callers can still pass Python ``None`` to NULL columns.
    """
    if value is None:
        return None
    return json.dumps(value, default=str)


def parse_jsonb_object(value: object) -> dict | None:
    """Parse a JSONB object column, unwrapping legacy double-encoded strings.

    Rows written before migration 307 may still be jsonb strings containing
    serialized JSON — recursively unwrap up to 5 levels before giving up.
    Returns ``None`` for missing, non-dict, or unparseable values so that
    downstream code can use ``value or {}`` safely.
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    current: object = value
    for _ in range(5):
        if not isinstance(current, str):
            break
        try:
            current = json.loads(current)
        except (json.JSONDecodeError, ValueError, TypeError):
            return None
    return current if isinstance(current, dict) else None


def parse_jsonb_list(value: object) -> list:
    """Parse a JSONB array column — asyncpg may return a list or raw string."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def safe_float(value: object, default: float | None = None) -> float | None:
    """Convert a DB value to float, treating only ``None`` as missing.

    Unlike ``float(x) if x else default``, this correctly handles
    ``Decimal("0.0")`` which is falsy but represents a real zero.
    """
    if value is None:
        return default
    return float(value)  # type: ignore[arg-type]


def safe_round(value: object, decimals: int = 2) -> float | None:
    """Convert to float and round, treating only ``None`` as missing.

    Combines ``safe_float`` + ``round`` in one call.  Handles ``0.0``
    correctly (falsy but valid).
    """
    converted = safe_float(value)
    if converted is None:
        return None
    return round(converted, decimals)
