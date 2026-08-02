"""Unit tests for synthesis output validation."""

from agents.synthesis import validate_synthesis_output

# ── Mode validation (existing behavior) ──────────────────────────────────


def test_no_warnings_for_normal_mode():
    """NORMAL mode should produce no warnings."""
    output = "TOP PICKS\nFPT: BUY\nEntry 80,000 | Stop 75,000 | Target 90,000"
    result, warnings = validate_synthesis_output(output, "NORMAL", 50_000_000)
    assert not warnings


def test_low_cash_blocks_buy():
    """LOW_CASH with 0 deployable should warn on BUY recs."""
    output = "TOP PICKS\nFPT: BUY\nEntry 80,000 | Stop 75,000 | Target 90,000"
    _, warnings = validate_synthesis_output(output, "LOW_CASH", 0)
    assert any("MODE VIOLATION" in w for w in warnings)


def test_reallocation_requires_exit():
    """REALLOCATION mode BUY requires EXIT in MY HOLDINGS."""
    output = (
        "MY HOLDINGS\nFPT: HOLD\n\nTOP PICKS\nVPB: BUY\nEntry 20,000 | Stop 18,000 | Target 25,000"
    )
    _, warnings = validate_synthesis_output(output, "REALLOCATION", 0)
    assert any("REALLOCATION" in w for w in warnings)


def test_reallocation_with_exit_no_warning():
    """REALLOCATION mode with EXIT should not warn."""
    output = (
        "MY HOLDINGS\nFPT: EXIT at 80,000\n\n"
        "TOP PICKS\nVPB: BUY\nEntry 20,000 | Stop 18,000 | Target 25,000"
    )
    _, warnings = validate_synthesis_output(output, "REALLOCATION", 0)
    assert not any("REALLOCATION" in w for w in warnings)


# ── Duplicate rationale detection ────────────────────────────────────────


def test_duplicate_rationale_detected():
    """Two tickers sharing identical rationale should produce a warning."""
    output = (
        "TOP PICKS\n"
        "VPB (Banking): WATCH\n"
        "Banks with strong CASA franchises favored over rate-sensitive lenders; benefits from FTSE upgrade\n\n"
        "MBB (Banking): WATCH\n"
        "Banks with strong CASA franchises favored over rate-sensitive lenders; benefits from FTSE upgrade\n\n"
        "SKIP THESE\nHPG: AVOID"
    )
    _, warnings = validate_synthesis_output(output, "NORMAL", 50_000_000)
    assert any("DUPLICATE RATIONALE" in w for w in warnings)
    assert any("VPB" in w and "MBB" in w for w in warnings)


def test_unique_rationales_no_warning():
    """Different rationales should produce no duplicate warning."""
    output = (
        "TOP PICKS\n"
        "VPB (Banking): BUY\n"
        "Entry 20,000 | Stop 18,000 | Target 25,000\n"
        "Strong CASA franchise with consumer lending upside from FE Credit recovery\n\n"
        "MBB (Banking): BUY\n"
        "Entry 25,000 | Stop 23,000 | Target 30,000\n"
        "Military-backed deposit stability with strong loan book growth in retail\n\n"
        "SKIP THESE\nHPG: AVOID"
    )
    _, warnings = validate_synthesis_output(output, "NORMAL", 50_000_000)
    assert not any("DUPLICATE RATIONALE" in w for w in warnings)


# ── Incomplete BUY validation ────────────────────────────────────────────


def test_buy_missing_stop():
    """BUY without stop should warn."""
    output = (
        "TOP PICKS\n"
        "FPT (Technology): BUY\n"
        "Entry 80,000 | Target 95,000\n"
        "Strong technical setup with momentum\n\n"
        "SKIP THESE\nHPG: AVOID"
    )
    _, warnings = validate_synthesis_output(output, "NORMAL", 50_000_000)
    assert any("INCOMPLETE BUY" in w and "FPT" in w and "stop" in w for w in warnings)


def test_buy_missing_all_levels():
    """BUY without any levels should warn with all missing."""
    output = (
        "TOP PICKS\n"
        "FPT (Technology): BUY\n"
        "Strong technical setup with momentum confirmation\n\n"
        "SKIP THESE\nHPG: AVOID"
    )
    _, warnings = validate_synthesis_output(output, "NORMAL", 50_000_000)
    assert any("INCOMPLETE BUY" in w and "entry" in w for w in warnings)


def test_buy_with_all_levels_no_warning():
    """BUY with entry/stop/target should not warn."""
    output = (
        "TOP PICKS\n"
        "FPT (Technology): BUY\n"
        "Entry 80,000 | Stop 75,000 | Target 95,000 | R:R 3.0\n"
        "Strong technical setup with momentum\n\n"
        "SKIP THESE\nHPG: AVOID"
    )
    _, warnings = validate_synthesis_output(output, "NORMAL", 50_000_000)
    assert not any("INCOMPLETE BUY" in w for w in warnings)


def test_watch_without_entry_no_error():
    """WATCH without entry should log info but not produce a warning."""
    output = (
        "TOP PICKS\n"
        "VPB (Banking): WATCH\n"
        "Monitoring for pullback to support zone\n\n"
        "SKIP THESE\nHPG: AVOID"
    )
    _, warnings = validate_synthesis_output(output, "NORMAL", 50_000_000)
    # WATCH without entry is info-level, not a warning
    assert not any("VPB" in w for w in warnings)


# ── Edge cases ───────────────────────────────────────────────────────────


def test_empty_output():
    """Empty output should return no warnings."""
    _, warnings = validate_synthesis_output("", "NORMAL", 50_000_000)
    assert not warnings


def test_no_top_picks_section():
    """Output without TOP PICKS should return no warnings."""
    output = "MY HOLDINGS\nFPT: HOLD\nTCB: HOLD"
    _, warnings = validate_synthesis_output(output, "NORMAL", 50_000_000)
    assert not warnings


def test_none_mode():
    """None mode should return no warnings."""
    output = "TOP PICKS\nFPT: BUY\nEntry 80,000 | Stop 75,000 | Target 95,000"
    _, warnings = validate_synthesis_output(output, None, None)
    assert not warnings


# ── Bug 8 (run2 2026-05-14): ATR_TRAIL picks exempt from "missing target" ──
# 5th recurrence of the ATR_TRAIL text-coupling defect class. The validator
# now reads the structured exit-family via the SWI-340 SSOT predicate
# `is_trailing_exit` instead of text-grepping for the word "TARGET".


def test_atr_trail_buy_not_flagged_missing_target():
    """An ATR_TRAIL pick legitimately carries no fixed target — its TOP
    PICKS block (LLM producer shape, no `Target` word) must NOT produce an
    INCOMPLETE BUY warning when `pre_computed_picks` marks it trailing."""
    output = (
        "TOP PICKS\n"
        "VRE (real-estate) BUY\n"
        "Entry 28,500 | Stop 26,100 | Exit Trail 2.5x ATR from peak (hard stop 24,000)\n"
        "Breakout with ADX confirmation\n\n"
        "SKIP THESE\nHPG: AVOID"
    )
    pre_computed_picks = [{"ticker": "VRE", "exit_family": "ATR_TRAIL", "target": None}]
    _, warnings = validate_synthesis_output(
        output, "NORMAL", 50_000_000, pre_computed_picks=pre_computed_picks
    )
    assert not any("INCOMPLETE BUY" in w for w in warnings)


def test_fixed_target_buy_still_flagged_when_target_missing():
    """A FIXED_TARGET pick whose block genuinely lacks a target is still
    flagged — the exemption is scoped to trailing picks only."""
    output = (
        "TOP PICKS\n"
        "VCB (banking) BUY\n"
        "Entry 85,500 | Stop 80,000\n"
        "Value re-rating underway\n\n"
        "SKIP THESE\nHPG: AVOID"
    )
    pre_computed_picks = [{"ticker": "VCB", "exit_family": "FIXED_TARGET", "target": 95000}]
    _, warnings = validate_synthesis_output(
        output, "NORMAL", 50_000_000, pre_computed_picks=pre_computed_picks
    )
    assert any("INCOMPLETE BUY" in w and "VCB" in w and "target" in w for w in warnings)


def test_atr_trail_exemption_noop_without_pre_computed_picks():
    """Backward-compatible default: with no `pre_computed_picks` the
    incomplete-BUY check behaves exactly as before."""
    output = (
        "TOP PICKS\n"
        "VRE (real-estate) BUY\n"
        "Entry 28,500 | Stop 26,100\n"
        "Breakout setup\n\n"
        "SKIP THESE\nHPG: AVOID"
    )
    _, warnings = validate_synthesis_output(output, "NORMAL", 50_000_000)
    assert any("INCOMPLETE BUY" in w and "VRE" in w for w in warnings)
