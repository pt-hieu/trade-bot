"""Database functions for strategy directives."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date

from ..database import get_db


async def save_strategy_directive(
    scan_date: date, directive_text: str, constraints: dict | Mapping[str, object]
) -> bool:
    """Save strategy directive to database.

    Args:
        scan_date: Date for the directive
        directive_text: Free-form strategic text from agent
        constraints: Deterministic constraints dict

    Returns:
        True if saved successfully
    """
    db = await get_db()
    try:
        await db.execute(
            """
            INSERT INTO strategy_directives (scan_date, directive, constraints)
            VALUES ($1, $2, $3::jsonb)
            ON CONFLICT (scan_date) DO UPDATE SET
                directive = EXCLUDED.directive,
                constraints = EXCLUDED.constraints,
                created_at = NOW()
            """,
            scan_date,
            directive_text,
            json.dumps(constraints),
        )
        return True
    except Exception as e:
        print(f"  [Neon] Failed to save strategy directive: {e}")
        return False


async def get_strategy_directive(scan_date: date) -> dict | None:
    """Load strategy directive for a date.

    Returns:
        Dict with directive and constraints, or None if not found.
    """
    db = await get_db()
    try:
        row = await db.fetch_one(
            "SELECT directive, constraints FROM strategy_directives WHERE scan_date = $1",
            scan_date,
        )
        if not row:
            return None

        constraints = row["constraints"]
        if isinstance(constraints, str):
            constraints = json.loads(constraints)

        return {
            "directive": row["directive"],
            "constraints": constraints,
        }
    except Exception as e:
        print(f"  [Neon] Failed to load strategy directive: {e}")
        return None
