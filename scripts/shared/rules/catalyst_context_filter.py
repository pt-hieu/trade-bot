"""Catalyst-context filter — LLM-INJECTION ONLY.

SWI-20: every prompt that injects active catalysts gets the same
deterministic gate. NEVER use this for dedup or article matching —
those paths consume the full active set on purpose. The dedup pre-check
in ``agents/catalysts.py`` and the article-match loop in
``pipeline/catalyst_news_check.py`` deliberately skip this helper.

Rules (OR-joined; permissive on purpose per
``feedback_failure_mode_asymmetry.md`` — "not trading is expensive"):

  (a) universe-relevant — any affected_ticker overlaps ``universe`` or
      the catalyst is market-wide (VN-INDEX placeholder).
  (b) materially confident — confidence in {"HIGH", "MEDIUM"}.
  (c) imminent — status == "imminent".

Sort by (impact rank, confidence rank, days_until ASC). Slice to ``cap``.
"""

from __future__ import annotations

from datetime import date, datetime

ExpectedDate = str | date | datetime | None

VN_INDEX_PLACEHOLDER = "VN-INDEX"

_IMPACT_RANK = {
    "HIGH": 0,
    "POSITIVE": 1,
    "NEGATIVE": 1,
    "MEDIUM": 2,
    "WATCH": 3,
    "LOW": 3,
    "NEUTRAL": 4,
}
_CONFIDENCE_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _days_until(value: ExpectedDate) -> int:
    if value is None:
        return 9999
    if isinstance(value, date) and not isinstance(value, datetime):
        return (value - date.today()).days
    if isinstance(value, datetime):
        return (value.date() - date.today()).days
    try:
        return (datetime.strptime(str(value), "%Y-%m-%d").date() - date.today()).days
    except (ValueError, TypeError):
        return 9999


def _affected_tickers(catalyst: dict) -> list[str]:
    return list(catalyst.get("affected_tickers") or catalyst.get("affected") or [])


def filter_catalyst_context(
    catalysts: list[dict],
    universe: set[str],
    cap: int = 7,
) -> list[dict]:
    """Filter active catalysts to the slice worth injecting into a prompt.

    Args:
        catalysts: full list of active-catalyst dicts (raw shape from
            ``get_active_catalysts_db`` or the ``get_active_catalysts``
            view dict; both carry ``affected_tickers``/``affected``,
            ``impact``, ``confidence``, ``status``, ``expected``).
        universe: set of tickers the calling agent cares about. Empty
            set still surfaces market-wide / HIGH+MEDIUM / imminent
            catalysts (rule b/c).
        cap: maximum entries returned.
    """
    kept: list[dict] = []
    for catalyst in catalysts:
        affected = _affected_tickers(catalyst)
        affected_set = {str(ticker).upper() for ticker in affected}
        is_market_wide = VN_INDEX_PLACEHOLDER in affected_set or not affected_set
        has_overlap = bool(universe & affected_set)
        confidence = (catalyst.get("confidence") or "").upper()
        is_material = confidence in {"HIGH", "MEDIUM"}
        is_imminent = (catalyst.get("status") or "").lower() == "imminent"

        if has_overlap or is_market_wide or is_material or is_imminent:
            kept.append(catalyst)

    kept.sort(
        key=lambda catalyst: (
            _IMPACT_RANK.get((catalyst.get("impact") or "").upper(), 5),
            _CONFIDENCE_RANK.get((catalyst.get("confidence") or "").upper(), 3),
            _days_until(catalyst.get("expected")),
        )
    )
    return kept[:cap]
