"""Fallback brief assembly when synthesis agent fails.

Preserves Phase 1-3 data (market regime, sector analyses, position alerts,
pre-computed picks) so the pipeline can continue to alert registration
and recommendation writing even if the LLM synthesis crashes.
"""

from shared.rules.vnd_price_clamp import normalize_vnd_price


def _display_price(value: object, reason_text: str) -> float:
    """Normalize a price for the degraded fallback brief (SWI-326).

    Recovers the dropped-zeros unit-shift (44 → 44,910) so the last-resort
    render does not ship a thousand-VND price — exactly the run where
    malformed prices are most likely. The degraded renderer must never crash,
    so an unrecoverable value falls back to the raw input rather than raising.
    """
    numeric: float | int | None
    if isinstance(value, bool):
        return 0.0  # guard against bool being treated as int
    if isinstance(value, int | float):
        numeric = value
    elif value is None:
        numeric = None
    else:
        return 0.0  # non-numeric pick field → degraded render shows 0
    try:
        normalized = normalize_vnd_price(
            numeric, reason_text, agent="recommendation", boundary="display"
        )
    except (ValueError, TypeError):
        return float(numeric) if numeric is not None else 0.0
    return float(normalized) if normalized is not None else 0.0


def assemble_fallback_brief(
    sector_results: list[str],
    position_alerts: dict | None,
    trading_mode: dict | None,
    pre_computed_picks: list[dict] | None,
    market_regime: str,
    global_risk_regime: str,
    deployable_cash: float,
) -> str:
    """Assemble minimal brief from pre-computed pipeline data."""
    mode = trading_mode.get("mode", "NORMAL") if trading_mode else "NORMAL"
    lines = [
        "## CONTEXT",
        f"Market: {market_regime} | Global: {global_risk_regime} | Mode: {mode}",
        f"Deployable cash: {deployable_cash:,.0f} VND",
        "",
        "## MY HOLDINGS",
    ]

    alerts = position_alerts.get("alerts", []) if position_alerts else []
    if alerts:
        for alert in alerts:
            ticker = alert.get("ticker", "?")
            action = alert.get("recommended_action", "HOLD")
            reason = alert.get("reason", "")
            lines.append(f"- {ticker}: {action} — {reason}")
    else:
        lines.append("No position alerts.")

    lines.append("")
    lines.append("## TOP PICKS")
    if pre_computed_picks:
        for pick in pre_computed_picks:
            ticker = pick.get("ticker", "?")
            note = pick.get("note", "")
            entry = _display_price(pick.get("entry_vnd") or pick.get("entry") or 0, note)
            stop = _display_price(pick.get("stop_vnd") or pick.get("stop") or 0, note)
            target = _display_price(pick.get("target") or pick.get("target_price") or 0, note)
            lines.append(
                f"- {ticker}: Entry {entry:,.0f} / Stop {stop:,.0f} / Target {target:,.0f}"
            )
            if note:
                lines.append(f"  {note}")
    else:
        lines.append("No picks computed.")

    lines.append("")
    lines.append("## SECTOR ANALYSES")
    lines.append("(Synthesis failed — raw sector outputs below)")
    lines.append("")
    for result in sector_results:
        lines.append(result)
        lines.append("")

    return "\n".join(lines)
