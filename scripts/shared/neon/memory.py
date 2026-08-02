"""Vector similarity search functions (Memory System)."""

from datetime import date
from typing import Any

from ..database import get_db
from ._sync import make_sync
from ._utils import safe_float


async def find_similar_days(
    context_embedding: list[float] | None,
    limit: int = 5,
    min_similarity: float = 0.7,
) -> list[dict]:
    """Find past trading days with similar market context via pgvector cosine similarity."""
    if context_embedding is None:
        return []

    db = await get_db()

    embedding_str = str(context_embedding)

    rows = await db.fetch_all(
        """
        SELECT
            record_date,
            market_regime,
            trading_mode,
            total_recs,
            win_rate,
            best_call,
            worst_call,
            key_insight,
            1 - (context_embedding <=> $1::vector) as similarity
        FROM daily_records
        WHERE context_embedding IS NOT NULL
        ORDER BY context_embedding <=> $1::vector
        LIMIT $2
        """,
        embedding_str,
        limit,
    )

    return [
        {
            "record_date": row["record_date"],
            "market_regime": row["market_regime"],
            "trading_mode": row["trading_mode"],
            "total_recs": row["total_recs"],
            "win_rate": safe_float(row["win_rate"]),
            "best_call": row["best_call"],
            "worst_call": row["worst_call"],
            "key_insight": row["key_insight"],
            "similarity": float(row["similarity"]),
        }
        for row in rows
        if row["similarity"] >= min_similarity
    ]


async def find_similar_patterns(
    pattern_embedding: list[float] | None,
    pattern_type: str = "winning",
    limit: int = 5,
    min_similarity: float = 0.6,
) -> list[dict]:
    """Find learning patterns similar to given embedding. Returns patterns with rules."""
    if pattern_embedding is None:
        return []

    db = await get_db()

    embedding_str = str(pattern_embedding)

    rows = await db.fetch_all(
        """
        SELECT
            pattern_description,
            win_rate,
            loss_rate,
            sample_size,
            actionable_rule,
            avoid_rule,
            1 - (pattern_embedding <=> $1::vector) as similarity
        FROM learning_patterns
        WHERE pattern_type = $2
          AND pattern_embedding IS NOT NULL
        ORDER BY pattern_embedding <=> $1::vector
        LIMIT $3
        """,
        embedding_str,
        pattern_type,
        limit,
    )

    return [
        {
            "pattern_description": row["pattern_description"],
            "win_rate": safe_float(row["win_rate"]),
            "loss_rate": safe_float(row["loss_rate"]),
            "sample_size": row["sample_size"],
            "actionable_rule": row["actionable_rule"],
            "avoid_rule": row["avoid_rule"],
            "similarity": float(row["similarity"]),
        }
        for row in rows
        if row["similarity"] >= min_similarity
    ]


async def find_applicable_rules(
    regime: str | None = None,
    sectors: list[str] | None = None,
    rsi: float | None = None,
    macro: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Find trading rules matching current conditions, sorted by confidence."""
    db = await get_db()

    conditions = ["confidence >= 0.6", "(expires_at IS NULL OR expires_at >= CURRENT_DATE)"]
    params: list[Any] = []
    param_idx = 1

    if regime:
        conditions.append(
            f"(${param_idx}::market_regime = ANY(condition_regime) OR condition_regime IS NULL)"
        )
        params.append(regime)
        param_idx += 1

    if sectors:
        conditions.append(
            f"(${param_idx}::text[] && condition_sectors::text[] OR condition_sectors IS NULL)"
        )
        params.append(sectors)
        param_idx += 1

    if rsi is not None:
        conditions.append(
            f"(${param_idx}::int <@ condition_rsi_range OR condition_rsi_range IS NULL)"
        )
        params.append(int(rsi))
        param_idx += 1

    if macro:
        conditions.append(f"(${param_idx}::text = ANY(condition_macro) OR condition_macro IS NULL)")
        params.append(macro)
        param_idx += 1

    params.append(limit)

    query = f"""
        SELECT
            rule_name,
            rule_type,
            description,
            action,
            confidence,
            sample_size,
            last_validated
        FROM trading_rules
        WHERE {" AND ".join(conditions)}
        ORDER BY confidence DESC, sample_size DESC NULLS LAST
        LIMIT ${param_idx}
    """

    rows = await db.fetch_all(query, *params)

    return [
        {
            "rule_name": row["rule_name"],
            "rule_type": row["rule_type"],
            "description": row["description"],
            "action": row["action"],
            "confidence": float(row["confidence"]),
            "sample_size": row["sample_size"],
            "last_validated": row["last_validated"],
        }
        for row in rows
    ]


async def upsert_trading_rule(
    rule_name: str,
    rule_type: str,
    description: str,
    action: str,
    confidence: float,
    condition_regime: list[str] | None = None,
    condition_sectors: list[str] | None = None,
    condition_rsi_range: tuple[int, int] | None = None,
    condition_macro: list[str] | None = None,
    derived_from_pattern_id: str | None = None,
    sample_size: int | None = None,
    rule_embedding: list[float] | None = None,
) -> str | None:
    """Insert or update a trading rule. Returns UUID or None on error."""
    db = await get_db()

    try:
        rsi_range = None
        if condition_rsi_range:
            rsi_range = f"[{condition_rsi_range[0]},{condition_rsi_range[1]})"

        rule_id = await db.fetch_val(
            """
            INSERT INTO trading_rules (
                rule_name, rule_type, description, action, confidence,
                condition_regime, condition_sectors, condition_rsi_range, condition_macro,
                derived_from_pattern_id, sample_size, rule_embedding,
                last_validated, updated_at, expires_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::int4range, $9, $10, $11, $12,
                    CURRENT_DATE, NOW(), CURRENT_DATE + INTERVAL '30 days')
            ON CONFLICT (rule_name) DO UPDATE SET
                description = EXCLUDED.description,
                action = EXCLUDED.action,
                confidence = EXCLUDED.confidence,
                condition_regime = EXCLUDED.condition_regime,
                condition_sectors = EXCLUDED.condition_sectors,
                condition_rsi_range = EXCLUDED.condition_rsi_range,
                condition_macro = EXCLUDED.condition_macro,
                sample_size = EXCLUDED.sample_size,
                rule_embedding = EXCLUDED.rule_embedding,
                last_validated = CURRENT_DATE,
                updated_at = NOW(),
                expires_at = CURRENT_DATE + INTERVAL '30 days'
            RETURNING id
            """,
            rule_name,
            rule_type,
            description,
            action,
            confidence,
            condition_regime,
            condition_sectors,
            rsi_range,
            condition_macro,
            derived_from_pattern_id,
            sample_size,
            rule_embedding,
        )
        return str(rule_id) if rule_id else None
    except Exception as e:
        print(f"  [Neon] Failed to upsert trading rule: {e}")
        return None


async def update_daily_record_embedding(
    record_date: date,
    context_embedding: list[float],
) -> bool:
    """Update context embedding for an existing daily record."""
    db = await get_db()

    try:
        # pgvector expects string format '[0.1,0.2,...]', not list[float]
        embedding_str = "[" + ",".join(str(v) for v in context_embedding) + "]"
        await db.execute(
            """
            UPDATE daily_records
            SET context_embedding = $1
            WHERE record_date = $2
            """,
            embedding_str,
            record_date,
        )
        return True
    except Exception as e:
        print(f"  [Neon] Failed to update daily record embedding: {e}")
        return False


async def update_pattern_embedding(
    pattern_id: str,
    pattern_embedding: list[float],
) -> bool:
    """Update embedding for an existing learning pattern."""
    db = await get_db()

    try:
        # pgvector expects string format '[0.1,0.2,...]', not list[float]
        embedding_str = "[" + ",".join(str(v) for v in pattern_embedding) + "]"
        await db.execute(
            """
            UPDATE learning_patterns
            SET pattern_embedding = $1
            WHERE id = $2
            """,
            embedding_str,
            pattern_id,
        )
        return True
    except Exception as e:
        print(f"  [Neon] Failed to update pattern embedding: {e}")
        return False


# ============================================================================
# Sync Wrappers
# ============================================================================

find_similar_days_sync = make_sync(find_similar_days)
find_similar_patterns_sync = make_sync(find_similar_patterns)
find_applicable_rules_sync = make_sync(find_applicable_rules)
upsert_trading_rule_sync = make_sync(upsert_trading_rule)
update_daily_record_embedding_sync = make_sync(update_daily_record_embedding)
update_pattern_embedding_sync = make_sync(update_pattern_embedding)
