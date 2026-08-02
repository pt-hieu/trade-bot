"""Deterministic SKIP_THESE selector — single source of truth.

Both `recommendation_builder.build_structured_recommendations` (writes to
`daily_recommendations`) and the brief renderer at
`scripts/pipeline/rendering/skip_these.py` call this selector with identical
inputs. Same code path → the DB table and the morning-brief SKIP section can
never list different tickers.

Originating incident: MON-2026-04-23-001 — brief rendered VPB/SZC/VRE as SKIP
while the DB listed MBB/NLG/PVI/TPB/VIX. The cause was two independent
derivations (deterministic rec-builder for the table, LLM prose for the
brief). This module ends that divergence.

Pure-Python, no DB, no LLM, no I/O — lives under ``shared/rules/`` to stay
importable by both pipeline phases and web serializers.
"""

from __future__ import annotations

from typing import Literal, TypedDict

SkipSource = Literal["sector_signals", "advocate_gated"]


class SkipEntry(TypedDict):
    """One SKIP bullet: ticker + rationale for rendering or persistence."""

    ticker: str
    reason: str
    source: SkipSource


_SKIP_SIGNALS = frozenset({"AVOID", "SKIP"})


def select_skip_tickers(
    sector_signals: list[dict] | None,
    gated_tickers: list[dict] | None,
    exclusions: set[str],
) -> list[SkipEntry]:
    """Compute the SKIP_THESE bullet list from structured inputs.

    Inputs:
    - ``sector_signals``: dict list from sector agents. Signals whose
      ``signal`` is AVOID or SKIP contribute one entry each.
    - ``gated_tickers``: dict list from advocate-gate output. Picks blocked
      by the bull/bear advocate challenge are shown as SKIP so the reader
      sees the rejection with a bear-argument excerpt.
    - ``exclusions``: tickers already covered by TOP_PICKS, MY_HOLDINGS, or
      LONG_TERM watchlist sections. The brief's MY HOLDINGS + TOP PICKS +
      LONG-TERM PORTFOLIO sections already surface these, and dual-coverage
      is noise.

    Output:
    - list of SkipEntry, deduped by ticker (first occurrence wins), in input
      order: sector signals then gated tickers.
    """
    seen: set[str] = set()
    entries: list[SkipEntry] = []

    for signal in sector_signals or []:
        ticker = (signal.get("ticker") or "").upper()
        if not ticker or ticker in exclusions or ticker in seen:
            continue
        raw = (signal.get("signal") or "").upper()
        if raw not in _SKIP_SIGNALS:
            continue
        seen.add(ticker)
        reason = signal.get("note") or ""
        entries.append({"ticker": ticker, "reason": reason, "source": "sector_signals"})

    for gated in gated_tickers or []:
        ticker = (gated.get("ticker") or "").upper()
        if not ticker or ticker in exclusions or ticker in seen:
            continue
        seen.add(ticker)
        bear_args = gated.get("bear_arguments") or []
        if isinstance(bear_args, list) and bear_args:
            reason = "; ".join(str(arg) for arg in bear_args[:2])
        else:
            reason = gated.get("gated_by") or "advocate_gate"
        entries.append({"ticker": ticker, "reason": reason, "source": "advocate_gated"})

    return entries
