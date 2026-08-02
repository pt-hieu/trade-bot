"""Watchlist queries and management operations."""

import logging
from collections import defaultdict

from ..database import get_db
from ._sync import make_sync
from ._types import LongtermWatchlistEntry, RemoveStockResult, SwingWatchlistRsiEntry
from ._utils import safe_float

logger = logging.getLogger(__name__)

# ============================================================================
# Queries
# ============================================================================


async def get_swing_watchlist() -> dict[str, list[str]]:
    """Query Swing Watchlist grouped by sector."""
    db = await get_db()
    rows = await db.fetch_all("""
        SELECT sw.ticker, s.name as sector
        FROM swing_watchlist sw
        JOIN sectors s ON s.id = sw.sector_id
        WHERE sw.is_active = TRUE
        ORDER BY s.name, sw.ticker
    """)

    watchlist: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        sector_key = row["sector"].lower().replace(" ", "_").replace("-", "_")
        watchlist[sector_key].append(row["ticker"])

    return dict(watchlist)


async def get_longterm_watchlist() -> dict[str, LongtermWatchlistEntry]:
    """Query Long-Term Watchlist from database."""
    db = await get_db()
    rows = await db.fetch_all("""
        SELECT lw.ticker, lw.entry_zone_vnd, lw.conviction, lw.updated_at, s.name as sector
        FROM longterm_watchlist lw
        JOIN sectors s ON s.id = lw.sector_id
        WHERE lw.is_active = TRUE
        ORDER BY lw.ticker
    """)

    watchlist = {}
    for row in rows:
        watchlist[row["ticker"]] = {
            "entry_zone": int(row["entry_zone_vnd"]) if row["entry_zone_vnd"] else 0,
            "conviction": row["conviction"] or "Medium",
            "sector": row["sector"] or "",
            "updated_at": row.get("updated_at"),
        }

    return watchlist


async def load_all_watchlist_tickers() -> set[str]:
    """Return the union of active swing + longterm watchlist tickers.

    Convenience helper consumed by catalyst revision, which still enforces
    "never widen the tradable set" (see phase_catalyst_revision_picks.py).
    Phase 0 rally_readmit CAN widen via the `rally_volume_new` trigger
    (SWI-322, 2026-05-11); catalyst revision inherits that widened set
    by reading the resulting active swing_watchlist rows here.
    Returned tickers are upper-cased.
    """
    db = await get_db()
    rows = await db.fetch_all("""
        SELECT ticker FROM swing_watchlist WHERE is_active = TRUE
        UNION
        SELECT ticker FROM longterm_watchlist WHERE is_active = TRUE
    """)
    return {row["ticker"].upper() for row in rows if row.get("ticker")}


async def get_swing_watchlist_with_rsi() -> list[SwingWatchlistRsiEntry]:
    """Query Swing Watchlist with RSI values and pinned status."""
    db = await get_db()
    rows = await db.fetch_all("""
        SELECT sw.ticker, s.name as sector, sw.stock_type, sw.rsi, sw.is_pinned
        FROM swing_watchlist sw
        JOIN sectors s ON s.id = sw.sector_id
        WHERE sw.is_active = TRUE
        ORDER BY s.name, sw.ticker
    """)

    return [
        {
            "ticker": row["ticker"],
            "sector": row["sector"],
            "stock_type": row["stock_type"],
            "rsi": safe_float(row["rsi"]),
            "is_pinned": row.get("is_pinned", False) or False,
        }
        for row in rows
    ]


# ============================================================================
# Management Operations
# ============================================================================


async def update_swing_rsi_batch(rsi_data: dict[str, float]) -> int:
    """Batch update RSI values in Swing Watchlist."""
    if not rsi_data:
        return 0

    db = await get_db()
    args_list = [(rsi, ticker.upper()) for ticker, rsi in rsi_data.items()]

    try:
        await db.execute_many(
            """
            UPDATE swing_watchlist
            SET rsi = $1, updated_at = NOW()
            WHERE ticker = $2
        """,
            args_list,
        )
        return len(args_list)
    except Exception as e:
        logger.warning("Batch RSI update failed: %s", e)
        return 0


async def add_swing_stock(ticker: str, sector: str, stock_type: str = "Private") -> bool:
    """Add a new stock to the Swing Watchlist."""
    db = await get_db()

    try:
        sector_id = await db.fetch_val(
            """
            SELECT id FROM sectors WHERE LOWER(display_name) = LOWER($1)
        """,
            sector,
        )

        if not sector_id:
            logger.error(
                "Sector display_name lookup failed for %s sector=%r — pass display_name "
                "(e.g. 'Real Estate'), not snake_case name (e.g. 'real_estate')",
                ticker,
                sector,
            )
            return False

        # is_pinned intentionally preserved on UPSERT — an existing pin survives
        # reactivation. SWI-322: new INSERT path defaults is_pinned=FALSE explicitly.
        await db.execute(
            """
            INSERT INTO swing_watchlist (ticker, sector_id, stock_type, is_active, is_pinned)
            VALUES ($1, $2, $3, TRUE, FALSE)
            ON CONFLICT (ticker) DO UPDATE
                SET is_active = TRUE, sector_id = EXCLUDED.sector_id
        """,
            ticker.upper(),
            sector_id,
            stock_type,
        )

        logger.info("Added %s (%s) to watchlist", ticker, sector)
        return True
    except Exception as e:
        logger.warning("Failed to add %s: %s", ticker, e)
        return False


async def remove_swing_stock(ticker: str) -> RemoveStockResult:
    """Remove a stock from the Swing Watchlist (soft delete).

    Pinned stocks are skipped — they cannot be auto-removed.

    Returns:
        dict with {removed: bool, pinned: bool, reason: str}
    """
    db = await get_db()

    try:
        row = await db.fetch_one(
            "SELECT is_pinned, pin_reason FROM swing_watchlist WHERE ticker = $1 AND is_active = TRUE",
            ticker.upper(),
        )

        if row and row.get("is_pinned"):
            reason = row.get("pin_reason") or "Stock is pinned"
            logger.info("Skipped %s removal: PINNED (%s)", ticker, reason)
            return {"removed": False, "pinned": True, "reason": reason}

        result = await db.execute(
            """
            UPDATE swing_watchlist
            SET is_active = FALSE, updated_at = NOW()
            WHERE ticker = $1 AND (is_pinned = FALSE OR is_pinned IS NULL)
        """,
            ticker.upper(),
        )

        if "UPDATE 0" in result:
            logger.warning("Ticker %s not found in Swing Watchlist for removal", ticker)
            return {"removed": False, "pinned": False, "reason": "Not found"}

        logger.info("Removed %s from watchlist", ticker)
        return {"removed": True, "pinned": False, "reason": ""}
    except Exception as e:
        logger.warning("Failed to remove %s: %s", ticker, e)
        return {"removed": False, "pinned": False, "reason": str(e)}


async def pin_swing_stock(ticker: str, reason: str = "") -> bool:
    """Pin a stock so it cannot be removed by automated updates."""
    db = await get_db()
    try:
        result = await db.execute(
            """
            UPDATE swing_watchlist
            SET is_pinned = TRUE, pin_reason = $2, updated_at = NOW()
            WHERE ticker = $1
        """,
            ticker.upper(),
            reason,
        )
        success = "UPDATE 0" not in result
        if success:
            logger.info("Pinned %s: %s", ticker, reason)
        return success
    except Exception as e:
        logger.warning("Failed to pin %s: %s", ticker, e)
        return False


async def unpin_swing_stock(ticker: str) -> bool:
    """Unpin a stock so it can be removed by automated updates."""
    db = await get_db()
    try:
        result = await db.execute(
            """
            UPDATE swing_watchlist
            SET is_pinned = FALSE, pin_reason = NULL, updated_at = NOW()
            WHERE ticker = $1
        """,
            ticker.upper(),
        )
        success = "UPDATE 0" not in result
        if success:
            logger.info("Unpinned %s", ticker)
        return success
    except Exception as e:
        logger.warning("Failed to unpin %s: %s", ticker, e)
        return False


async def ensure_stock_exists(ticker: str) -> bool:
    """Ensure stock exists in stocks table."""
    db = await get_db()
    exists = await db.fetch_val("SELECT 1 FROM stocks WHERE ticker = $1", ticker)
    if not exists:
        await db.execute(
            """
            INSERT INTO stocks (ticker, sector_id, stock_type)
            VALUES ($1, 1, 'Private')
            ON CONFLICT DO NOTHING
            """,
            ticker,
        )
    return True


# ============================================================================
# Sector Peers
# ============================================================================


async def get_sector_peers(ticker: str) -> list[str]:
    """Return tickers from the same sector as the given ticker.

    Searches both swing_watchlist and longterm_watchlist, deduplicates,
    excludes the target ticker itself. Returns up to 15 peers.
    """
    db = await get_db()
    rows = await db.fetch_all(
        """
        WITH target_sector AS (
            SELECT sector_id FROM swing_watchlist WHERE ticker = $1 AND is_active = TRUE
            UNION
            SELECT sector_id FROM longterm_watchlist WHERE ticker = $1 AND is_active = TRUE
            LIMIT 1
        )
        SELECT DISTINCT sw.ticker FROM swing_watchlist sw
        JOIN target_sector ts ON sw.sector_id = ts.sector_id
        WHERE sw.is_active = TRUE AND sw.ticker != $1
        UNION
        SELECT DISTINCT lw.ticker FROM longterm_watchlist lw
        JOIN target_sector ts ON lw.sector_id = ts.sector_id
        WHERE lw.is_active = TRUE AND lw.ticker != $1
        LIMIT 15
        """,
        ticker.upper(),
    )
    return [row["ticker"] for row in rows]


# ============================================================================
# Sync Wrappers
# ============================================================================

get_swing_watchlist_sync = make_sync(get_swing_watchlist)
get_longterm_watchlist_sync = make_sync(get_longterm_watchlist)
update_swing_rsi_batch_sync = make_sync(update_swing_rsi_batch)
add_swing_stock_sync = make_sync(add_swing_stock)
remove_swing_stock_sync = make_sync(remove_swing_stock)
pin_swing_stock_sync = make_sync(pin_swing_stock)
unpin_swing_stock_sync = make_sync(unpin_swing_stock)
