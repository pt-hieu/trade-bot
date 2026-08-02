"""Persist discovery results to the catalysts DB table."""

from __future__ import annotations

import logging
from datetime import date

from shared.neon.catalysts import (
    complete_catalyst,
    get_active_catalysts_db,
    link_catalyst_articles,
    update_catalyst_field,
    upsert_catalyst,
)
from shared.rules.catalyst_classifier import classify_catalyst_type
from shared.rules.catalyst_expected_parser import PERSIST_OK_STATUSES, parse_expected
from shared.rules.catalyst_key import compose_catalyst_key

from .audit import _record_catalyst_audit
from .dedup import _find_duplicate_catalyst, _resolve_supporting_ids
from .schemas import _confidence_rank

logger = logging.getLogger(__name__)


async def _persist_discoveries(
    discoveries: dict,
    scan_date: date | None = None,
    classified_articles: list[dict] | None = None,
    *,
    existing_catalysts: list[dict] | None = None,
) -> None:
    """Write discovery results to catalysts DB table.

    Links are scoped to ``supporting_article_ids`` from each addition (or
    a sanitised subset of the batch's article_ids for back-compat), NOT
    every article in the batch — otherwise every new geopolitical catalyst
    would accumulate unrelated articles and poison downstream narrative
    joins.
    """
    today = scan_date or date.today()
    batch_article_ids: frozenset[str] = frozenset(
        art["article_id"] for art in (classified_articles or []) if art.get("article_id")
    )

    if existing_catalysts is None:
        existing_catalysts = await get_active_catalysts_db(None)

    for addition in discoveries.get("additions", []):
        supporting_ids = _resolve_supporting_ids(addition, batch_article_ids)

        effective_type, outcome, reason = classify_catalyst_type(
            event=addition.get("event") or "",
            candidate_type=addition.get("catalyst_type") or "regulatory",
            has_phases=bool(addition.get("phases")),
        )
        if outcome == "rejected" and reason == "missing_phases":
            logger.warning(
                "Rejected catalyst '%s' — classifier requires phases for geopolitical reclassify.",
                addition.get("event"),
            )
            await _record_catalyst_audit(
                event=addition.get("event") or "",
                candidate_type=addition.get("catalyst_type") or "",
                reason="missing_phases",
                scan_date=today,
            )
            continue
        if outcome == "coerced":
            logger.info(
                "Coerced catalyst '%s' catalyst_type %s -> %s (rule=%s)",
                addition.get("event"),
                addition.get("catalyst_type"),
                effective_type,
                reason,
            )
            await _record_catalyst_audit(
                event=addition.get("event") or "",
                candidate_type=addition.get("catalyst_type") or "",
                reason=reason or "coerced",
                scan_date=today,
                rule_corrected_type=effective_type,
            )
            addition["catalyst_type"] = effective_type

        duplicate_key = _find_duplicate_catalyst(
            addition["event"],
            existing_catalysts,
            candidate_type=addition.get("catalyst_type") or "regulatory",
        )
        if duplicate_key:
            logger.info(
                "Skipping duplicate catalyst '%s' — matches existing '%s'. Linking articles.",
                addition["event"],
                duplicate_key,
            )
            if supporting_ids:
                await link_catalyst_articles(duplicate_key, supporting_ids)
            existing = next(
                (c for c in existing_catalysts if c.get("catalyst_key") == duplicate_key),
                None,
            )
            if existing and _confidence_rank(addition.get("confidence", "LOW")) > _confidence_rank(
                existing.get("confidence") or "LOW"
            ):
                await update_catalyst_field(duplicate_key, "confidence", addition["confidence"])
            continue

        catalyst_key = compose_catalyst_key(addition["event"])

        parsed_date, parsed_status = parse_expected(addition.get("expected") or "", today)
        if parsed_status not in PERSIST_OK_STATUSES:
            logger.warning(
                "catalyst dropped: status=%s event=%r expected=%r",
                parsed_status,
                addition.get("event"),
                addition.get("expected"),
            )
            continue
        upsert_payload: dict[str, object] = {
            "catalyst_key": catalyst_key,
            "event": addition["event"],
            "expected": addition["expected"],
            "affected_tickers": addition["affected"],
            "impact": addition["impact"],
            "confidence": addition["confidence"],
            "source": addition.get("source", "agent discovery"),
            "added_date": today,
            "expected_date": parsed_date,
            "expected_status": parsed_status,
            "supporting_article_count": len(supporting_ids),
            "official_document_flag": bool(addition.get("official_document_flag")),
        }
        if addition.get("catalyst_type"):
            upsert_payload["catalyst_type"] = addition["catalyst_type"]
        if addition.get("driver"):
            upsert_payload["driver"] = addition["driver"]
        if addition.get("phases"):
            upsert_payload["phases"] = addition["phases"]
        upsert_payload["catalyst_factors"] = list(addition.get("catalyst_factors") or [])

        try:
            await upsert_catalyst(upsert_payload)
        except ValueError as ve:
            logger.error(
                "Rejected catalyst addition '%s' — validation error: %s",
                addition.get("event"),
                ve,
            )
            continue

        if supporting_ids:
            await link_catalyst_articles(catalyst_key, supporting_ids)

    for update in discoveries.get("updates", []):
        try:
            await update_catalyst_field(
                update["catalyst_id"],
                update["field"],
                update["new_value"],
            )
        except ValueError as ve:
            logger.error(
                "Rejected catalyst update for %s.%s — validation error: %s",
                update.get("catalyst_id"),
                update.get("field"),
                ve,
            )

    for completion in discoveries.get("completions", []):
        await complete_catalyst(
            completion["catalyst_id"],
            completion["outcome"],
            completion["actual_date"],
        )
