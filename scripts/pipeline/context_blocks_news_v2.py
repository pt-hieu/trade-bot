"""Context-block builders for News Pipeline v2 (SWI-244).

Two stages, two budgets:

* Stage 1 (relevance gate) — top-300 universe rendered as ticker rows with
  sector + 2-3 aliases. Budget ≤ 4K tokens to stay inside the 7K injected
  limit alongside title + summary + system prompt. The LLM has zero
  parametric knowledge of VN listings, so this block is the *only* anchor
  for entity spotting.
* Stage 2 (extractor) — only the entities Stage 1 spotted, resolved against
  ``company_profiles`` (ticker + sector + 1-line summary + aliases).
  Typically ≤10 rows per article. Plus active narratives + catalysts (last
  14 days) so the LLM can reuse identity instead of fabricating duplicates.

Render style mirrors `pipeline/context_blocks_ticker.py` patterns: dense
header line, dash-prefixed rows, blank-line block separators. No prose.
"""

from __future__ import annotations

from typing import TypedDict

from shared.neon import (
    get_active_catalysts_db,
    get_active_narratives,
    get_universe_with_aliases,
)

# ── Public TypedDicts ─────────────────────────────────────────────────────


class StageOnePayload(TypedDict):
    """Output of Phase 0 batch fetch for the Stage 1 relevance pass."""

    universe_block: str
    universe_size: int


class StageTwoPayload(TypedDict):
    """Output of Phase 0 batch fetch reused for every Stage 2 call.

    The candidates block is article-specific and built per-call via
    ``build_resolved_candidates_block(...)``; the rest are batch-static.
    """

    active_narratives_block: str
    active_catalysts_block: str
    universe_tickers: frozenset[str]


# ── Stage 1 — top universe ────────────────────────────────────────────────


def render_universe_block(rows: list[dict]) -> str:
    """Render a list of universe rows as the Stage 1 prompt block.

    Pure formatting — accepts pre-fetched rows so callers can share a
    single ``get_universe_with_aliases`` round-trip across Stage 1 +
    alias-index builds.
    """
    if not rows:
        return "VN UNIVERSE: (empty — backfill missing, escalate to operator)"
    lines = [
        f"VN UNIVERSE ({len(rows)} active tickers — output candidate_entities "
        "as raw company/brand tokens spotted in the article):",
    ]
    for r in rows:
        ticker = r["ticker"]
        sector = r.get("sector_name") or "?"
        aliases = r.get("aliases") or []
        alias_str = ";".join(aliases[:3]) if aliases else ""
        lines.append(
            f"- {ticker} [{sector}]: {alias_str}" if alias_str else f"- {ticker} [{sector}]"
        )
    return "\n".join(lines)


async def build_top_universe_block(limit: int = 200) -> str:
    """Stage 1 universe injection — convenience fetcher + renderer.

    Default limit tuned to stay inside the 4K-token Stage 1 budget (~13
    chars per ticker row including aliases). Callers that already hold
    universe rows should call ``render_universe_block`` directly to
    avoid a second DB round-trip.
    """
    rows = await get_universe_with_aliases(limit=limit)
    return render_universe_block(rows)


# ── Stage 2 — resolved candidates (per-article) ───────────────────────────


def build_resolved_candidates_block(candidates: list[dict]) -> str:
    """Stage 2 per-article candidate block.

    ``candidates`` is the orchestrator's resolved match (raw Stage 1
    entity → ``company_profiles`` row). Each row carries:
    ticker, sector_name, business_summary_short, aliases, raw_entity.
    """
    if not candidates:
        return (
            "CANDIDATE TICKERS (Stage 1 found none — set affected_tickers=[] "
            "and abstain=true unless title/summary names a ticker directly):"
        )

    lines = [f"CANDIDATE TICKERS ({len(candidates)} resolved by Stage 1):"]
    for c in candidates:
        ticker = c["ticker"]
        sector = c.get("sector_name") or "?"
        summary = c.get("business_summary_short") or ""
        raw = c.get("raw_entity") or ""
        bits = [f"- {ticker} [{sector}]"]
        if raw:
            bits.append(f'matched="{raw}"')
        if summary:
            bits.append(summary)
        lines.append(" ".join(bits))
    lines.append(
        "Output `affected_tickers` MUST be a subset of the tickers above "
        "(plus the literal 'VN-INDEX' for market-wide events)."
    )
    return "\n".join(lines)


# ── Stage 2 — active narratives ───────────────────────────────────────────


async def build_active_narratives_block(days: int = 14, limit: int = 40) -> tuple[str, list[dict]]:
    """Stage 2 active narratives block.

    Returns ``(rendered_block, raw_rows)`` so the orchestrator can reuse
    the rows for ``narrative_match_key`` resolution without a second DB
    round-trip. Narratives are filtered to ``pipeline_version='v2'`` by
    the shared/neon helper after the cutover patch.
    """
    rows = await get_active_narratives()
    rows = rows[:limit]
    if not rows:
        return (
            "ACTIVE NARRATIVES: (none — emit narrative_link_kind='NEW' if "
            "the article warrants a new thread, otherwise 'NONE')",
            [],
        )

    lines = [
        f"ACTIVE NARRATIVES ({len(rows)} threads, last {days}d — emit "
        "`narrative_match_key` matching one of the keys below to attach, "
        "or a fresh slug to start a new thread):",
    ]
    for r in rows:
        key = r.get("narrative_key") or "?"
        theme = (r.get("theme") or "")[:80]
        tickers = (r.get("affected_tickers") or [])[:3]
        ticker_str = ",".join(tickers) if tickers else "—"
        ntype = r.get("narrative_type") or "?"
        lines.append(f"- {key} [{ntype}] ({ticker_str}): {theme}")
    return "\n".join(lines), rows


# ── Stage 2 — active catalysts ────────────────────────────────────────────


async def build_active_catalysts_block(days: int = 14, limit: int = 40) -> tuple[str, list[dict]]:
    """Stage 2 active catalysts block.

    Returns ``(rendered_block, raw_rows)``. Filtered to v2 by the
    shared/neon helper after cutover.
    """
    rows = await get_active_catalysts_db()
    rows = rows[:limit]
    if not rows:
        return (
            "ACTIVE CATALYSTS: (none — emit catalyst_link_kind='NEW' if "
            "the article describes a fresh upcoming event, else 'NONE')",
            [],
        )

    lines = [
        f"ACTIVE CATALYSTS ({len(rows)} events, last {days}d — emit "
        "`catalyst_event_phrase` describing the event; the orchestrator "
        "will resolve to an existing catalyst_key or compose a new one):",
    ]
    for r in rows:
        key = r.get("catalyst_key") or "?"
        event = (r.get("event") or "")[:80]
        tickers = (r.get("affected_tickers") or [])[:3]
        ticker_str = ",".join(tickers) if tickers else "—"
        ctype = r.get("catalyst_type") or "?"
        lines.append(f"- {key} [{ctype}] ({ticker_str}): {event}")
    return "\n".join(lines), rows


# ── Phase 0 fan-out ───────────────────────────────────────────────────────


async def build_stage_one_payload(
    universe_limit: int = 200,
    universe_rows: list[dict] | None = None,
) -> StageOnePayload:
    """Stage 1 payload. Pass ``universe_rows`` to skip the DB round-trip."""
    rows = universe_rows or await get_universe_with_aliases(limit=universe_limit)
    rows = rows[:universe_limit]
    return {"universe_block": render_universe_block(rows), "universe_size": len(rows)}


async def build_stage_two_static_payload(
    universe_rows: list[dict] | None = None,
) -> tuple[StageTwoPayload, list[dict], list[dict]]:
    """Batch-fetch the Stage 2 static blocks once per pipeline run.

    Returns ``(payload, narrative_rows, catalyst_rows)`` so the
    orchestrator can reuse the rows for identity resolution without
    re-querying.
    """
    narratives_block, narrative_rows = await build_active_narratives_block()
    catalysts_block, catalyst_rows = await build_active_catalysts_block()
    universe = universe_rows or await get_universe_with_aliases(limit=2000)
    universe_tickers = frozenset(r["ticker"] for r in universe)
    payload: StageTwoPayload = {
        "active_narratives_block": narratives_block,
        "active_catalysts_block": catalysts_block,
        "universe_tickers": universe_tickers,
    }
    return payload, narrative_rows, catalyst_rows


__all__ = [
    "StageOnePayload",
    "StageTwoPayload",
    "build_active_catalysts_block",
    "build_active_narratives_block",
    "build_resolved_candidates_block",
    "build_stage_one_payload",
    "build_stage_two_static_payload",
    "build_top_universe_block",
]


# Suppress unused-import warning — `date` is exposed for downstream typing.
