"""Unit tests for inter-day drift detection."""

from agents.tools.interday import detect_interday_drifts, extract_position_recommendations

# ── extract_position_recommendations ──────────────────────────────────────


def test_extract_recs_basic():
    """Parse basic MY HOLDINGS section."""
    brief = """
TODAY'S THEME
Market is recovering.

MY HOLDINGS
- FPT: HOLD — trending above MA20, stop=115k
- VHM: EXIT — thesis broken, stop=80k

TOP PICKS
- HPG: BUY at 22k
"""
    recs = extract_position_recommendations(brief)
    assert "FPT" in recs
    assert recs["FPT"]["action"] == "HOLD"
    assert "VHM" in recs
    assert recs["VHM"]["action"] == "EXIT"


def test_extract_recs_with_trim():
    """Parse TRIM action."""
    brief = """
MY HOLDINGS
- TCB: TRIM — take 50% profit at resistance, stop=31k
TOP PICKS
"""
    recs = extract_position_recommendations(brief)
    assert "TCB" in recs
    assert recs["TCB"]["action"] == "TRIM"


def test_extract_recs_no_holdings():
    """Return empty dict if no MY HOLDINGS section."""
    brief = "TOP PICKS\n- FPT: BUY\n"
    recs = extract_position_recommendations(brief)
    assert recs == {}


def test_extract_recs_empty_brief():
    """Return empty dict for empty brief."""
    assert extract_position_recommendations("") == {}
    assert extract_position_recommendations(None) == {}


def test_extract_recs_stop_parsing():
    """Extract stop level from recommendation line."""
    brief = """
MY HOLDINGS
- FPT: HOLD — above support, stop=115000
TOP PICKS
"""
    recs = extract_position_recommendations(brief)
    assert "FPT" in recs
    # stop should be extracted
    assert recs["FPT"]["stop"] is not None


# ── detect_interday_drifts ─────────────────────────────────────────────────


def _make_brief(holdings_section: str) -> str:
    return f"TODAY'S THEME\nTest.\n\nMY HOLDINGS\n{holdings_section}\n\nTOP PICKS\n"


def test_detect_exit_to_trim_drift():
    """EXIT yesterday → TRIM today = drift detected."""
    prev = _make_brief("- VHM: EXIT — momentum broken\n")
    today = _make_brief("- VHM: TRIM — taking partial profits\n")
    drifts = detect_interday_drifts(today, prev)
    assert any("[interday_drift]" in d and "VHM" in d for d in drifts)


def test_detect_exit_to_hold_drift():
    """EXIT yesterday → HOLD today = drift detected."""
    prev = _make_brief("- VHM: EXIT — below MA20\n")
    today = _make_brief("- VHM: HOLD — waiting for confirmation\n")
    drifts = detect_interday_drifts(today, prev)
    assert any("[interday_drift]" in d and "VHM" in d for d in drifts)


def test_detect_trim_to_hold_drift():
    """TRIM yesterday → HOLD today = drift detected."""
    prev = _make_brief("- TCB: TRIM — near resistance\n")
    today = _make_brief("- TCB: HOLD — consolidating\n")
    drifts = detect_interday_drifts(today, prev)
    assert any("[interday_drift]" in d and "TCB" in d for d in drifts)


def test_no_drift_hold_to_hold():
    """HOLD → HOLD is not a drift."""
    prev = _make_brief("- FPT: HOLD — trending up\n")
    today = _make_brief("- FPT: HOLD — still above MA20\n")
    drifts = detect_interday_drifts(today, prev)
    assert not any("[interday_drift]" in d and "FPT" in d for d in drifts)


def test_no_drift_exit_to_exit():
    """EXIT → EXIT is consistent, no drift."""
    prev = _make_brief("- VHM: EXIT — below support\n")
    today = _make_brief("- VHM: EXIT — confirmed breakdown\n")
    drifts = detect_interday_drifts(today, prev)
    assert not any("[interday_drift]" in d and "VHM" in d for d in drifts)


def test_detect_unfollowed_exit():
    """EXIT yesterday, ticker still in holdings today = unfollowed exit."""
    prev = _make_brief("- VHM: EXIT — thesis broken\n")
    today = _make_brief("- FPT: HOLD — trending\n")  # VHM not in today's brief
    holdings = [{"ticker": "VHM", "plan_type": "SWING", "shares": 100, "avg_cost": 80000}]
    drifts = detect_interday_drifts(today, prev, current_holdings=holdings)
    assert any("[unfollowed_exit]" in d and "VHM" in d for d in drifts)


def test_no_unfollowed_exit_when_position_closed():
    """EXIT yesterday + not in holdings today = position was likely closed."""
    prev = _make_brief("- VHM: EXIT — thesis broken\n")
    today = _make_brief("- FPT: HOLD — trending\n")
    holdings = [{"ticker": "FPT", "plan_type": "SWING", "shares": 100, "avg_cost": 100000}]
    drifts = detect_interday_drifts(today, prev, current_holdings=holdings)
    assert not any("[unfollowed_exit]" in d and "VHM" in d for d in drifts)


def test_empty_briefs():
    """Empty briefs return no drifts."""
    drifts = detect_interday_drifts("", "some prev brief")
    assert drifts == []
    drifts = detect_interday_drifts("some brief", "")
    assert drifts == []
    drifts = detect_interday_drifts(None, None)
    assert drifts == []


def test_no_overlap_tickers():
    """Different tickers in each brief = no drifts."""
    prev = _make_brief("- FPT: EXIT — breakdown\n")
    today = _make_brief("- VHM: HOLD — consolidating\n")
    drifts = detect_interday_drifts(today, prev)
    assert not any("[interday_drift]" in d for d in drifts)
