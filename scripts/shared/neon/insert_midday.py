"""Midday-check writers (split out of insert_content.py).

Pulled from ``insert_content.py`` to keep the article-insert module under
the 350-line cap (CLAUDE.md). The midday writer mirrors the
``RecommendationOverride`` contract at persistence and post-verifies child
row inserts. See AUDIT-2026-04-24-001 for the loud-failure invariants.
"""

from __future__ import annotations

import json
import logging
from datetime import date

from ..database import get_db
from ..narrative import _EXECUTION_PHRASES, narrative_truth_check
from ..ticker_extract import is_valid_ticker
from ..vn_universe import (
    VN_INDEX_PLACEHOLDER,
    VNUniverseUnavailable,
    is_vn_listed,
    load_vn_universe_async,
)
from ._sync import make_sync

logger = logging.getLogger(__name__)


class MiddayOverrideReasonViolation(ValueError):
    """Midday override `reason` contained execution-claim prose (SWI-255)."""


def _enforce_midday_override_reason_signal_language(scan_date: date, override: dict) -> None:
    """Fail-closed gate at the persistence boundary.

    Mirror of the agent-side validator in ``agents.midday.validate``;
    runs unconditionally so retry-loop or future-agent paths cannot
    bypass it. Execution verbs in the reason text fabricate trades that
    never happened — see SWI-255 ACV 2026-05-05 incident.
    """
    reason = override.get("reason") or ""
    violation = narrative_truth_check(
        reason,
        phrases=_EXECUTION_PHRASES,
        structural_value=False,  # midday cannot observe executions
        expected=True,
        check_name="OVERRIDE_REASON_OUTCOME_VERB",
        severity="critical",
        detail=("Midday override reason uses outcome verbs but midday cannot observe executions."),
        suggestion="Use signal language: 'signal cancelled', 'stop level breached intraday'.",
    )
    if violation is None:
        return
    ticker = override.get("ticker") or "?"
    logger.error(
        "insert_midday_check %s: REJECTING override — ticker=%s reason cites execution "
        "but midday cannot observe trades. reason=%r",
        scan_date,
        ticker,
        reason[:240],
    )
    raise MiddayOverrideReasonViolation(
        f"insert_midday_check {scan_date}: midday override for {ticker!r} reason "
        f"uses outcome verbs (executed/closed/taken/stopped out). Midday cannot "
        f"observe executions; use signal language instead. See SWI-255."
    )


def _shape_or_vn_listed(ticker: str | None, universe: frozenset[str] | None) -> bool:
    """Validate ticker shape, then VN universe membership when universe is primed.

    Fail-open when ``universe`` is None: a DB hiccup on the universe fetch
    falls back to shape-only validation so ingest doesn't lose rows during
    a transient outage.
    """
    if not (ticker and is_valid_ticker(ticker)):
        return ticker == VN_INDEX_PLACEHOLDER
    if universe is None:
        return True
    return is_vn_listed(ticker, universe)


def _enforce_midday_override_stop_contract(scan_date: date, override: dict) -> None:
    """Mirror the `RecommendationOverride` contract at persistence.

    Two contracts enforced (belt-and-suspenders for hand-built dicts that
    bypass Pydantic — e.g. resume paths):

      1. ``CANCEL`` with stop-citing reason MUST populate ``revised_stop``
         (MON-2026-04-24-002).
      2. Every ``revised_*`` VND field is normalized via
         ``shared.rules.midday_override_planning.normalize_vnd_price`` so
         a unit-shifted ``44.91`` becomes ``44910`` before write
         (SWI-140 / SWI-137).
    """
    from agents.midday import override_reason_mentions_stop
    from shared.rules.vnd_price_clamp import normalize_vnd_price

    reason_text = override.get("reason")
    for field_name in ("revised_entry", "revised_stop", "revised_target"):
        current = override.get(field_name)
        normalized = normalize_vnd_price(
            current, reason_text, agent="midday_override", boundary="persistence"
        )
        override[field_name] = normalized

    status = (override.get("midday_status") or "").upper()
    if status != "CANCEL":
        return
    if not override_reason_mentions_stop(reason_text):
        return
    if override.get("revised_stop") is not None:
        return
    ticker = override.get("ticker") or "?"
    logger.error(
        "insert_midday_check %s: REJECTING midday override — ticker=%s "
        "midday_status=CANCEL with stop-citing reason but revised_stop is None. "
        "See MON-2026-04-24-002. reason=%r",
        scan_date,
        ticker,
        (reason_text or "")[:240],
    )
    raise ValueError(
        f"insert_midday_check {scan_date}: midday override for {ticker!r} "
        "is CANCEL with stop-citing reason but revised_stop is null. Populate "
        "revised_stop with the authoritative stop level (see "
        "shared/rules/stop_resolution.py::resolve_stop_for_rec) or rewrite "
        "the reason to not cite a stop."
    )


async def insert_midday_check(scan_date: date, data: dict) -> bool:
    """Insert midday check data."""
    db = await get_db()

    try:
        vn_universe: frozenset[str] | None = await load_vn_universe_async()
    except VNUniverseUnavailable:
        logger.warning(
            "insert_midday_check: VN universe unavailable — falling back to shape-only ticker gate"
        )
        vn_universe = None

    def _vn_ok(ticker: str | None) -> bool:
        return _shape_or_vn_listed(ticker, vn_universe)

    try:
        raw_overrides = data.get("recommendation_overrides") or []
        validated_overrides = []
        for item in raw_overrides:
            if isinstance(item, dict):
                _enforce_midday_override_stop_contract(scan_date, item)
                _enforce_midday_override_reason_signal_language(scan_date, item)
                validated_overrides.append(item)
            else:
                logger.warning(
                    "insert_midday_check %s: dropping non-dict override: %s (type=%s)",
                    scan_date,
                    str(item)[:100],
                    type(item).__name__,
                )
        overrides_json = json.dumps(validated_overrides)

        from ._afternoon_plan_serde import serialize_afternoon_plan

        afternoon_plan_json = serialize_afternoon_plan(
            data.get("afternoon_plan"),
            context=f"insert_midday_check scan_date={scan_date}",
        )

        midday_id = await db.fetch_val(
            """
            INSERT INTO midday_checks (scan_date, trading_mode, morning_reflection, afternoon_plan, capital_note, recommendation_overrides)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6::jsonb)
            ON CONFLICT (scan_date) DO UPDATE SET
                trading_mode = EXCLUDED.trading_mode, morning_reflection = EXCLUDED.morning_reflection,
                afternoon_plan = EXCLUDED.afternoon_plan, capital_note = EXCLUDED.capital_note,
                recommendation_overrides = EXCLUDED.recommendation_overrides
            RETURNING id
            """,
            scan_date,
            data.get("trading_mode"),
            data.get("morning_reflection"),
            afternoon_plan_json,
            data.get("capital_note"),
            overrides_json,
        )

        await db.execute("DELETE FROM midday_entries_hit WHERE midday_id = $1", midday_id)
        await db.execute("DELETE FROM midday_big_movers WHERE midday_id = $1", midday_id)
        await db.execute("DELETE FROM midday_position_alerts WHERE midday_id = $1", midday_id)

        for entry in data.get("entries_hit", []):
            ticker = entry.get("ticker")
            if _vn_ok(ticker):
                await db.execute(
                    """
                    INSERT INTO midday_entries_hit (midday_id, ticker, recommended_entry_vnd, actual_low_vnd, current_price_vnd, status)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    midday_id,
                    ticker,
                    int(entry.get("recommended_entry", 0) * 1000)
                    if entry.get("recommended_entry")
                    else None,
                    int(entry.get("actual_low", 0) * 1000) if entry.get("actual_low") else None,
                    int(entry.get("current_price", 0) * 1000)
                    if entry.get("current_price")
                    else None,
                    entry.get("status"),
                )

        for mover in data.get("big_movers", []):
            ticker = mover.get("ticker")
            if _vn_ok(ticker):
                await db.execute(
                    """
                    INSERT INTO midday_big_movers (midday_id, ticker, open_price_vnd, current_price_vnd, change_pct, direction)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    midday_id,
                    ticker,
                    int(mover.get("open_price", 0) * 1000) if mover.get("open_price") else None,
                    int(mover.get("current_price", 0) * 1000)
                    if mover.get("current_price")
                    else None,
                    mover.get("change_pct"),
                    mover.get("direction"),
                )

        for alert in data.get("position_alerts", []):
            ticker = alert.get("ticker")
            if _vn_ok(ticker):
                await db.execute(
                    """
                    INSERT INTO midday_position_alerts (midday_id, ticker, current_price_vnd, level_vnd, level_type, distance_pct, urgency)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    midday_id,
                    ticker,
                    int(alert.get("current_price", 0) * 1000)
                    if alert.get("current_price")
                    else None,
                    int(alert.get("level", 0) * 1000) if alert.get("level") else None,
                    alert.get("level_type"),
                    alert.get("distance_pct"),
                    alert.get("urgency"),
                )

        expected = sum(1 for e in data.get("entries_hit", []) if _vn_ok(e.get("ticker")))
        expected += sum(1 for m in data.get("big_movers", []) if _vn_ok(m.get("ticker")))
        expected += sum(1 for a in data.get("position_alerts", []) if _vn_ok(a.get("ticker")))
        if expected > 0:
            actual = await db.fetch_val(
                "SELECT COUNT(*) FROM midday_entries_hit WHERE midday_id = $1", midday_id
            )
            actual += await db.fetch_val(
                "SELECT COUNT(*) FROM midday_big_movers WHERE midday_id = $1", midday_id
            )
            actual += await db.fetch_val(
                "SELECT COUNT(*) FROM midday_position_alerts WHERE midday_id = $1", midday_id
            )
            if actual == 0:
                logger.warning(f"Midday {scan_date}: expected {expected} child rows, wrote 0")

        return True
    except Exception as e:
        logger.error(f"insert_midday_check {scan_date}: {e}")
        return False


insert_midday_check_sync = make_sync(insert_midday_check)
