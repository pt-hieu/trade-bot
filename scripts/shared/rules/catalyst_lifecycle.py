"""Catalyst phase lifecycle resolution — pure deterministic Python.

No async, no DB, no LLM. Determines current phase status with grace period
for recently expired phases and approaching-resolution detection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Literal

from .geopolitical import MAX_OPEN_ENDED_PHASE_DAYS, parse_phase_period

logger = logging.getLogger(__name__)

LifecycleState = Literal[
    "ACTIVE", "APPROACHING", "APPROACHING_RESOLUTION", "RECENTLY_EXPIRED", "NONE"
]

# Grace period: how many days after a bounded phase ends we still show it
PHASE_GRACE_DAYS = 14
# How many days before a phase ends to flag "approaching resolution"
APPROACHING_RESOLUTION_DAYS = 3
# How many days before a phase starts to flag "approaching"
APPROACHING_START_DAYS = 14


@dataclass(frozen=True)
class PhaseStatus:
    """Result of resolving which phase a catalyst is currently in."""

    phase_name: str | None
    phase_info: dict | None
    days_active: int
    lifecycle: LifecycleState

    @property
    def is_relevant(self) -> bool:
        """Whether this phase status should be surfaced to agents."""
        return self.lifecycle != "NONE"

    @property
    def impact(self) -> str:
        """Phase impact (POSITIVE/NEGATIVE/NEUTRAL), or empty if no phase."""
        if self.phase_info is None:
            return ""
        return self.phase_info.get("impact", "NEUTRAL")

    @property
    def behavior(self) -> str:
        """Phase behavior description, or empty if no phase."""
        if self.phase_info is None:
            return ""
        return self.phase_info.get("behavior", "")


_NO_PHASE = PhaseStatus(phase_name=None, phase_info=None, days_active=0, lifecycle="NONE")


def resolve_phase_status(phases: dict, today: date | None = None) -> PhaseStatus:
    """Determine current phase lifecycle status.

    Checks in priority order:
    1. Active phase (today within bounds or open-ended)
    2. Phase approaching resolution (ends within 3 days)
    3. Recently expired phase (ended within 14 days)
    4. Upcoming phase (starts within 14 days)

    Args:
        phases: Dict of {phase_name: {period, impact, behavior, ...}}
        today: Override for testing. Defaults to today.

    Returns:
        PhaseStatus with lifecycle classification.
    """
    if not phases:
        return _NO_PHASE

    if today is None:
        today = date.today()

    # Pass 1: Find active phase
    active = _find_active_phase(phases, today)
    if active is not None:
        return active

    # Pass 2: Find most recently expired phase (within grace period)
    recently_expired = _find_recently_expired(phases, today)
    if recently_expired is not None:
        return recently_expired

    # Pass 3: Find upcoming phase (starts within 14 days)
    approaching = _find_approaching(phases, today)
    if approaching is not None:
        return approaching

    return _NO_PHASE


def _find_active_phase(phases: dict, today: date) -> PhaseStatus | None:
    """Find a currently active phase. Also detects approaching-resolution."""
    for phase_name, phase_info in phases.items():
        period = phase_info.get("period", "")
        start_date, end_date, is_open_ended = parse_phase_period(period)
        if start_date is None:
            continue

        if is_open_ended:
            if today >= start_date:
                days_active = (today - start_date).days
                if days_active > MAX_OPEN_ENDED_PHASE_DAYS:
                    continue
                return PhaseStatus(
                    phase_name=phase_name,
                    phase_info=phase_info,
                    days_active=days_active,
                    lifecycle="ACTIVE",
                )
        elif end_date is not None and start_date <= today <= end_date:
            days_until_end = (end_date - today).days
            lifecycle = (
                "APPROACHING_RESOLUTION"
                if days_until_end <= APPROACHING_RESOLUTION_DAYS
                else "ACTIVE"
            )
            return PhaseStatus(
                phase_name=phase_name,
                phase_info=phase_info,
                days_active=(today - start_date).days,
                lifecycle=lifecycle,
            )

    return None


def _find_recently_expired(phases: dict, today: date) -> PhaseStatus | None:
    """Find the most recently expired bounded phase within grace period."""
    best: PhaseStatus | None = None
    best_days_since = PHASE_GRACE_DAYS + 1

    for phase_name, phase_info in phases.items():
        period = phase_info.get("period", "")
        start_date, end_date, is_open_ended = parse_phase_period(period)
        if start_date is None or is_open_ended or end_date is None:
            continue

        if end_date < today:
            days_since_expired = (today - end_date).days
            if days_since_expired <= PHASE_GRACE_DAYS and days_since_expired < best_days_since:
                best_days_since = days_since_expired
                best = PhaseStatus(
                    phase_name=phase_name,
                    phase_info=phase_info,
                    days_active=days_since_expired,
                    lifecycle="RECENTLY_EXPIRED",
                )

    return best


def _find_approaching(phases: dict, today: date) -> PhaseStatus | None:
    """Find the nearest upcoming phase that starts within 14 days."""
    best: PhaseStatus | None = None
    best_days_until = APPROACHING_START_DAYS + 1

    for phase_name, phase_info in phases.items():
        period = phase_info.get("period", "")
        start_date, end_date, is_open_ended = parse_phase_period(period)
        if start_date is None:
            continue

        if start_date > today:
            days_until = (start_date - today).days
            if days_until <= APPROACHING_START_DAYS and days_until < best_days_until:
                best_days_until = days_until
                best = PhaseStatus(
                    phase_name=phase_name,
                    phase_info=phase_info,
                    days_active=0,
                    lifecycle="APPROACHING",
                )

    return best
