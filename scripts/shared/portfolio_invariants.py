"""Pre-flight portfolio invariants checked at pipeline startup.

After migration 318 merged the FPT dual-listed slices into a single row,
the portfolio has no dual-listed tickers. This invariant fires loudly if a
user action re-creates a dual-listed state so we revisit the decision
rather than silently collapsing one slice downstream.
"""

from __future__ import annotations

import sys


class PortfolioInvariantError(RuntimeError):
    """Raised when a startup portfolio invariant fails."""


async def assert_no_dual_listed_tickers() -> None:
    """Abort if any ticker appears on more than one `portfolio_holdings` row.

    Reason: the renderer / alert / P/L paths all special-cased dual-listed
    tickers before migration 318. Reintroducing the state silently would
    revive the class of bugs the merge was meant to close.
    """
    from shared.database import get_db

    db = await get_db()
    rows = await db.fetch_all(
        """
        SELECT ticker, COUNT(*) AS slice_count
          FROM portfolio_holdings
         GROUP BY ticker
        HAVING COUNT(*) > 1
        """
    )
    if rows:
        detail = ", ".join(f"{r['ticker']}×{r['slice_count']}" for r in rows)
        raise PortfolioInvariantError(
            "DUAL_LISTED_TICKER: portfolio_holdings contains >1 row for "
            f"ticker(s): {detail}. The renderer + alert paths assume one "
            "row per ticker since migration 318. Decide explicitly whether "
            "to re-introduce dual listing (and teach the renderer to handle "
            "it) before proceeding."
        )


def report_invariant_and_exit(exc: PortfolioInvariantError) -> None:
    """Print a remediation block for `exc` and `sys.exit(1)`."""
    print(f"[portfolio-invariant] ABORT: {exc}", flush=True)
    print(
        "[portfolio-invariant] Fix: merge the duplicate slices with a migration that "
        "keeps one row per (ticker, plan_type): set shares to the sum, and avg_cost to "
        "SUM(shares * avg_cost) / SUM(shares), then delete the absorbed row.",
        flush=True,
    )
    sys.exit(1)
