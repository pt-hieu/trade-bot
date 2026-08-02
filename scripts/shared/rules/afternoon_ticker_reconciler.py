"""Post-LLM afternoon_plan ticker reconciler.

Originating incident: MON-2026-04-23-002. The midday LLM returned three
`afternoon_plan` entries with `ticker=None` while the `reason` text still
identified each position by a price fingerprint — a stop level, a
catastrophic floor, an uptrend line. Downstream per-ticker routing
(plan_type scoping on overrides, retro aggregation, audit) needs a
non-null ticker.

This reconciler runs after the agent returns and before persistence:
  * Promote-if-mappable: when an entry has a missing or unrecognized
    ticker but `reason` contains a stop/avg-cost fingerprint or 3-letter
    ticker token matching a current holding, mutate the entry so ticker
    points at that holding.
  * Leave-if-unmappable: when no match, KEEP ticker=None. Migration 316
    documents null-ticker as semantically valid for legacy NOTE rows —
    replay paths still need to parse them. Instead of dropping, emit one
    `afternoon_plan_unmapped` telemetry span for the batch so
    pipeline-review catches regressions.

Matches the `max_loss_breaches` post-LLM injection pattern at
scripts/agents/midday.py:268-304 and the LLM→enum classifier pattern at
scripts/shared/rules/catalyst_classifier.py.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol

from shared.observability import span
from shared.text_utils import TICKER_TOKEN_RE

logger = logging.getLogger(__name__)

_PRICE_KEYS: tuple[str, ...] = ("stop_price_vnd", "avg_cost", "current_price_vnd")
_PRICE_TOLERANCE_PCT = 0.02


class _AfternoonActionLike(Protocol):
    """Subset of AfternoonAction the reconciler mutates. Pydantic models
    satisfy this structurally."""

    ticker: str | None
    reason: str
    evidence_price_vnd: int | None


def _coerce_price(value: object) -> int | None:
    try:
        price = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def _price_fingerprints(value: object) -> list[str]:
    """Return all string forms a holding price might appear as in LLM prose:
    comma-grouped, bare integer, and (for >=1000) k-suffix variants at 1- and
    2-decimal precision plus the rounded integer-k."""
    price = _coerce_price(value)
    if price is None:
        return []
    fingerprints: list[str] = [f"{price:,}", f"{price}"]
    if price >= 1000:
        fingerprints.append(f"{price / 1000:.1f}k")
        fingerprints.append(f"{price / 1000:.2f}k")
        fingerprints.append(f"{round(price / 1000)}k")
    return fingerprints


def _build_fingerprint_index(holdings: list[dict]) -> list[tuple[str, list[str]]]:
    """Precompute (ticker, fingerprints) tuples once for the entry loop.

    Fingerprints that map to >=2 tickers are dropped from BOTH tickers' index
    entries to prevent first-match-wins ambiguity, with an ERROR log so audit
    can detect prose that cannot be safely reconciled."""
    raw: dict[str, list[str]] = {}
    for holding in holdings:
        ticker = (holding.get("ticker") or "").upper()
        if not ticker:
            continue
        prints: list[str] = []
        for key in _PRICE_KEYS:
            prints.extend(_price_fingerprints(holding.get(key)))
        if prints:
            raw[ticker] = prints

    fp_to_tickers: dict[str, list[str]] = {}
    for ticker, fingerprints in raw.items():
        for fingerprint in fingerprints:
            fp_to_tickers.setdefault(fingerprint, []).append(ticker)

    collisions = {fp for fp, owners in fp_to_tickers.items() if len(owners) > 1}
    for fp in sorted(collisions):
        logger.error(
            "fingerprint_collision: fp=%r tickers=%s — dropping from index",
            fp,
            fp_to_tickers[fp],
        )

    index: list[tuple[str, list[str]]] = []
    for ticker, fingerprints in raw.items():
        unique = [fp for fp in fingerprints if fp not in collisions]
        if unique:
            index.append((ticker, unique))
    return index


def _resolve_by_structured_evidence(
    evidence_price_vnd: int | None,
    holdings: list[dict],
) -> str | None:
    """Primary reconcile path: integer match against holding prices within
    ±2% tolerance. Falls back to fingerprint matching when null/ambiguous."""
    if not evidence_price_vnd or evidence_price_vnd <= 0:
        return None
    matches: list[str] = []
    for holding in holdings:
        ticker = (holding.get("ticker") or "").upper()
        if not ticker:
            continue
        for key in _PRICE_KEYS:
            price = _coerce_price(holding.get(key))
            if price is None:
                continue
            if abs(price - evidence_price_vnd) <= price * _PRICE_TOLERANCE_PCT:
                matches.append(ticker)
                break
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        logger.error(
            "evidence_price_collision: evidence_price_vnd=%d matched tickers=%s — "
            "falling back to fingerprint",
            evidence_price_vnd,
            matches,
        )
    return None


def _resolve_ticker(
    reason: str,
    fingerprint_index: list[tuple[str, list[str]]],
    holding_tickers: set[str],
) -> str | None:
    """Fallback path: fingerprint string-match first, then bare ticker token
    match constrained to current holdings. Last resort behind structured
    evidence per the ``structured-over-keyword`` rule."""
    if not reason:
        return None
    for ticker, fingerprints in fingerprint_index:
        if any(fp in reason for fp in fingerprints):
            return ticker
    for token in TICKER_TOKEN_RE.findall(reason):
        if token in holding_tickers:
            return token
    return None


def reconcile_afternoon_tickers(
    entries: Sequence[_AfternoonActionLike],
    holdings: list[dict],
) -> Sequence[_AfternoonActionLike]:
    """Promote mappable unmapped entries; emit one telemetry span per batch.

    Mutates entries in place; returns the same sequence for caller chaining.
    """
    holding_tickers = {(h.get("ticker") or "").upper() for h in holdings if h.get("ticker")}
    fingerprint_index = _build_fingerprint_index(holdings)
    unmapped_excerpts: list[str] = []

    for entry in entries:
        raw_ticker = (entry.ticker or "").upper() if entry.ticker else ""
        if raw_ticker and raw_ticker in holding_tickers:
            entry.ticker = raw_ticker  # normalize case
            continue

        evidence = getattr(entry, "evidence_price_vnd", None)
        resolved = _resolve_by_structured_evidence(evidence, holdings)
        if resolved:
            logger.warning(
                "afternoon_plan: promoted ticker %s → %s from evidence_price_vnd=%s",
                entry.ticker,
                resolved,
                evidence,
            )
            entry.ticker = resolved
            continue

        resolved = _resolve_ticker(entry.reason, fingerprint_index, holding_tickers)
        if resolved:
            logger.warning(
                "afternoon_plan: promoted ticker %s → %s from reason fingerprint (reason=%r)",
                entry.ticker,
                resolved,
                entry.reason,
            )
            entry.ticker = resolved
            continue

        unmapped_excerpts.append((entry.reason or "")[:120])

    if unmapped_excerpts:
        with span(
            "afternoon_plan_unmapped",
            agent="midday",
            unmapped_count=len(unmapped_excerpts),
            reason_excerpts=unmapped_excerpts,
            holding_count=len(holding_tickers),
        ):
            logger.warning(
                "afternoon_plan: %d entries left with ticker=None (holdings=%s)",
                len(unmapped_excerpts),
                sorted(holding_tickers),
            )
    return entries
