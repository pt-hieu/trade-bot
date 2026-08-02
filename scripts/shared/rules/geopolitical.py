"""Centralized geopolitical shock phase configuration and date parsing.

Single source of truth for phase severity, regime floors, shock multipliers,
and active-phase filtering. Pure deterministic Python — no async, no DB, no LLM.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.types import GeopoliticalShockDict

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PhaseConfig:
    """Configuration for a single geopolitical shock phase."""

    severity: int
    shock_multiplier: float
    regime_floor: str | None
    active_for_agents: bool
    context_header: str


GEOPOLITICAL_PHASES: dict[str, PhaseConfig] = {
    "immediate_shock": PhaseConfig(
        severity=3,
        shock_multiplier=0.5,
        regime_floor="ELEVATED",
        active_for_agents=True,
        context_header="IMMEDIATE SHOCK",
    ),
    "sustained_pressure": PhaseConfig(
        severity=2,
        shock_multiplier=0.75,
        regime_floor="CAUTIOUS",
        active_for_agents=True,
        context_header="SUSTAINED PRESSURE",
    ),
    "resolution_or_escalation": PhaseConfig(
        severity=1,
        shock_multiplier=0.9,
        regime_floor=None,
        active_for_agents=True,
        context_header="RESOLUTION / ESCALATION",
    ),
}

# --- Derived maps (computed once at import time) ---

ACTIVE_SHOCK_PHASES: frozenset[str] = frozenset(
    name for name, config in GEOPOLITICAL_PHASES.items() if config.active_for_agents
)

PHASE_SEVERITY: dict[str, int] = {
    name: config.severity for name, config in GEOPOLITICAL_PHASES.items()
}

REGIME_FLOOR_MAP: dict[str, str] = {
    name: config.regime_floor
    for name, config in GEOPOLITICAL_PHASES.items()
    if config.regime_floor is not None
}

SHOCK_MULTIPLIER_MAP: dict[str, float] = {
    name: config.shock_multiplier for name, config in GEOPOLITICAL_PHASES.items()
}


def derive_shock_affected_tickers(
    geopolitical_shock: GeopoliticalShockDict | Mapping[str, object] | None,
) -> frozenset[str]:
    """Return uppercase ticker set for the active geopolitical shock, or empty.

    Single source of truth for the "is this ticker shock-affected today?"
    question. Returns an empty frozenset when there's no shock or the phase
    is not in `ACTIVE_SHOCK_PHASES` (calm/resolution short-circuits).
    Callers can use `ticker in result` directly without any guard.
    """
    if not geopolitical_shock:
        return frozenset()
    phase_name = geopolitical_shock.get("phase_name")
    if (phase_name or "") not in ACTIVE_SHOCK_PHASES:
        return frozenset()
    affected = geopolitical_shock.get("affected_tickers") or []
    if not isinstance(affected, list | tuple | set | frozenset):
        return frozenset()
    return frozenset(str(ticker).upper() for ticker in affected if ticker)


# Ordering used by `apply_shock_floor`. Higher value = more conservative.
REGIME_ORDER: dict[str, int] = {"CALM": 0, "CAUTIOUS": 1, "ELEVATED": 2, "CRISIS": 3}


def apply_shock_floor(
    computed_regime: str,
    active_geopolitical_phase: str | None,
    phase_stale: bool = False,
) -> str:
    """Raise ``computed_regime`` up to the phase's minimum regime floor.

    Shared helper called from ``calculate_global_regime`` (happy path) and
    every fail-closed branch in ``fetch_macro_metrics`` — ensures the
    ELEVATED/CAUTIOUS floor survives DXY/VIX outages on shock mornings.
    Returns ``computed_regime`` unchanged when no shock is active or when
    the floor is already weaker than the computed regime.

    When ``phase_stale`` is True (the catalyst lifecycle has flagged the
    shock as data-stale — e.g. open-ended phase past the warning
    threshold, or retro-downgraded severity with no fresh news), the
    applied floor softens by one regime notch (ELEVATED -> CAUTIOUS,
    CAUTIOUS -> CALM). This is L2 of the 2026-04-24 regime fix: the
    user keeps authority over the phase name, but the deterministic
    layer stops fossilizing an expired shock into the full floor. The
    one-notch decay never drops below CALM, never touches CRISIS
    (shock floors do not push to CRISIS anyway), and never mutates the
    phase record itself.
    """
    if not active_geopolitical_phase:
        return computed_regime
    floor = REGIME_FLOOR_MAP.get(active_geopolitical_phase)
    if not floor:
        return computed_regime
    effective_floor = _REGIME_SOFTEN_MAP.get(floor) if phase_stale else floor
    if not effective_floor:
        return computed_regime
    if REGIME_ORDER.get(effective_floor, 0) > REGIME_ORDER.get(computed_regime, 0):
        if phase_stale and effective_floor != floor:
            logger.info(
                "Geopolitical floor: %s -> %s (active %s phase, stale -> softened from %s)",
                computed_regime,
                effective_floor,
                active_geopolitical_phase,
                floor,
            )
        else:
            logger.info(
                "Geopolitical floor: %s -> %s (active %s phase)",
                computed_regime,
                effective_floor,
                active_geopolitical_phase,
            )
        return effective_floor
    return computed_regime


# Only ELEVATED / CAUTIOUS are reachable phase floors (see
# GEOPOLITICAL_PHASES). CRISIS is never a phase-derived floor — shock
# phases cap at ELEVATED — so no CRISIS entry is needed.
_REGIME_SOFTEN_MAP: dict[str, str] = {
    "ELEVATED": "CAUTIOUS",
    "CAUTIOUS": "CALM",
}


# --- Staleness thresholds ---

MAX_OPEN_ENDED_PHASE_DAYS = 90
PHASE_STALE_WARNING_DAYS = 60

# --- Date parsing ---

# Pattern: "Mar 1, 2026+" or "Apr 2026+"
_OPEN_ENDED_WITH_DAY = re.compile(r"^([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})\s*\+$")
_OPEN_ENDED_MONTH_ONLY = re.compile(r"^([A-Z][a-z]{2})\s+(\d{4})\s*\+$")
# Misplaced plus: "Sep 21+, 2026" (plus after day instead of year)
_OPEN_ENDED_MISPLACED_PLUS = re.compile(r"^([A-Z][a-z]{2})\s+(\d{1,2})\+,\s*(\d{4})$")

# Pattern: "Mar 1-7, 2026" (same month) or "Mar 28 - Apr 5, 2026" (cross-month)
_BOUNDED_SAME_MONTH = re.compile(r"^([A-Z][a-z]{2})\s+(\d{1,2})\s*-\s*(\d{1,2}),\s*(\d{4})$")
_BOUNDED_CROSS_MONTH = re.compile(
    r"^([A-Z][a-z]{2})\s+(\d{1,2})\s*-\s*([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})$"
)


def parse_phase_period(period: str) -> tuple[date | None, date | None, bool]:
    """Parse a phase period string into structured dates.

    Supports:
      - "Mar 1, 2026+"          → open-ended from specific date
      - "Apr 2026+"             → open-ended from 1st of month
      - "Mar 1-7, 2026"        → same-month bounded range
      - "Mar 28 - Apr 5, 2026" → cross-month bounded range

    Returns:
        (start_date, end_date_or_None, is_open_ended)
        Returns (None, None, False) if parsing fails.
    """
    period = period.strip()

    # Open-ended with day: "Mar 1, 2026+"
    match = _OPEN_ENDED_WITH_DAY.match(period)
    if match:
        month_str, day_str, year_str = match.groups()
        try:
            start = datetime.strptime(f"{month_str} {day_str}, {year_str}", "%b %d, %Y").date()
            return start, None, True
        except ValueError:
            return None, None, False

    # Misplaced plus after day: "Sep 21+, 2026" → treat as "Sep 21, 2026+"
    match = _OPEN_ENDED_MISPLACED_PLUS.match(period)
    if match:
        month_str, day_str, year_str = match.groups()
        logger.warning(
            "Misplaced '+' in phase period '%s' — treating as '%s %s, %s+'",
            period,
            month_str,
            day_str,
            year_str,
        )
        try:
            start = datetime.strptime(f"{month_str} {day_str}, {year_str}", "%b %d, %Y").date()
            return start, None, True
        except ValueError:
            return None, None, False

    # Open-ended month only: "Apr 2026+"
    match = _OPEN_ENDED_MONTH_ONLY.match(period)
    if match:
        month_str, year_str = match.groups()
        try:
            start = datetime.strptime(f"{month_str} 1, {year_str}", "%b %d, %Y").date()
            return start, None, True
        except ValueError:
            return None, None, False

    # Bounded cross-month: "Mar 28 - Apr 5, 2026"
    match = _BOUNDED_CROSS_MONTH.match(period)
    if match:
        start_month, start_day, end_month, end_day, year_str = match.groups()
        try:
            start = datetime.strptime(f"{start_month} {start_day}, {year_str}", "%b %d, %Y").date()
            end = datetime.strptime(f"{end_month} {end_day}, {year_str}", "%b %d, %Y").date()
            return start, end, False
        except ValueError:
            return None, None, False

    # Bounded same-month: "Mar 1-7, 2026"
    match = _BOUNDED_SAME_MONTH.match(period)
    if match:
        month_str, start_day, end_day, year_str = match.groups()
        try:
            start = datetime.strptime(f"{month_str} {start_day}, {year_str}", "%b %d, %Y").date()
            end = datetime.strptime(f"{month_str} {end_day}, {year_str}", "%b %d, %Y").date()
            return start, end, False
        except ValueError:
            return None, None, False

    logger.warning("Unparseable phase period: '%s'", period)
    return None, None, False


def validate_phase_periods(phases: dict) -> list[str]:
    """Validate all phase periods at write-time.

    Returns list of error messages. Empty list = all valid.
    """
    errors: list[str] = []
    for phase_name, phase_info in phases.items():
        if not isinstance(phase_info, dict):
            errors.append(f"Phase '{phase_name}': info is not a dict")
            continue
        period = phase_info.get("period", "")
        if not period:
            errors.append(f"Phase '{phase_name}': missing 'period' field")
            continue
        start, end, is_open = parse_phase_period(period)
        if start is None:
            errors.append(
                f"Phase '{phase_name}': unparseable period '{period}'. "
                "Expected: 'Mar 1-7, 2026', 'Mar 1, 2026+', 'Apr 2026+', "
                "or 'Mar 28 - Apr 5, 2026'"
            )
        if not is_open and end is not None and end < start:  # type: ignore[operator]
            errors.append(f"Phase '{phase_name}': end date {end} is before start date {start}")
    return errors


# Canonical phase-shape allowlists — derived from GEOPOLITICAL_PHASES so the
# agent validators can't drift behind new phase definitions.
PHASE_KEYS: frozenset[str] = frozenset(GEOPOLITICAL_PHASES.keys())
PHASE_IMPACTS: frozenset[str] = frozenset({"POSITIVE", "NEGATIVE", "NEUTRAL"})


def validate_phase_shape(phases: dict) -> None:
    """Validate the structural shape of a catalyst ``phases`` dict.

    Called from both ``CatalystAddition`` and ``CatalystUpdate`` Pydantic
    validators so the two paths stay in lockstep. Raises ``ValueError``
    with a descriptive message on first violation — Pydantic wraps the
    error into ``ValidationError`` at the call site.
    """
    if not isinstance(phases, dict):
        raise ValueError("phases must be a dict")
    for phase_name, phase_info in phases.items():
        if phase_name not in PHASE_KEYS:
            raise ValueError(
                f"phase '{phase_name}' not allowed; must be one of {sorted(PHASE_KEYS)}"
            )
        if not isinstance(phase_info, dict):
            raise ValueError(f"phase '{phase_name}': info must be a dict")
        for required in ("period", "impact", "behavior"):
            if required not in phase_info:
                raise ValueError(f"phase '{phase_name}': missing '{required}'")
        impact = phase_info.get("impact")
        if impact not in PHASE_IMPACTS:
            raise ValueError(f"phase '{phase_name}': impact must be one of {sorted(PHASE_IMPACTS)}")
