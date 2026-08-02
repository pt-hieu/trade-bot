"""Data fetchers + metric computation for the Phase 0 rally_readmit pass.

Split out of rally_readmit.py to keep each module under the 350-line cap.
Pure I/O + numeric helpers — no orchestration logic lives here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from shared.database import get_db

try:
    import logfire as _logfire
except ImportError:  # logfire optional in unit tests / local dev
    _logfire = None

logger = logging.getLogger(__name__)


async def fetch_deactivated_swing_rows() -> list[dict]:
    """Deactivated, non-pinned swing rows with sector display_name resolved."""
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT sw.ticker, s.display_name AS sector
        FROM swing_watchlist sw
        LEFT JOIN sectors s ON s.id = sw.sector_id
        WHERE sw.is_active = FALSE
          AND (sw.is_pinned = FALSE OR sw.is_pinned IS NULL)
        """
    )
    return [{"ticker": r["ticker"], "sector": r["sector"]} for r in rows]


async def fetch_active_swing_tickers() -> set[str]:
    db = await get_db()
    rows = await db.fetch_all("SELECT ticker FROM swing_watchlist WHERE is_active = TRUE")
    return {r["ticker"].upper() for r in rows}


async def fetch_prior_swing_tickers() -> set[str]:
    """All tickers that have EVER had a swing_watchlist row (active or not)."""
    db = await get_db()
    rows = await db.fetch_all("SELECT ticker FROM swing_watchlist")
    return {r["ticker"].upper() for r in rows}


async def fetch_longterm_with_sector() -> dict[str, str | None]:
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT lw.ticker, s.display_name AS sector
        FROM longterm_watchlist lw
        LEFT JOIN sectors s ON s.id = lw.sector_id
        WHERE lw.is_active = TRUE
        """
    )
    return {r["ticker"].upper(): r["sector"] for r in rows}


async def fetch_stock_sector(ticker: str) -> str | None:
    db = await get_db()
    return await db.fetch_val(
        """
        SELECT s.display_name FROM stocks st
        LEFT JOIN sectors s ON s.id = st.sector_id
        WHERE st.ticker = $1
        """,
        ticker.upper(),
    )


async def fetch_new_universe_candidates() -> dict[str, str | None]:
    """SWI-322: {ticker: sector_display_name} for stocks NOT in swing_watchlist
    AND NOT in longterm_watchlist.

    Returns display_name (NOT name slug) to honor the add_swing_stock contract
    at watchlist.py:132 which matches on LOWER(display_name).
    """
    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT st.ticker, s.display_name AS sector
        FROM stocks st
        JOIN sectors s ON s.id = st.sector_id
        LEFT JOIN swing_watchlist sw ON sw.ticker = st.ticker
        LEFT JOIN longterm_watchlist lw ON lw.ticker = st.ticker
        WHERE st.sector_id IS NOT NULL
          AND sw.ticker IS NULL
          AND lw.ticker IS NULL
        """
    )
    return {r["ticker"].upper(): r["sector"] for r in rows}


async def fetch_high_positive_catalyst_tickers() -> dict[str, str]:
    """{ticker: catalyst_key} for active HIGH-confidence POSITIVE catalysts."""
    try:
        from shared.neon.catalyst_filters import filter_high_positive_catalyst_tickers
        from shared.neon.catalyst_summaries import get_active_catalysts

        rows = await get_active_catalysts()
    except Exception as exc:
        logger.warning("rally_readmit: get_active_catalysts failed: %s", exc, exc_info=True)
        return {}
    return filter_high_positive_catalyst_tickers(rows)


def compute_5d_return_and_vol_ratio(
    bars: list[dict],
) -> tuple[float | None, float | None]:
    """Compute ret_5d (close vs close 5 trading days back) and vol_ratio_20d.

    Bars are newest-last. Returns (None, None) if insufficient data.
    """
    if not bars or len(bars) < 6:
        return None, None
    try:
        last_close = float(bars[-1].get("close") or 0)
        prior_close = float(bars[-6].get("close") or 0)
    except (TypeError, ValueError):
        return None, None
    if prior_close <= 0 or last_close <= 0:
        return None, None
    ret_5d = (last_close - prior_close) / prior_close

    last_vol = float(bars[-1].get("volume") or 0)
    window = bars[-21:-1] if len(bars) >= 21 else bars[:-1]
    if not window:
        return ret_5d, None
    avg_vol = sum(float(b.get("volume") or 0) for b in window) / len(window)
    vol_ratio = (last_vol / avg_vol) if avg_vol > 0 else None
    return ret_5d, vol_ratio


async def fetch_metrics(
    tickers: list[str],
) -> dict[str, tuple[float | None, float | None]]:
    """{ticker: (ret_5d, vol_ratio_20d)}. Empty dict on fetch failure."""
    if not tickers:
        return {}
    from shared.vnstock_client import fetch_history_batch

    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")
    try:
        raw = await fetch_history_batch(tickers, start=start, end=end)
    except Exception as exc:
        logger.warning("rally_readmit: fetch_history_batch failed: %s", exc, exc_info=True)
        if _logfire is not None:
            _logfire.error("rally_readmit_technicals_failed", error=str(exc))
        return {}

    metrics: dict[str, tuple[float | None, float | None]] = {}
    for ticker, payload in raw.items():
        bars = payload.get("data", []) if isinstance(payload, dict) else []
        ret_5d, vol_ratio = compute_5d_return_and_vol_ratio(bars)
        metrics[ticker.upper()] = (ret_5d, vol_ratio)
    return metrics
