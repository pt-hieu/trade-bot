"""Shared belief collection helper — fail-loud on null-belief sub-agent output.

After the A2 schema contract (non-null `belief` field on SectorAnalystView /
AnalystView), encountering `view.belief is None` at collect time means
PydanticAI's retry budget exhausted OR a broader schema bypass — not a
benign gap. This helper replaces 3 silent-drop sites that previously only
warned (or didn't warn at all) and let the pipeline continue with empty
beliefs lists.

Call sites:
- scripts/agents/sector.py
- scripts/agents/positions_ensemble_aggregator.py
- scripts/agents/positions_ensemble_fallback.py
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from shared.observability import emit_belief_coverage_gap_span


@runtime_checkable
class _HasBelief(Protocol):
    """Structural type for sector/positions analyst views.

    Both SectorAnalystView and AnalystView fit this shape.
    """

    ticker: str

    @property
    def belief(self) -> object: ...  # TickerBelief | None (runtime-checked)


@runtime_checkable
class _HasViews(Protocol):
    views: list  # list[_HasBelief] — pyright can't cross-type through inheritance here


def collect_beliefs_from_views(
    reports: list[tuple[str, _HasViews]],
    *,
    agent_key_prefix: str,
    scope_name: str,
    logger: logging.Logger,
) -> list[dict]:
    """Collect non-null beliefs from sub-agent reports; fail loud on gaps.

    Args:
        reports: ordered list of (analyst_type, report) pairs.
        agent_key_prefix: "sector" or "positions" — combined with analyst_type
            to form the final agent_key persisted to the DB.
        scope_name: sector name (for sector ensemble) or "positions" marker.
        logger: caller's logger so errors land in the right namespace.

    Returns:
        List of belief dicts with `agent_key` stamped on each, de-duplicated
        by (ticker, agent_key).
    """
    beliefs: list[dict] = []
    seen: set[tuple[str, str]] = set()
    missing: list[tuple[str, str]] = []

    for analyst_type, report in reports:
        agent_key = f"{agent_key_prefix}_{analyst_type}"
        for view in report.views:
            view_belief = getattr(view, "belief", None)
            ticker = getattr(view, "ticker", "?")
            if view_belief is None:
                missing.append((agent_key, ticker))
                continue
            belief_ticker = getattr(view_belief, "ticker", ticker)
            dedup_key = (belief_ticker, agent_key)
            if dedup_key in seen:
                logger.warning(
                    "Duplicate belief skipped: %s/%s in %s",
                    agent_key,
                    belief_ticker,
                    scope_name,
                )
                continue
            seen.add(dedup_key)
            beliefs.append({"agent_key": agent_key, **view_belief.model_dump()})

    if missing:
        logger.error(
            "BELIEF_COVERAGE_GAP scope=%s missing=%d sample=%s",
            scope_name,
            len(missing),
            missing[:10],
        )
        emit_belief_coverage_gap_span(
            scope=scope_name,
            missing_count=len(missing),
            missing_sample=missing[:10],
            logger=logger,
        )

    return beliefs
