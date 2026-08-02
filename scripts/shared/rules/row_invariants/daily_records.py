"""Mirror placeholder for `daily_records` CHECK constraints (SWI-NN).

Stub.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import ViolationDetail


def validate_row(row: tuple) -> list[ViolationDetail]:  # noqa: ARG001
    return []
