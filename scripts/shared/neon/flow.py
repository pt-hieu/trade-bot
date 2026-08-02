"""Foreign flow queries (single-date, history, streak)."""

import asyncio
from datetime import date

from ..database import get_db
from ._utils import safe_float


async def get_foreign_flow(scan_date: date | None = None) -> dict:
    """Get foreign flow data for a given date."""
    if scan_date is None:
        scan_date = date.today()

    db = await get_db()
    row = await db.fetch_one(
        """
        SELECT id, net_value_billion, buy_value_billion, sell_value_billion,
               signal, pattern, interpretation
        FROM foreign_flows WHERE scan_date = $1
    """,
        scan_date,
    )

    if not row:
        return {"error": f"No foreign flow data found for {scan_date}"}

    flow_id = row["id"]
    top_bought, top_sold = await asyncio.gather(
        db.fetch_all(
            """
            SELECT ticker, value_billion, buy_value_billion, sell_value_billion,
                   net_value_billion, ownership_pct
            FROM foreign_flow_details
            WHERE flow_id = $1 AND flow_type = 'bought'
            ORDER BY rank
        """,
            flow_id,
        ),
        db.fetch_all(
            """
            SELECT ticker, value_billion, buy_value_billion, sell_value_billion,
                   net_value_billion, ownership_pct
            FROM foreign_flow_details
            WHERE flow_id = $1 AND flow_type = 'sold'
            ORDER BY rank
        """,
            flow_id,
        ),
    )

    def _flow_detail(row_data: dict) -> dict:
        return {
            "ticker": row_data["ticker"],
            "value_billion": safe_float(row_data["value_billion"], default=0),
            "buy_value_billion": safe_float(row_data["buy_value_billion"]),
            "sell_value_billion": safe_float(row_data["sell_value_billion"]),
            "net_value_billion": safe_float(row_data["net_value_billion"]),
            "ownership_pct": safe_float(row_data["ownership_pct"]),
        }

    return {
        "net_value_billion": safe_float(row["net_value_billion"], default=0),
        "buy_value_billion": safe_float(row["buy_value_billion"], default=0),
        "sell_value_billion": safe_float(row["sell_value_billion"], default=0),
        "signal": row["signal"] or "",
        "pattern": row["pattern"] or "",
        "interpretation": row["interpretation"] or "",
        "top_bought": [_flow_detail(dict(detail_row)) for detail_row in top_bought],
        "top_sold": [_flow_detail(dict(detail_row)) for detail_row in top_sold],
    }


async def get_foreign_flow_history(days: int = 5) -> list[dict]:
    """Get aggregate foreign flow for the last N trading days."""
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT scan_date, net_value_billion, signal, pattern
        FROM foreign_flows
        ORDER BY scan_date DESC LIMIT $1
    """,
        days,
    )
    return [
        {
            "date": str(row["scan_date"]),
            "net": safe_float(row["net_value_billion"], default=0),
            "signal": row["signal"] or "",
            "pattern": row["pattern"] or "",
        }
        for row in rows
    ]


async def get_ticker_flow_streak(ticker: str, days: int = 5) -> list[dict]:
    """Get per-ticker foreign flow for the last N trading days."""
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT ff.scan_date, ffd.net_value_billion
        FROM foreign_flow_details ffd
        JOIN foreign_flows ff ON ff.id = ffd.flow_id
        WHERE ffd.ticker = $1
        ORDER BY ff.scan_date DESC LIMIT $2
    """,
        ticker.upper(),
        days,
    )
    return [
        {
            "date": str(row["scan_date"]),
            "net": safe_float(row["net_value_billion"], default=0),
        }
        for row in rows
    ]


async def get_ticker_flow_streak_batch(tickers: list[str], days: int = 5) -> dict[str, list[dict]]:
    """Get per-ticker foreign flow for the last N trading days in one query.

    Uses ROW_NUMBER() to keep only the top-N most recent days per ticker.
    Returns dict mapping uppercased ticker to list of {date, net} ordered newest first.
    """
    if not tickers:
        return {}

    normalized = [ticker.upper() for ticker in tickers]
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT ticker, scan_date, net_value_billion
        FROM (
            SELECT ffd.ticker,
                   ff.scan_date,
                   ffd.net_value_billion,
                   ROW_NUMBER() OVER (
                       PARTITION BY ffd.ticker
                       ORDER BY ff.scan_date DESC
                   ) AS rn
            FROM foreign_flow_details ffd
            JOIN foreign_flows ff ON ff.id = ffd.flow_id
            WHERE ffd.ticker = ANY($1::text[])
        ) ranked
        WHERE rn <= $2
        ORDER BY ticker, scan_date DESC
        """,
        normalized,
        days,
    )
    result: dict[str, list[dict]] = {ticker: [] for ticker in normalized}
    for row in rows:
        result[row["ticker"]].append(
            {
                "date": str(row["scan_date"]),
                "net": safe_float(row["net_value_billion"], default=0),
            }
        )
    return result
