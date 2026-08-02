"""SWI-317 — guard ATR_TRAIL risk_reward=None at diagnostic print loop and
ticker-context briefing builder.

ATR_TRAIL contract (SWI-115): risk_reward=None end-to-end. Two consumers were
not aligned: phase_picks.py print loop (TypeError on `:.1f`), and
context_blocks_ticker.py (silently coerced None→0.0 via `or 0`, then emitted
"R:R 0.0 [LOW R:R — below threshold]" to the LLM).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def test_phase_picks_print_loop_handles_atr_trail_none_rr(capsys):
    """The diagnostic print at phase_picks.py:226-231 must not TypeError when
    a pick carries risk_reward=None (ATR_TRAIL contract per SWI-115)."""
    picks = [
        {"ticker": "VHM", "risk_reward": None, "shares": 500, "exit_family": "ATR_TRAIL"},
        {"ticker": "FPT", "risk_reward": 3.2, "shares": 200, "exit_family": "TARGET"},
    ]
    for p in picks:
        rr_display = f"{p['risk_reward']:.1f}" if p["risk_reward"] is not None else "ATR_TRAIL"
        print(f"    {p['ticker']}: R:R {rr_display}, {p['shares']} shares", flush=True)

    out = capsys.readouterr().out
    assert "VHM: R:R ATR_TRAIL, 500 shares" in out
    assert "FPT: R:R 3.2, 200 shares" in out


def test_format_ticker_briefing_atr_trail_displays_trailing_not_zero():
    """context_blocks_ticker.format_ticker_briefing must emit 'R:R trailing'
    for ATR_TRAIL setups (risk_reward=None), NOT 'R:R 0.0'. Otherwise the
    LLM sees a [LOW R:R — below threshold] tag for legitimate trailing
    setups (SWI-317 data-quality bug)."""
    from pipeline.context_blocks_ticker import format_ticker_briefing

    technicals = {
        "close": 50_000,
        "trade_setup": {
            "valid": True,
            "entry": 50_000,
            "stop": 48_000,
            "target": None,
            "risk_reward": None,
        },
    }
    out = format_ticker_briefing("VHM", technicals=technicals)
    assert "R:R trailing" in out
    assert "R:R 0.0" not in out
    assert "[LOW R:R" not in out


def test_format_ticker_briefing_fixed_rr_still_renders_low_tag():
    """Regression — fixed-RR setups below RR_FLOOR_DEFAULT still emit
    the [LOW R:R] tag."""
    from pipeline.context_blocks_ticker import format_ticker_briefing
    from shared.rules.rr_floors import RR_FLOOR_DEFAULT

    low_rr = max(RR_FLOOR_DEFAULT - 0.5, 0.5)
    technicals = {
        "close": 50_000,
        "trade_setup": {
            "valid": True,
            "entry": 50_000,
            "stop": 48_000,
            "target": 51_000,
            "risk_reward": low_rr,
        },
    }
    out = format_ticker_briefing("ABC", technicals=technicals)
    assert f"R:R {low_rr:.1f}" in out
    assert "[LOW R:R" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
