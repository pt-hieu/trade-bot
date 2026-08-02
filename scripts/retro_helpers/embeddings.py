"""
Embedding generation for retrospective memory system.
Extracted from retrospective.py for the 300-line file limit.
"""

from shared.database import get_db


async def generate_embeddings(
    scan_date,
    rotation_eval: dict | None,
    macro_eval: dict | None,
    midday_data: dict | None,
) -> None:
    """
    Generate and store embeddings for daily record and learning patterns.

    Called after DB inserts so records exist. Non-fatal — logs errors and continues.
    """
    from agents.memory.embeddings import embed_context
    from shared.neon.memory import update_daily_record_embedding, update_pattern_embedding

    db = await get_db()

    # 1. Embed daily record context
    try:
        regime_row = await db.fetch_one(
            "SELECT regime FROM market_regimes WHERE scan_date = $1",
            scan_date,
        )
        market_regime = regime_row["regime"] if regime_row else "NEUTRAL"

        context = {
            "market_regime": market_regime,
            "global_macro": macro_eval.get("global_risk_regime") if macro_eval else None,
            "hot_sectors": rotation_eval.get("hot_sectors", []) if rotation_eval else [],
            "cold_sectors": rotation_eval.get("cold_sectors", []) if rotation_eval else [],
            "vix": float(macro_eval["vix_value"])
            if macro_eval and macro_eval.get("vix_value")
            else None,
            "trading_mode": midday_data.get("trading_mode") if midday_data else None,
        }
        embedding = embed_context(context)
        if embedding:
            if await update_daily_record_embedding(scan_date, embedding):
                print(f"  Embedded daily record ({len(embedding)} dims)")
            else:
                print("  Warning: failed to store daily record embedding")
        else:
            print("  Warning: embedding model returned None")
    except Exception as e:
        print(f"  Warning: daily record embedding failed: {e}")

    # 2. Embed all learning patterns (replaced on each run, so embed all)
    try:
        rows = await db.fetch_all(
            "SELECT id, pattern_type, pattern_description, win_rate FROM learning_patterns",
        )
        embedded = 0
        for row in rows:
            ctx = {
                "pattern": row["pattern_description"],
                "pattern_type": row["pattern_type"],
                "win_rate": float(row["win_rate"]) if row["win_rate"] is not None else 0,
            }
            emb = embed_context(ctx)
            if emb:
                await update_pattern_embedding(str(row["id"]), emb)
                embedded += 1
        print(f"  Embedded {embedded}/{len(rows)} learning patterns")
    except Exception as e:
        print(f"  Warning: pattern embedding failed: {e}")
