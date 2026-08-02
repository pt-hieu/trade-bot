"""Insert strategy insights (per-strategy win rates) from retro pipeline."""

import logging
from datetime import date

from ..database import get_db
from ._sync import make_sync

logger = logging.getLogger(__name__)


async def insert_strategy_insights(
    strategy_patterns: dict,
    scan_date: date | str | None = None,
) -> bool:
    """Persist per-strategy win rates to strategy_insights table.

    Args:
        strategy_patterns: Dict of {strategy: {win_rate, sample_size}}
            as produced by update_learnings() in retro_helpers/learnings.py.
        scan_date: Date for this snapshot. Defaults to today.
    """
    if not strategy_patterns:
        logger.info("No strategy patterns to insert")
        return True

    if isinstance(scan_date, str):
        scan_date = date.fromisoformat(scan_date)
    scan_date = scan_date or date.today()

    db = await get_db()

    try:
        await db.execute(
            "DELETE FROM strategy_insights WHERE scan_date = $1",
            scan_date,
        )

        for strategy_name, stats in strategy_patterns.items():
            await db.execute(
                """
                INSERT INTO strategy_insights (strategy, win_rate, sample_size, scan_date)
                VALUES ($1, $2, $3, $4)
                """,
                strategy_name,
                stats.get("win_rate"),
                stats.get("sample_size"),
                scan_date,
            )

        logger.info(
            "Inserted %d strategy insights for %s",
            len(strategy_patterns),
            scan_date,
        )
        return True
    except Exception as error:
        logger.warning(
            "Failed to insert strategy insights (scan_date=%s, count=%d): %s",
            scan_date,
            len(strategy_patterns),
            error,
        )
        return False


insert_strategy_insights_sync = make_sync(insert_strategy_insights)
