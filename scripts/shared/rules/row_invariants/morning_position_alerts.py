"""Mirror placeholder for `morning_position_alerts` CHECK constraints (SWI-NN).

No CHECK constraints today. Stub keeps the migration-invariant-mirror hook
self-test green and gives future CHECKs an obvious home.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import ViolationDetail


def validate_row(row: tuple) -> list[ViolationDetail]:  # noqa: ARG001
    return []
