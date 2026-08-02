"""Async constraint orchestration — fetches DB data, delegates to shared/rules/constraints.

Pure logic lives in shared/rules/constraints.py. This module only handles DB I/O.
"""

import logging
from datetime import date

from shared.rules.constraints import (
    PipelineConstraints,
    apply_circuit_breakers,
    compose_with_retro,
    compute_directive_constraints,
    inject_entry_gate,
)

logger = logging.getLogger(__name__)


async def compute_pipeline_constraints(
    scan_date: date,
    entries_allowed: bool,
    entries_blocked_reason: str | None = None,
) -> tuple[PipelineConstraints, list[dict], dict]:
    """Single async entry point for pipeline constraints.

    Fetches goals + cash + retro from DB, composes via pure functions.
    Returns (constraints, goals, cash_dict).
    """
    import asyncio

    from agents.tools.portfolio import get_all_goals_progress_async, get_cash_balance_async
    from agents.tools.retro_constraints import compute_retro_constraints

    # Fetch cash + retro in parallel (independent DB calls)
    cash_task = asyncio.ensure_future(get_cash_balance_async())
    retro_task = asyncio.ensure_future(compute_retro_constraints(scan_date))
    cash = await cash_task
    goals = await get_all_goals_progress_async(cash=cash, scan_date=scan_date)
    constraints = compute_directive_constraints(goals, cash)

    try:
        retro = await retro_task
        constraints = compose_with_retro(constraints, retro)
    except Exception as error:
        logger.warning("Retro constraints unavailable (non-fatal): %s", error)

    constraints = apply_circuit_breakers(constraints)
    constraints = inject_entry_gate(constraints, entries_allowed, entries_blocked_reason)

    return constraints, goals, cash
