"""
Pure string formatting functions for synthesis output.

No agent, no async, no LLM dependencies.
"""

from __future__ import annotations

from shared.rules.exit_strategy import is_trailing_exit
from shared.rules.rr_floors import BORDERLINE_RR_EPSILON

_CONTRACT_VIOLATION_MSG = "fixed-target contract violation (target or R:R missing)"


def _fixed_target_contract_broken(target, rr_raw) -> bool:
    """Mirrors the validator's exit-contract gate for a non-trailing pick (SWI-340)."""
    return target is None or rr_raw is None or rr_raw <= 0


def _format_pre_computed_picks_fallback(
    pre_computed_picks: list[dict] | None,
    sector_results: list[str],
) -> str:
    """Format pre-computed picks as plain text when synthesis_picks times out."""
    lines = ["TOP PICKS"]
    if pre_computed_picks:
        for pick in pre_computed_picks:
            ticker = pick.get("ticker") or ""
            entry = pick.get("entry") or 0
            stop = pick.get("stop") or 0
            target = pick.get("target")
            rr_raw = pick.get("risk_reward")
            action = pick.get("action") or "BUY"
            lines.append(f"{ticker} ({action})")
            lines.append(f"Entry: {entry:,.0f}")
            lines.append(f"Stop: {stop:,.0f}")
            if is_trailing_exit(pick):
                lines.append("Target: trailing stop (ATR_TRAIL)")
                lines.append("R:R: trailing — no fixed target")
            elif _fixed_target_contract_broken(target, rr_raw):
                lines.append(f"Pick excluded: {_CONTRACT_VIOLATION_MSG}")
            else:
                lines.append(f"Target: {target:,.0f}")
                lines.append(f"R:R {rr_raw:.1f}")
            lines.append(pick.get("note") or "Pre-computed pick — synthesis timed out")
            lines.append("")
    else:
        lines.append("No pre-computed picks available")
    # SKIP THESE and WHAT TO DO TODAY are rendered deterministically
    # downstream in scripts/agents/synthesis.py (render_skip_these,
    # render_what_to_do_today). Emitting stubs here causes sections to
    # appear twice in the brief on fallback path.
    return "\n".join(lines)


def _format_rr_with_precision(rr: float, floor: float | None = None) -> str:
    """Display R:R at 1 decimal, or 2 decimals when borderline against an active floor."""
    if floor is not None and abs(rr - floor) < BORDERLINE_RR_EPSILON:
        return f"{rr:.2f}"
    return f"{rr:.1f}"


def _format_expectancy_header(
    rolling_win_rate: float | None,
    expectancy_floor: float | None,
) -> str | None:
    """One-line expectancy context for the LLM.

    Surfaces the rolling win rate and the derived R:R floor so the agent can
    qualitatively interpret why borderline picks are being filtered. The
    arithmetic itself stays in Python (deterministic-calc rule).
    """
    if rolling_win_rate is None and expectancy_floor is None:
        return None
    parts = ["## EXPECTANCY CONTEXT"]
    if rolling_win_rate is not None:
        wr_pct = rolling_win_rate * 100 if rolling_win_rate <= 1 else rolling_win_rate
        # Compute expected R per trade at the active floor for intuition.
        if expectancy_floor is not None and rolling_win_rate > 0:
            wr = rolling_win_rate if rolling_win_rate <= 1 else rolling_win_rate / 100
            expected_r = wr * expectancy_floor - (1 - wr)
            parts.append(
                f"- Rolling win rate: {wr_pct:.0f}% — at the active floor "
                f"({expectancy_floor:.1f} R:R), expected value ≈ {expected_r:+.2f}R per trade"
            )
        else:
            parts.append(f"- Rolling win rate: {wr_pct:.0f}%")
    if expectancy_floor is not None:
        parts.append(
            f"- Expectancy floor: {expectancy_floor:.1f} R:R minimum required for E ≥ 0.3R"
        )
    return "\n".join(parts)


def _format_pre_computed_picks(picks: list[dict], min_rr_floor: float | None = None) -> str:
    """Format pre-computed picks as context for synthesis agent.

    Shows deterministic net-of-cost R:R with target provenance
    (conservative vs aggressive) and optional stretch hint. Never surfaces
    dual R:R candidates — the chooser already picked one.
    """
    if not picks:
        return ""
    lines = ["## PRE-COMPUTED TOP PICK CANDIDATES (validated R:R from real levels)"]
    for pick in picks:
        action = pick.get("action", "BUY")
        line = f"{pick['ticker']} ({action}) ({pick['sector']}): Entry {pick['entry']:,.0f} | Stop {pick['stop']:,.0f}"

        rr_raw = pick.get("risk_reward")
        rr_gross = pick.get("risk_reward_gross")
        target_basis = pick.get("target_basis") or "conservative"
        rr_stretch = pick.get("rr_stretch")
        verdict = pick.get("verdict") or "full_size"

        target_val = pick.get("target")
        if is_trailing_exit(pick):
            line += "\n  Target: trailing stop (ATR_TRAIL) — no fixed R:R"
        elif _fixed_target_contract_broken(target_val, rr_raw):
            line += f"\n  Target: pick excluded — {_CONTRACT_VIOLATION_MSG}"
        else:
            assert target_val is not None and rr_raw is not None  # narrowed by helper above
            target_label = (
                "Aggressive (swing_high)" if target_basis == "aggressive" else "Conservative (R1)"
            )
            rr_display = _format_rr_with_precision(rr_raw, min_rr_floor)
            line += (
                f"\n  Target: {target_val:,.0f} [{target_label}] -> R:R {rr_display} (net of cost)"
            )
            if rr_gross is not None and abs(rr_gross - rr_raw) > 0.05:
                line += f" | gross {rr_gross:.1f}"
            if rr_stretch is not None and rr_stretch > rr_raw:
                line += f"\n  Stretch target if momentum extends: R:R {rr_stretch:.1f}"
        line += f"\n  Verdict: {verdict} | Shares {pick['shares']}"
        if action == "LIMIT_BUY":
            gap = pick.get("gap_from_support_pct") or 0
            limit_market_rr = pick.get("market_rr") or 0
            line += f"\n  LIMIT ORDER: price is {gap:.1f}% above entry. Market R:R only {limit_market_rr:.1f}. Needs pullback to fill."
        line += f"\n  Note: {pick.get('note') or ''}"

        # Volume confirmation
        volume_vs_avg = pick.get("volume_vs_avg")
        pattern_name = pick.get("pattern_name")
        if pattern_name and volume_vs_avg is not None:
            confirmed = "[OK]" if pick.get("volume_confirmed") else "[LOW conviction]"
            line += f"\n  Pattern: {pattern_name} on {volume_vs_avg:.1f}x avg volume {confirmed}"
        elif pattern_name:
            line += f"\n  Pattern: {pattern_name}"

        # Exit plan
        exit_plan = pick.get("exit_plan")
        if exit_plan and exit_plan.get("legs"):
            for leg in exit_plan["legs"]:
                leg_line = f"  Leg {leg['leg']}: {leg['action']}"
                if leg.get("stop_adjust"):
                    leg_line += f", {leg['stop_adjust']}"
                if leg.get("trailing_stop"):
                    leg_line += f", {leg['trailing_stop']}"
                line += f"\n{leg_line}"
            line += f"\n  Time stop: {exit_plan.get('time_stop', '')}"

        lines.append(line)
    return "\n".join(lines)
