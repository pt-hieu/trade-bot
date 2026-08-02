"""Unit tests for reversal conviction cap in belief persistence."""

import sys
from pathlib import Path

# Add scripts/ to path for direct imports
_SCRIPTS = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from shared.neon.beliefs import REVERSAL_CONVICTION_CAP, _apply_reversal_penalty


class TestApplyReversalPenalty:
    """_apply_reversal_penalty caps conviction for REVERSED beliefs."""

    def test_reversed_above_cap_gets_capped(self):
        belief = {"conviction": 0.85, "agent_key": "test", "ticker": "FPT"}
        _apply_reversal_penalty(belief, "REVERSED")
        assert belief["conviction"] == REVERSAL_CONVICTION_CAP

    def test_reversed_below_cap_unchanged(self):
        belief = {"conviction": 0.4, "agent_key": "test", "ticker": "FPT"}
        _apply_reversal_penalty(belief, "REVERSED")
        assert belief["conviction"] == 0.4

    def test_reversed_at_cap_unchanged(self):
        belief = {"conviction": 0.6, "agent_key": "test", "ticker": "FPT"}
        _apply_reversal_penalty(belief, "REVERSED")
        assert belief["conviction"] == 0.6

    def test_reaffirmed_not_penalized(self):
        belief = {"conviction": 0.9, "agent_key": "test", "ticker": "FPT"}
        _apply_reversal_penalty(belief, "REAFFIRMED")
        assert belief["conviction"] == 0.9

    def test_new_not_penalized(self):
        belief = {"conviction": 0.85, "agent_key": "test", "ticker": "FPT"}
        _apply_reversal_penalty(belief, "NEW")
        assert belief["conviction"] == 0.85

    def test_updated_not_penalized(self):
        belief = {"conviction": 0.8, "agent_key": "test", "ticker": "FPT"}
        _apply_reversal_penalty(belief, "UPDATED")
        assert belief["conviction"] == 0.8

    def test_missing_conviction_uses_default(self):
        belief = {"agent_key": "test", "ticker": "FPT"}
        _apply_reversal_penalty(belief, "REVERSED")
        # Default 0.5 < cap 0.6, so unchanged
        assert (
            "conviction" not in belief or belief.get("conviction", 0.5) <= REVERSAL_CONVICTION_CAP
        )

    def test_cap_value_is_0_6(self):
        assert REVERSAL_CONVICTION_CAP == 0.6
