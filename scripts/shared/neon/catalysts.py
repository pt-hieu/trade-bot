"""Catalyst & capital event DB operations."""

import json
import logging
from datetime import date

from shared.vn_universe import filter_vn_tickers

from ..database import get_db
from ..rules.geopolitical import validate_phase_periods
from ._sync import make_sync
from ._utils import json_for_jsonb_cast

logger = logging.getLogger(__name__)

# News v2 cutover (SWI-241): catalyst rows carry `pipeline_version` so v1
# discovery output stays in the table for audit but is excluded from the
# active-set read paths.
PIPELINE_VERSION_V2 = "v2"

# Fix 4 — HIGH-confidence article floor (2026-04-21):
# A catalyst tagged HIGH must clear one of two bars:
#   (a) ≥3 supporting articles (multi-source corroboration), OR
#   (b) an `official_document_flag=True` naming a qualifying primary source
#       (VN decree/SBV circular/MOF announcement/exchange notice, FTSE/MSCI
#       release, Fed/IMF/BOJ/ECB official publication).
# Otherwise the upsert silently downgrades confidence to MEDIUM and logs
# `high_confidence_downgrade`. This exists because the Apr-21 audit found
# 12 HIGH rows with 1 article and `hormuz_closure_2026` HIGH with 0 —
# a condition Fix 1's GEO_MIXED tie-break cannot tolerate.
_HIGH_CONFIDENCE_MIN_ARTICLES: int = 3

# ── Catalysts ──────────────────────────────────────────────────


async def get_active_catalysts_db(
    tickers: list[str] | None = None,
) -> list[dict]:
    """Get active catalysts, optionally filtered by affected tickers.

    Uses GIN index on affected_tickers for overlap (&&) queries.
    'VN-INDEX' in affected_tickers means "affects all stocks".
    """
    db = await get_db()
    # LEFT JOIN + GROUP BY materialises supporting_article_count from the
    # catalyst_articles join so shared/rules/catalyst_override.py can apply
    # the LOW-confidence corroboration gate without per-row subqueries.
    # $1 may be NULL (no ticker filter) — the OR short-circuits.
    # `c.*` is safe with `GROUP BY c.id` because id is the table PK —
    # PostgreSQL treats all non-aggregated columns as functionally dependent.
    rows = await db.fetch_all(
        """SELECT c.*,
                  COUNT(ca.article_id) AS supporting_article_count
           FROM catalysts c
           LEFT JOIN catalyst_articles ca USING (catalyst_key)
           WHERE status IN ('active', 'monitoring', 'imminent')
             AND c.pipeline_version = $2
             AND ($1::text[] IS NULL
                  OR affected_tickers && $1
                  OR 'VN-INDEX' = ANY(affected_tickers))
           GROUP BY c.id
           ORDER BY
             CASE confidence
               WHEN 'HIGH' THEN 0
               WHEN 'MEDIUM' THEN 1
               ELSE 2
             END,
             expected""",
        tickers,
        PIPELINE_VERSION_V2,
    )
    return [_row_to_dict(r) for r in rows]


def _enforce_high_confidence_floor(data: dict) -> str:
    """Return the effective confidence for an upsert.

    HIGH is kept only when the agent corroborates with ≥3 articles OR flags
    `official_document_flag=True`. Otherwise HIGH is downgraded to MEDIUM
    and a structured log line is emitted. Does not mutate `data`.

    Fix 4, 2026-04-21 — breaks the single-source HIGH pattern (12 rows
    were HIGH with 1 article on Apr 21) that Fix 1's GEO_MIXED tie-break
    cannot trust.
    """
    confidence = (data.get("confidence") or "").upper()
    if confidence != "HIGH":
        return confidence
    if data.get("official_document_flag"):
        return "HIGH"
    article_count = int(data.get("supporting_article_count") or 0)
    if article_count >= _HIGH_CONFIDENCE_MIN_ARTICLES:
        return "HIGH"
    logger.info(
        "high_confidence_downgrade: catalyst_key=%s article_count=%d official=%s → MEDIUM",
        data.get("catalyst_key"),
        article_count,
        bool(data.get("official_document_flag")),
    )
    return "MEDIUM"


async def upsert_catalyst(data: dict) -> bool:
    """Upsert a catalyst by catalyst_key.

    When ``data`` carries a ``phases`` dict the period strings are validated
    against :func:`validate_phase_periods`. Any parse failure now raises
    ``ValueError`` instead of silently warning — RC1 lets agents author
    phases, so malformed input must fail loudly to prevent undead catalysts
    like the 2026-04-13 Hormuz rows.

    Fix 4 (2026-04-21): confidence is re-evaluated through
    :func:`_enforce_high_confidence_floor` before insert. Callers supplying
    HIGH without ≥3 supporting articles or an `official_document_flag` get
    silently downgraded to MEDIUM.
    """
    db = await get_db()
    try:
        phases = data.get("phases")
        if phases:
            validation_errors = validate_phase_periods(phases)
            if validation_errors:
                raise ValueError(
                    f"upsert_catalyst({data.get('catalyst_key')}) phase validation failed: "
                    + "; ".join(validation_errors)
                )
        phases_json = json_for_jsonb_cast(phases)
        effective_confidence = _enforce_high_confidence_floor(data)
        # News v2 (SWI-241) write-side VN-universe guard — drop any ticker
        # that doesn't pass the curated VN universe before the row hits the
        # catalysts table. Replaces the deleted ``narrative_sector_filter``
        # regex layer with a single shared filter call.
        affected_tickers = filter_vn_tickers(
            list(data.get("affected_tickers", data.get("affected", [])) or []),
            context="upsert_catalyst",
        )
        # Fix 2 (2026-04-21): persist the structured factor list alongside
        # the phases column. Empty array is a valid value; constraint on
        # the DB side only rejects out-of-enum elements.
        catalyst_factors = list(data.get("catalyst_factors") or [])
        # SWI-18 (2026-04-27): persist `expected_status` alongside `expected_date`
        # so the lifecycle scorer can distinguish intentionally-dateless
        # (ongoing) catalysts from genuine parse failures (unparseable). The
        # ON CONFLICT branch now updates `expected_date` + `expected_status`
        # too — previously the INSERT-only path left existing NULL rows
        # stuck on NULL even after a re-upsert with a now-parseable date.
        # `catalyst_type` and `driver` are written on initial insert and
        # updated via COALESCE so a NULL from the agent preserves the prior
        # value (re-classification flow doesn't lose accepted types).
        await db.execute(
            """INSERT INTO catalysts
                (catalyst_key, event, expected, affected_tickers,
                 impact, confidence, notes, source, phases,
                 status, added_date, last_confirmed_at, expected_date,
                 catalyst_factors, expected_status, catalyst_type, driver,
                 pipeline_version)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,NOW(),$12,$13,$14,$15,$16,$17)
               ON CONFLICT (catalyst_key) DO UPDATE SET
                 event = EXCLUDED.event,
                 expected = EXCLUDED.expected,
                 affected_tickers = EXCLUDED.affected_tickers,
                 impact = EXCLUDED.impact,
                 confidence = EXCLUDED.confidence,
                 notes = EXCLUDED.notes,
                 source = EXCLUDED.source,
                 phases = EXCLUDED.phases,
                 catalyst_factors = EXCLUDED.catalyst_factors,
                 expected_date = EXCLUDED.expected_date,
                 expected_status = EXCLUDED.expected_status,
                 catalyst_type = COALESCE(EXCLUDED.catalyst_type, catalysts.catalyst_type),
                 driver = COALESCE(EXCLUDED.driver, catalysts.driver),
                 pipeline_version = EXCLUDED.pipeline_version,
                 last_confirmed_at = NOW(),
                 updated_at = NOW()""",
            data["catalyst_key"],
            data["event"],
            data["expected"],
            affected_tickers,
            data["impact"],
            effective_confidence,
            data.get("notes"),
            data.get("source"),
            phases_json,
            data.get("status", "active"),
            data.get("added_date", date.today()),
            data.get("expected_date"),
            catalyst_factors,
            data.get("expected_status"),
            data.get("catalyst_type"),
            data.get("driver"),
            data.get("pipeline_version") or PIPELINE_VERSION_V2,
        )
        return True
    except ValueError:
        # Phase validation is a hard contract violation — propagate so the
        # calling agent's retry loop sees it and the catalyst does NOT end
        # up as an undead row.
        raise
    except Exception as e:
        logger.warning("Failed to upsert catalyst: %s", e)
        return False


async def complete_catalyst(
    catalyst_key: str,
    outcome: str,
    actual_date: str,
) -> bool:
    """Mark a catalyst as completed."""
    db = await get_db()
    try:
        await db.execute(
            """UPDATE catalysts
               SET status = 'resolved',
                   outcome = $2,
                   actual_date = $3,
                   updated_at = NOW()
               WHERE catalyst_key = $1""",
            catalyst_key,
            outcome,
            actual_date,
        )
        return True
    except Exception as e:
        logger.warning("Failed to complete catalyst: %s", e)
        return False


_ALLOWED_CATALYST_FIELDS = frozenset(
    {
        "event",
        "expected",
        "affected_tickers",
        "impact",
        "confidence",
        "notes",
        "source",
        "phases",
        "catalyst_type",
        "catalyst_factors",
        "driver",
    }
)

# Fields that are JSONB and must be cast on the way in.
_JSONB_CATALYST_FIELDS: frozenset[str] = frozenset({"phases"})


async def update_catalyst_field(
    catalyst_key: str,
    field: str,
    value: str | dict[str, object] | list[object] | None,
) -> bool:
    """Update a single whitelisted field on a catalyst.

    RC1 widened the agent write path from scalar strings to include
    ``phases`` (dict). Dict / list values bind through an explicit
    ``::jsonb`` cast to avoid double-encoding.
    """
    if field not in _ALLOWED_CATALYST_FIELDS:
        logger.warning("Field '%s' not allowed for catalyst update", field)
        return False

    if field == "phases":
        if not isinstance(value, dict):
            logger.error(
                "update_catalyst_field phases: expected dict, got %s — refusing to write",
                type(value).__name__,
            )
            return False
        validation_errors = validate_phase_periods(value)
        if validation_errors:
            raise ValueError(
                f"update_catalyst_field({catalyst_key}, phases) validation failed: "
                + "; ".join(validation_errors)
            )

    db = await get_db()
    try:
        if field in _JSONB_CATALYST_FIELDS:
            await db.execute(
                f"""UPDATE catalysts
                    SET {field} = $2::jsonb, last_updated = CURRENT_DATE, updated_at = NOW()
                    WHERE catalyst_key = $1""",
                catalyst_key,
                json_for_jsonb_cast(value),
            )
        else:
            await db.execute(
                f"""UPDATE catalysts
                    SET {field} = $2, last_updated = CURRENT_DATE, updated_at = NOW()
                    WHERE catalyst_key = $1""",
                catalyst_key,
                value,
            )
        return True
    except ValueError:
        raise
    except Exception as e:
        logger.warning("Failed to update catalyst field: %s", e)
        return False


# ── Capital Events ─────────────────────────────────────────────


async def get_upcoming_capital_events_db(
    tickers: list[str] | None = None,
) -> list[dict]:
    """Get pending capital events, optionally filtered by ticker."""
    db = await get_db()
    if tickers:
        rows = await db.fetch_all(
            """SELECT * FROM capital_events
               WHERE status = 'pending' AND ticker = ANY($1)
               ORDER BY expected_date""",
            tickers,
        )
    else:
        rows = await db.fetch_all(
            """SELECT * FROM capital_events
               WHERE status = 'pending'
               ORDER BY expected_date""",
        )
    return [dict(r) for r in rows]


async def upsert_capital_event(data: dict) -> bool:
    """Upsert a capital event by event_key."""
    db = await get_db()
    try:
        dilution = data.get("dilution_pct")
        if isinstance(dilution, str):
            try:
                dilution = float(dilution.replace("%", ""))
            except (ValueError, AttributeError):
                dilution = None

        await db.execute(
            """INSERT INTO capital_events
                (event_key, ticker, event_type, description,
                 amount, expected_date, dilution_pct, impact,
                 source, status, added_date)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
               ON CONFLICT (event_key) DO UPDATE SET
                 description = EXCLUDED.description,
                 amount = EXCLUDED.amount,
                 expected_date = EXCLUDED.expected_date,
                 dilution_pct = EXCLUDED.dilution_pct,
                 impact = EXCLUDED.impact,
                 source = EXCLUDED.source,
                 updated_at = NOW()""",
            data["event_key"],
            data["ticker"],
            data["event_type"],
            data["description"],
            data.get("amount", ""),
            data["expected_date"],
            dilution,
            data.get("impact", "WATCH"),
            data.get("source"),
            data.get("status", "pending"),
            data.get("added_date", date.today()),
        )
        return True
    except Exception as e:
        logger.warning("Failed to upsert capital event: %s", e)
        return False


async def refresh_catalyst_lifecycle() -> dict:
    """Daily lifecycle transitions for non-terminal catalysts."""
    db = await get_db()
    counts = {"imminent": 0, "expired": 0, "confidence_decay": 0}

    try:
        # 1. active → imminent when expected_date within 21 days
        result = await db.execute(
            """UPDATE catalysts
               SET status = 'imminent', updated_at = NOW()
               WHERE expected_date IS NOT NULL
                 AND expected_date - CURRENT_DATE BETWEEN 0 AND 21
                 AND status IN ('active', 'monitoring')""",
        )
        counts["imminent"] = int((result or "UPDATE 0").split()[-1])

        # 2. → expired when expected_date passed by 14+ days (matches phase grace period).
        # Phased catalysts are auto-expired too, but only after 30 days of no
        # confirmation. Without this gate, agent-authored phased catalysts
        # (enabled by RC1) turn into undead rows the next time the shock
        # resolves and news stops mentioning them.
        result = await db.execute(
            """UPDATE catalysts
               SET status = 'expired', updated_at = NOW()
               WHERE status NOT IN ('resolved', 'expired')
                 AND (
                      (expected_date IS NOT NULL
                         AND expected_date + 14 < CURRENT_DATE
                         AND phases IS NULL)
                   OR (phases IS NOT NULL
                         AND last_confirmed_at < NOW() - INTERVAL '30 days')
                 )""",
        )
        counts["expired"] = int((result or "UPDATE 0").split()[-1])

        # 2b. NULL expected_date + no phases have no date-based expiry path
        result = await db.execute(
            """UPDATE catalysts
               SET status = 'expired', updated_at = NOW()
               WHERE status NOT IN ('resolved', 'expired')
                 AND expected_date IS NULL
                 AND phases IS NULL
                 AND (
                      (confidence = 'LOW'
                         AND last_confirmed_at < NOW() - INTERVAL '45 days')
                   OR (last_confirmed_at < NOW() - INTERVAL '90 days')
                 )""",
        )
        counts["expired"] += int((result or "UPDATE 0").split()[-1])

        # 2c. SWI-18 (2026-04-27): tighter staleness for `unparseable` rows.
        # An LLM emitted a temporal token the parser couldn't resolve — the
        # row entered the DB with NULL `expected_date` AND a structured flag
        # saying parsing failed. Fast-stale at 14d from `last_confirmed_at`
        # so genuine parse failures don't escape the imminent gate forever.
        # Additive over 2b — `ongoing` rows (intentionally dateless) keep
        # the legacy 45/90d window. Same status guard as the other branches.
        result = await db.execute(
            """UPDATE catalysts
               SET status = 'expired', updated_at = NOW()
               WHERE status NOT IN ('resolved', 'expired')
                 AND expected_date IS NULL
                 AND phases IS NULL
                 AND expected_status = 'unparseable'
                 AND last_confirmed_at < NOW() - INTERVAL '14 days'""",
        )
        counts["expired"] += int((result or "UPDATE 0").split()[-1])

        # 3. Confidence decay: HIGH → MEDIUM after 14d, MEDIUM → LOW after 28d
        result = await db.execute(
            """UPDATE catalysts
               SET confidence = 'MEDIUM', updated_at = NOW()
               WHERE confidence = 'HIGH'
                 AND last_confirmed_at < NOW() - INTERVAL '14 days'
                 AND status IN ('active', 'monitoring', 'imminent')""",
        )
        counts["confidence_decay"] += int((result or "UPDATE 0").split()[-1])

        result = await db.execute(
            """UPDATE catalysts
               SET confidence = 'LOW', updated_at = NOW()
               WHERE confidence = 'MEDIUM'
                 AND last_confirmed_at < NOW() - INTERVAL '28 days'
                 AND status IN ('active', 'monitoring', 'imminent')""",
        )
        counts["confidence_decay"] += int((result or "UPDATE 0").split()[-1])

    except Exception as e:
        logger.warning("Failed to refresh catalyst lifecycle: %s", e)

    return counts


async def link_catalyst_articles(catalyst_key: str, article_ids: list[str]) -> int:
    """Link source articles to a catalyst via the bridge table (batch insert)."""
    if not article_ids:
        return 0
    db = await get_db()
    try:
        await db.execute_many(
            """INSERT INTO catalyst_articles (catalyst_key, article_id)
               VALUES ($1, $2)
               ON CONFLICT DO NOTHING""",
            [(catalyst_key, article_id) for article_id in article_ids],
        )
        return len(article_ids)
    except Exception as error:
        logger.warning("Failed to link articles to catalyst %s: %s", catalyst_key, error)
        return 0


# ── Freshness monitor (SWI-64) ─────────────────────────────────


async def assert_catalyst_freshness(max_age_days: int = 2) -> list[dict]:
    """Return active catalysts whose ``last_updated`` is older than the
    threshold. SWI-64: the news-check write-back now refreshes every
    checked key (not just signal-producers), so any row this monitor
    surfaces points at a real upstream gap (catalyst missing from the
    active set, refresh job not running, etc.). Verifier — never raises;
    callers log loudly.
    """
    db = await get_db()
    rows = await db.fetch_all(
        """SELECT catalyst_key, last_updated
             FROM catalysts
            WHERE status IN ('active', 'monitoring', 'imminent')
              AND pipeline_version = 'v2'
              AND (last_updated IS NULL OR last_updated < CURRENT_DATE - ($1 * INTERVAL '1 day'))""",
        max_age_days,
    )
    return [dict(row) for row in rows]


# ── Helpers ────────────────────────────────────────────────────


def _row_to_dict(row) -> dict:
    """Convert DB row to dict, parsing JSONB phases if string."""
    row_dict = dict(row)
    phases = row_dict.get("phases")
    if isinstance(phases, str):
        row_dict["phases"] = json.loads(phases)
    return row_dict


# ── Sync wrappers (standalone CLI only) ────────────────────────

get_active_catalysts_db_sync = make_sync(get_active_catalysts_db)
get_upcoming_capital_events_db_sync = make_sync(get_upcoming_capital_events_db)
upsert_catalyst_sync = make_sync(upsert_catalyst)
upsert_capital_event_sync = make_sync(upsert_capital_event)
complete_catalyst_sync = make_sync(complete_catalyst)
refresh_catalyst_lifecycle_sync = make_sync(refresh_catalyst_lifecycle)
link_catalyst_articles_sync = make_sync(link_catalyst_articles)
