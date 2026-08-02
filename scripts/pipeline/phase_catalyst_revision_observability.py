"""Logfire probes for catalyst strategy revision (SWI-57).

Pulled out of ``phase_catalyst_revision`` so that file stays under the
350-LOC cap. Pure helpers — no DB, no LLM.
"""

from __future__ import annotations

import re
from datetime import date

from shared.observability import log_info

_FIDELITY_MIN_KEY_LEN = 4
_FIDELITY_STOPWORDS = {"the", "and", "for", "buy", "sell", "vn", "vnindex"}


def emit_revision_lexical_fidelity(
    *,
    scan_date: date,
    changed_catalysts: list[dict] | None,
    revised_strategy: str | None,
) -> None:
    """Emit lexical word-boundary fidelity ratio (Logfire-only).

    Compares trigger catalyst keys against the revised strategy body. Lexical
    matching only — see SWI-230 for the LLM-side acknowledged_keys follow-up.
    """
    trigger_keys = {
        (c.get("catalyst_key") or c.get("event") or "").lower()
        for c in (changed_catalysts or [])
        if c.get("catalyst_key") or c.get("event")
    }
    trigger_keys = {
        k for k in trigger_keys if len(k) >= _FIDELITY_MIN_KEY_LEN and k not in _FIDELITY_STOPWORDS
    }
    body = (revised_strategy or "").lower()
    matched = {k for k in trigger_keys if re.search(rf"\b{re.escape(k)}\b", body)}
    denom = len(trigger_keys) or 1
    log_info(
        "catalyst_revision_fidelity",
        lexical_fidelity_ratio=round(len(matched) / denom, 3) if trigger_keys else 0.0,
        metric_kind="lexical",
        trigger_count=len(trigger_keys),
        matched_count=len(matched),
        scan_date=str(scan_date),
    )
