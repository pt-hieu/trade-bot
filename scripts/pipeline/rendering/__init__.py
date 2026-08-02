"""Deterministic renderers for brief sections.

Pure Python, no LLM. Used after LLM sub-agents produce structured
decisions; renderers convert those decisions into the final brief prose.

Rationale: LLMs that author prose paraphrasing an upstream structured
decision drift (2026-04-15 pipeline review: synthesis_picks wrote
"HOLD FPT" despite synthesis_holdings choosing "TRIM 30% FPT"). Moving
the prose generation to Python eliminates paraphrase drift.
"""

from .models import HoldingAction, derive_holding_actions
from .my_holdings import render_my_holdings
from .what_to_do_today import render_what_to_do_today

__all__ = [
    "HoldingAction",
    "derive_holding_actions",
    "render_my_holdings",
    "render_what_to_do_today",
]
