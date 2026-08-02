#!/usr/bin/env python3
"""
Actionable rule generation and persistence from pattern extraction.

Extracted from patterns.py to stay under 300-line limit.
"""


def compute_actionable_rules(losing_patterns: list[dict]) -> list[dict]:
    """
    Generate concrete, machine-readable rule changes from high-loss patterns.

    Requires sample_size >= 10 and loss_rate >= 70% to be actionable.
    Skips patterns dominated by VARIANCE — bad luck, not a systemic flaw.
    Returns top 3 sorted by loss_rate descending.
    """
    candidates = [
        p
        for p in losing_patterns
        if p.get("sample_size", 0) >= 10 and p.get("loss_rate", 0) >= 0.7 and p.get("avoid_rule")
    ]
    candidates.sort(key=lambda p: p["loss_rate"], reverse=True)

    rules = []
    for p in candidates[:3]:
        dom_error = p.get("dominant_error", "N/A")
        loss_pct = round(p["loss_rate"] * 100)
        n = p["sample_size"]
        error_bd = p.get("error_breakdown", {})

        # VARIANCE-dominated losses: sound setup, bad luck — don't generate avoid rule
        if dom_error == "VARIANCE" and n >= 3:
            continue

        if dom_error == "ANALYSIS_ERROR":
            rule_text = (
                f"{p['avoid_rule']} [thesis errors: {error_bd.get('ANALYSIS_ERROR', 0)}/{n}]"
            )
            rule_type = "ADD_FILTER"
        elif dom_error == "EXECUTION_ERROR":
            rule_text = (
                f"Adjust stop/timing: {p['avoid_rule']} "
                f"[execution errors: {error_bd.get('EXECUTION_ERROR', 0)}/{n}]"
            )
            rule_type = "ADJUST_EXECUTION"
        elif dom_error == "CALIBRATION_ERROR":
            rule_text = (
                f"Adjust entry/stop/target levels: {p['avoid_rule']} "
                f"[calibration errors: {error_bd.get('CALIBRATION_ERROR', 0)}/{n}]"
            )
            rule_type = "ADJUST_LEVELS"
        else:
            rule_text = p["avoid_rule"]
            rule_type = "ADD_FILTER"

        rules.append(
            {
                "rule": rule_text,
                "evidence": f"n={n}, {loss_pct}% loss rate",
                "type": rule_type,
                "dominant_error": dom_error,
                "action": p.get("action", "UNKNOWN"),
            }
        )

    return rules


def build_avoid_rule_key(action: str, dominant_error: str) -> str:
    """Build a stable DB key for an avoid rule, independent of volatile percentages."""
    error_suffix = dominant_error if dominant_error != "N/A" else "GENERAL"
    return f"avoid:{action}:{error_suffix}"


async def persist_actionable_rules(actionable_rules: list[dict]) -> int:
    """Upsert actionable rules from pattern extraction into trading_rules table.

    Args:
        actionable_rules: List of {rule, evidence, type, dominant_error} dicts

    Returns:
        Number of rules successfully persisted.
    """
    if not actionable_rules:
        return 0

    from shared.neon.memory import upsert_trading_rule

    count = 0
    for r in actionable_rules:
        rule_text = r.get("rule", "")
        evidence = r.get("evidence", "")
        if not rule_text:
            continue

        # Derive sample size from evidence string "n=5, 70% loss rate"
        sample_size = None
        if evidence:
            try:
                n_part = [p for p in evidence.split(",") if "n=" in p]
                if n_part:
                    sample_size = int(n_part[0].strip().replace("n=", ""))
            except (ValueError, IndexError):
                pass

        # Derive confidence from loss rate in evidence
        confidence = 0.7  # default (threshold for actionable_rules)
        if evidence:
            try:
                rate_part = [p for p in evidence.split(",") if "%" in p]
                if rate_part:
                    rate_str = (
                        rate_part[0].strip().replace("% loss rate", "").replace("%", "").strip()
                    )
                    confidence = float(rate_str) / 100.0
            except (ValueError, IndexError):
                pass

        action = r.get("action", "UNKNOWN")
        dominant_error = r.get("dominant_error", "N/A")
        rule_name = build_avoid_rule_key(action, dominant_error)

        rule_id = await upsert_trading_rule(
            rule_name=rule_name,
            rule_type="avoid",
            description=rule_text,
            action="REDUCE_OR_SKIP",
            confidence=confidence,
            sample_size=sample_size,
        )
        if rule_id:
            count += 1

    if count:
        print(f"    Persisted {count} actionable rules to trading_rules table")
    return count
