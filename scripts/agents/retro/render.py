"""Deterministic prefixes for retro per-ticker analyses.

Python writes the rule + execution prefix from authoritative structural
data; the LLM's qualitative addendum follows. See SWI-135 / SWI-255.

`format_execution_prefix` lives in `shared/narrative/` because executed-vs-
not-executed is generic; `format_rule_prefix` lives here because it is
retro-specific (driven off `RetroRule`).
"""

from __future__ import annotations

from shared.narrative import format_execution_prefix, format_price_prefix
from shared.rules.retro_rule_classifier import RetroRule


def _safe_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _safe_int(value: object, default: int = 0) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    return default


def format_rule_prefix(rule_applied: RetroRule, eval_row: dict) -> str:
    """Render `rule_applied` into one authoritative sentence.

    Covers all 16 `RetroRule` literals. Adding a new RetroRule MUST add a
    branch here — the parametrized exhaustiveness test in
    `tests/unit/test_retro_render_prefixes.py` enforces this at CI time
    (pyright is in `basic` mode and does not enforce match-exhaustive).
    """
    day = _safe_float(eval_row.get("day_change"))
    pnl = _safe_float(eval_row.get("pnl_percent"))
    actual_pl = _safe_float(eval_row.get("actual_pl_pct"))
    actual_exit = _safe_int(eval_row.get("actual_exit_price_vnd"))

    if rule_applied == "LONGTERM_THESIS_INTACT":
        return f"LONGTERM thesis intact: day_change={day:+.1f}% within structural variance."
    if rule_applied == "LONGTERM_CATASTROPHIC":
        return f"LONGTERM catastrophic: pnl_percent={pnl:+.1f}% at/below floor."
    if rule_applied == "LONGTERM_EXCLUDED":
        return "LONGTERM excluded from win/loss tally."
    if rule_applied == "SWING_TARGET_HIT":
        return f"SWING target hit: P/L={pnl:+.1f}% at target."
    if rule_applied == "SWING_STOPPED":
        return f"SWING stop breached: stop_hit=True, P/L={pnl:+.1f}%."
    if rule_applied == "SWING_HOLD":
        verdict = "passed" if day > 0 else "failed"
        return f"SWING HOLD: day_change={day:+.1f}% — strict-positive rule {verdict}."
    if rule_applied == "SWING_WIN":
        return f"SWING win: day_change={day:+.1f}%, P/L={pnl:+.1f}%."
    if rule_applied == "SWING_LOSS":
        return f"SWING loss: day_change={day:+.1f}%, P/L={pnl:+.1f}%."
    if rule_applied == "SWING_PENDING":
        return f"SWING pending: position open, day_change={day:+.1f}%."
    if rule_applied == "SWING_MISSED":
        return "SWING signal not entered today."
    if rule_applied == "TRADE_EXECUTED_WIN":
        return f"Trade executed (win): actual_pl_pct={actual_pl:+.2f}%, exit={actual_exit:,}VND."
    if rule_applied == "TRADE_EXECUTED_LOSS":
        return f"Trade executed (loss): actual_pl_pct={actual_pl:+.2f}%, exit={actual_exit:,}VND."
    if rule_applied == "WATCH_MISS":
        outcome = "win" if day > 0 else "loss"
        return f"WATCH ticker — outcome would have been a {outcome}."
    if rule_applied == "WAIT_UNMET":
        return "WAIT criteria unmet — no entry signal fired."
    if rule_applied == "SKIP_CORRECT":
        return "SKIP correct — outcome confirms avoidance."
    if rule_applied == "UNCLASSIFIED":
        return "Unclassified evaluation; review row manually."

    # Pyright basic mode does not enforce match-exhaustive; raise so tests
    # catch a missing branch when a new RetroRule literal is added.
    raise AssertionError(f"format_rule_prefix: unhandled rule {rule_applied!r}")


def build_deterministic_prefixes_block(pre_evals: list[dict]) -> str:
    """Render rule + execution prefixes for every ticker as a markdown block.

    Used by the quarantine path (SWI-255) when the LLM draft fails the
    validator: deterministic truth survives even when prose is rejected.
    """
    lines: list[str] = ["## DETERMINISTIC PREFIXES (rule + execution truth)"]
    for e in pre_evals:
        rule_applied = e.get("rule_applied") or "UNCLASSIFIED"
        rule_prefix = format_rule_prefix(rule_applied, e)
        execution_prefix = format_execution_prefix(e)
        lines.append(f"- **{e.get('ticker', '?')}**: {rule_prefix} {execution_prefix}")
    return "\n".join(lines)


def stamp_deterministic_prefix(eval_row: dict, llm_text: str) -> str:
    """Prepend rule + execution (+ price) prefixes to the LLM's qualitative text.

    Python owns the rule citation, execution claim, and — for non-executed
    rows — the EOD/prev-close stamp. LLM addendum follows. Ordering:
    rule prefix → execution prefix → price prefix (HOLD only) → LLM text.
    SWI-135 (rule prefix), SWI-255 (execution prefix + price prefix).
    """
    rule_applied = eval_row.get("rule_applied") or "UNCLASSIFIED"
    rule_prefix = format_rule_prefix(rule_applied, eval_row)
    execution_prefix = format_execution_prefix(eval_row)
    parts = [rule_prefix, execution_prefix]
    if not eval_row.get("trade_executed"):
        price_prefix = format_price_prefix(eval_row)
        if price_prefix:
            parts.append(price_prefix)
    parts.append(llm_text)
    return " ".join(p for p in parts if p).strip()


__all__ = [
    "build_deterministic_prefixes_block",
    "format_rule_prefix",
    "stamp_deterministic_prefix",
]
