"""Mirror placeholder for `catalyst_signals` CHECK constraints (SWI-NN).

Stub. Fill in when a CHECK lands on this table.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import ViolationDetail


def validate_row(row: tuple) -> list[ViolationDetail]:  # noqa: ARG001
    return []
