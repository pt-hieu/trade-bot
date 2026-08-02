"""Geopolitical shock context builder for agent prompt injection."""

from collections.abc import Mapping

from shared.rules.geopolitical import ACTIVE_SHOCK_PHASES, GEOPOLITICAL_PHASES

# Read-only mapping view over a GeopoliticalShockDict. Using Mapping (not the
# TypedDict directly) keeps this helper a leaf module that cross-imports
# cleanly from shared.neon, agents, and pipeline without circular chains.
ShockLike = Mapping[str, object]


def _as_str(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def build_geopolitical_context(geopolitical_shock: ShockLike | None) -> str:
    """Build geopolitical context string for agent prompt injection.

    Returns empty string if no active shock or phase not in ACTIVE_SHOCK_PHASES.
    Reusable across positions_ensemble, sector, critic, position_strategist, longterm.
    """
    if not geopolitical_shock:
        return ""
    phase_name = _as_str(geopolitical_shock.get("phase_name"))
    if phase_name not in ACTIVE_SHOCK_PHASES:
        return ""

    phase_config = GEOPOLITICAL_PHASES.get(phase_name)
    header = phase_config.context_header if phase_config else phase_name.upper()

    # Resolution phase has uncertain directionality — avoid strong conviction language.
    if phase_name == "resolution_or_escalation":
        return _build_resolution_context(geopolitical_shock, header)

    return _build_active_shock_context(geopolitical_shock, header)


def _build_active_shock_context(geopolitical_shock: ShockLike, header: str) -> str:
    """Build context for immediate_shock or sustained_pressure phases."""
    lines = [
        "GEOPOLITICAL SHOCK CONTEXT",
        f"Active: {_as_str(geopolitical_shock.get('catalyst_event'), 'Unknown event')}",
        f"Phase: {header}",
        f"Behavior: {_as_str(geopolitical_shock.get('behavior'), 'Monitor closely')}",
        f"Impact: {_as_str(geopolitical_shock.get('impact'), 'NEGATIVE')}",
    ]
    _append_common_fields(lines, geopolitical_shock)
    lines.append("Factor this into your analysis — correlations increase during shocks.")
    return "\n".join(lines)


def _build_resolution_context(geopolitical_shock: ShockLike, header: str) -> str:
    """Build softer context for resolution_or_escalation phase."""
    lines = [
        "GEOPOLITICAL UNCERTAINTY CONTEXT",
        f"Active: {_as_str(geopolitical_shock.get('catalyst_event'), 'Unknown event')}",
        f"Phase: {header}",
        f"Behavior: {_as_str(geopolitical_shock.get('behavior'), 'Monitor for resolution or escalation')}",
        "Situation is uncertain — prepare for resolution (sharp recovery) or escalation (deeper selloff).",
        "Reduce conviction on directional geo-driven bets. Maintain existing positions cautiously.",
    ]
    _append_common_fields(lines, geopolitical_shock)
    return "\n".join(lines)


def _append_common_fields(lines: list[str], geopolitical_shock: ShockLike) -> None:
    """Append affected tickers, notes, and staleness warning."""
    affected_raw = geopolitical_shock.get("affected_tickers")
    affected: list[str] = (
        [t for t in affected_raw if isinstance(t, str)] if isinstance(affected_raw, list) else []
    )
    if affected:
        lines.append(f"Impacted tickers: {', '.join(affected[:15])}")
    notes = _as_str(geopolitical_shock.get("notes"))
    if notes:
        lines.append(f"Notes: {notes}")
    days_active_raw = geopolitical_shock.get("days_active")
    days_active = days_active_raw if isinstance(days_active_raw, int) else 0
    if geopolitical_shock.get("phase_stale"):
        lines.append(
            f"WARNING: This shock phase has been active for {days_active} days — may be stale."
        )
