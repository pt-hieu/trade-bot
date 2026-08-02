"""Prose formatters that turn market dicts into natural-language strings."""

from __future__ import annotations


def _format_regime_prose(regime: dict) -> str:
    """Convert market regime dict to natural prose."""
    if "error" in regime:
        return f"Market Regime: {regime['error']}"

    r = regime.get("regime", "UNKNOWN")
    confidence = regime.get("regime_confidence", 0)
    signal = regime.get("key_signal", "No signal")
    rec = regime.get("recommendation", "")

    conf_pct = (
        f"{confidence * 100:.0f}%" if isinstance(confidence, (int, float)) else f"{confidence}%"
    )
    return f"Market Regime: {r} ({conf_pct} confidence). Signal: {signal}. {rec}"


def _format_rotation_prose(rotation: dict) -> str:
    """Convert sector rotation dict to natural prose."""
    if "error" in rotation:
        return f"Sector Rotation: {rotation['error']}"

    hot = rotation.get("hot_sectors", [])
    cold = rotation.get("cold_sectors", [])
    signal = rotation.get("rotation_signal", "No signal")

    lines = ["Sector Rotation:"]
    if hot:
        lines.append(f"HOT: {', '.join(hot)} (focus here).")
    else:
        lines.append("HOT: None identified.")
    if cold:
        lines.append(f"COLD: {', '.join(cold)} (avoid or reduce).")
    else:
        lines.append("COLD: None identified.")
    lines.append(f"Signal: {signal}")

    return " ".join(lines)


def _format_macro_prose(macro: dict) -> str:
    """Convert macro metrics dict to natural prose."""
    if "error" in macro:
        return f"Global Macro: {macro['error']}"

    dxy = macro.get("dxy_value")
    dxy_sig = macro.get("dxy_signal", "UNKNOWN")
    vix = macro.get("vix_value")
    vix_sig = macro.get("vix_signal", "UNKNOWN")
    usd_vnd = macro.get("usd_vnd_rate")
    usd_vnd_sig = macro.get("usd_vnd_signal", "UNKNOWN")
    risk = macro.get("global_risk_regime", "UNKNOWN")
    interp = macro.get("interpretation", "")
    events = macro.get("upcoming_events", [])

    dxy_explain = {
        "STRONG": "pressure on EM flows",
        "WEAK": "favorable for EM",
        "NEUTRAL": "stable",
    }.get(dxy_sig, "")

    vix_explain = {
        "LOW": "risk appetite healthy",
        "MODERATE": "normal volatility",
        "HIGH": "elevated fear",
        "EXTREME": "panic mode",
    }.get(vix_sig, "")

    usd_explain = {
        "STABLE": "no currency stress",
        "PRESSURE": "mild capital outflow",
        "FLIGHT": "capital flight risk",
    }.get(usd_vnd_sig, "")

    risk_action = {
        "CALM": "Normal trading, all strategies valid.",
        "CAUTIOUS": "Reduce position sizes, tighter stops.",
        "ELEVATED": "Defensive stocks only, no growth longs.",
        "CRISIS": "Cash preservation, exits only.",
    }.get(risk, "")

    oil = macro.get("oil_price")
    oil_sig = macro.get("oil_signal", "")
    oil_change = macro.get("oil_change_pct")

    oil_explain = {
        "LOW": "cheap energy, favorable",
        "NORMAL": "stable",
        "ELEVATED": "inflationary pressure",
        "ELEVATED_SPIKE": "sudden spike, inflation risk",
        "EXTREME": "supply crisis",
        "EXTREME_SPIKE": "supply shock",
    }.get(oil_sig, "")

    lines = ["Global Macro Context:"]
    if dxy is not None:
        lines.append(f"DXY: {dxy:.1f} ({dxy_sig} - {dxy_explain}).")
    if vix is not None:
        lines.append(f"VIX: {vix:.1f} ({vix_sig} - {vix_explain}).")
    if usd_vnd is not None:
        lines.append(f"USD/VND: {usd_vnd:,.0f} ({usd_vnd_sig} - {usd_explain}).")
    if oil is not None:
        oil_str = f"Oil: {oil:.1f} USD/bbl"
        if oil_change is not None:
            oil_str += f" ({oil_change:+.2f}%)"
        if oil_sig:
            oil_str += f" ({oil_sig}"
            if oil_explain:
                oil_str += f" - {oil_explain}"
            oil_str += ")."
        else:
            oil_str += "."
        lines.append(oil_str)
    lines.append(f"Global Risk: {risk}. {risk_action}")
    if events:
        lines.append(f"Upcoming: {', '.join(events[:3])}.")
    if interp:
        lines.append(f"Context: {interp}")

    return " ".join(lines)


def _format_regime_history_prose(history: list) -> str:
    """Convert regime history list to natural prose."""
    if not history:
        return "No regime history available."

    if isinstance(history[0], dict) and "error" in history[0]:
        return f"Regime History: {history[0]['error']}"

    lines = [f"Regime History ({len(history)} days):"]
    for h in history[:5]:
        d = h.get("date", "?")
        r = h.get("regime", "?")
        c = h.get("confidence", 0)
        conf_str = f"{c * 100:.0f}%" if isinstance(c, (int, float)) else f"{c}%"
        lines.append(f"{d}: {r} ({conf_str})")

    return " ".join(lines)


def _format_macro_history_prose(history: list) -> str:
    """Convert macro history list to natural prose."""
    if not history:
        return "No macro history available."

    if isinstance(history[0], dict) and "error" in history[0]:
        return f"Macro History: {history[0]['error']}"

    lines = [f"Macro History ({len(history)} days):"]
    for h in history[:5]:
        d = h.get("date", "?")
        risk = h.get("global_risk_regime", "?")
        dxy = h.get("dxy_signal", "?")
        vix = h.get("vix_signal", "?")
        lines.append(f"{d}: {risk} (DXY:{dxy}, VIX:{vix})")

    return " ".join(lines)
