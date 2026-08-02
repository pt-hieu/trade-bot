"""Tests for midday.formatter.format_afternoon_plan_prose (migration 316)."""

from midday.formatter import format_afternoon_plan_prose


def test_empty_list_returns_na():
    assert format_afternoon_plan_prose([]) == "N/A"


def test_none_returns_na():
    assert format_afternoon_plan_prose(None) == "N/A"


def test_single_ticker_action_renders():
    plan = [{"ticker": "FPT", "action": "HOLD", "confidence": "HIGH", "reason": "above 20-EMA"}]
    assert format_afternoon_plan_prose(plan) == "- HOLD FPT [HIGH]: above 20-EMA"


def test_legacy_null_ticker_seed_renders_without_ticker():
    """Migration 316 seeded legacy rows with ticker=None — prose must not print 'None'."""
    plan = [{"ticker": None, "action": "NOTE", "confidence": "LOW", "reason": "legacy note"}]
    assert format_afternoon_plan_prose(plan) == "- NOTE [LOW]: legacy note"


def test_missing_reason_falls_back_to_placeholder():
    plan = [{"ticker": "VHM", "action": "TRIM", "confidence": "MEDIUM", "reason": ""}]
    assert format_afternoon_plan_prose(plan) == "- TRIM VHM [MEDIUM]: (no reason provided)"


def test_multiple_entries_render_as_bullets():
    plan = [
        {"ticker": "FPT", "action": "HOLD", "confidence": "HIGH", "reason": "trend intact"},
        {"ticker": "VHM", "action": "EXIT", "confidence": "HIGH", "reason": "stop breached"},
    ]
    result = format_afternoon_plan_prose(plan)
    assert result.startswith("- HOLD FPT [HIGH]: trend intact")
    assert "- EXIT VHM [HIGH]: stop breached" in result


def test_note_appended_after_entries():
    plan = [{"ticker": "FPT", "action": "HOLD", "confidence": "HIGH", "reason": "trend intact"}]
    result = format_afternoon_plan_prose(plan, note="Flat tape, wait for close.")
    assert result.endswith("Flat tape, wait for close.")
    assert "- HOLD FPT" in result


def test_note_only_no_entries():
    result = format_afternoon_plan_prose([], note="Defer to morning plan.")
    assert result == "Defer to morning plan."


def test_malformed_entries_skipped():
    plan = [
        "not-a-dict",
        {"ticker": "FPT", "action": "HOLD", "confidence": "HIGH", "reason": "ok"},
        None,
    ]
    assert format_afternoon_plan_prose(plan) == "- HOLD FPT [HIGH]: ok"


def test_uppercases_action_and_confidence():
    plan = [{"ticker": "fpt", "action": "hold", "confidence": "high", "reason": "x"}]
    # Ticker is not uppercased (source of truth is DB), but action/confidence are.
    assert format_afternoon_plan_prose(plan) == "- HOLD fpt [HIGH]: x"
