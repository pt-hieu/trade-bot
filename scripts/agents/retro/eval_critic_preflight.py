"""Deterministic pre-flight for retro_eval_critic.

Splits the 6-item critic checklist: 3 mechanical rules here (regex / set
lookup / table match), 3 qualitative rules (weak_insight, temporal_leak,
metric_misuse) left for the LLM. The LLM confirms / dismisses candidates
from this module and still owns open-vocabulary flagging for the others.
"""

from __future__ import annotations

import re
from typing import TypedDict

_NUMBER_THRESHOLD_RE = re.compile(r"\d+(?:\.\d+)?%?")
_CALIBRATION_CITATION_TOKENS = ("stop/ATR", "entry_gap", "stop_buffer")

# direction_correct × error_type coherence table.
# `True` in the `incoherent` cell means the combination is wrong by construction.
_ERROR_TYPE_DIRECTION_INCOHERENT: dict[tuple[bool, str], bool] = {
    (True, "ANALYSIS_ERROR"): True,
    (False, "VARIANCE"): True,
    (False, "EXECUTION_ERROR"): True,
}


class PreflightCandidate(TypedDict):
    """A single mechanical-rule candidate awaiting LLM confirmation."""

    ticker: str
    rule_id: str  # vague_lesson | missing_citation | error_type_mismatch
    note: str


def _has_number_or_threshold(text: str) -> bool:
    return bool(_NUMBER_THRESHOLD_RE.search(text or ""))


def _has_calibration_citation(text: str) -> bool:
    lower = (text or "").lower()
    return any(token.lower() in lower for token in _CALIBRATION_CITATION_TOKENS)


def check_vague_lesson(analysis: dict) -> PreflightCandidate | None:
    """Flag lessons with no digit/percent marker — LLM confirms whether a
    spelled-out number slipped past the regex."""
    lesson = (analysis.get("lesson") or "").strip()
    if not lesson:
        return None
    if _has_number_or_threshold(lesson):
        return None
    return {
        "ticker": analysis.get("ticker") or "?",
        "rule_id": "vague_lesson",
        "note": f"Lesson has no number/threshold: {lesson!r}",
    }


def check_missing_citation(analysis: dict) -> PreflightCandidate | None:
    """Flag CALIBRATION_ERROR analyses that don't cite stop/ATR, entry_gap, or stop_buffer."""
    if (analysis.get("error_type") or "").upper() != "CALIBRATION_ERROR":
        return None
    body = (analysis.get("analysis") or "") + " " + (analysis.get("lesson") or "")
    if _has_calibration_citation(body):
        return None
    return {
        "ticker": analysis.get("ticker") or "?",
        "rule_id": "missing_citation",
        "note": "CALIBRATION_ERROR lacks stop/ATR, entry_gap, or stop_buffer citation.",
    }


def check_error_type_mismatch(analysis: dict) -> PreflightCandidate | None:
    """Flag error_type values that are incoherent with the direction_correct hint."""
    error_type = (analysis.get("error_type") or "").upper()
    direction_correct = analysis.get("direction_correct")
    if direction_correct is None or not error_type:
        return None
    if not isinstance(direction_correct, bool):
        return None
    if _ERROR_TYPE_DIRECTION_INCOHERENT.get((direction_correct, error_type)):
        return {
            "ticker": analysis.get("ticker") or "?",
            "rule_id": "error_type_mismatch",
            "note": (
                f"error_type={error_type} is incoherent with direction_correct={direction_correct}"
            ),
        }
    return None


def run_preflight(analyses: list[dict]) -> list[PreflightCandidate]:
    """Apply all three mechanical rules to every analysis.

    The LLM receives this list and confirms / dismisses each candidate,
    AND keeps open-vocabulary flagging for the 3 qualitative rules
    (weak_insight, temporal_leak, metric_misuse).
    """
    checks = (check_vague_lesson, check_missing_citation, check_error_type_mismatch)
    candidates: list[PreflightCandidate] = []
    for analysis in analyses:
        if not isinstance(analysis, dict):
            continue
        for check in checks:
            candidate = check(analysis)
            if candidate is not None:
                candidates.append(candidate)
    return candidates


def format_preflight_candidates(candidates: list[PreflightCandidate]) -> str:
    """Render candidates as a compact block for the critic's user prompt."""
    if not candidates:
        return "No mechanical-rule candidates — pre-flight is clean."
    lines = [
        f"- [{candidate['rule_id']}] {candidate['ticker']}: {candidate['note']}"
        for candidate in candidates
    ]
    return "Pre-flight mechanical candidates (confirm or dismiss each):\n" + "\n".join(lines)
