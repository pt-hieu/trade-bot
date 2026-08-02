#!/usr/bin/env python3
"""
Watchlist Update Agent using PydanticAI.

Weekly update of swing trading watchlist - analyzes sentiment, rotation,
and scores stocks for add/remove decisions.
"""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

from pydantic import BaseModel, computed_field

# Sector mapping
SECTOR_MAP = {
    "ACB": "Banking",
    "BID": "Banking",
    "CTG": "Banking",
    "HDB": "Banking",
    "MBB": "Banking",
    "SHB": "Banking",
    "STB": "Banking",
    "TCB": "Banking",
    "TPB": "Banking",
    "VCB": "Banking",
    "VIB": "Banking",
    "VPB": "Banking",
    "BCM": "Real Estate",
    "NLG": "Real Estate",
    "VHM": "Real Estate",
    "VRE": "Real Estate",
    "KBC": "Real Estate",
    "IDC": "Real Estate",
    "FPT": "Technology",
    "SSI": "Securities",
    "VCI": "Securities",
    "HCM": "Securities",
    "VIX": "Securities",
    "VND": "Securities",
    "MSN": "Consumer",
    "MWG": "Consumer",
    "SAB": "Consumer",
    "VNM": "Consumer",
    "VIC": "Real Estate",  # SWI-304: Vingroup parent — peers are Real Estate, not Consumer staples
    "GAS": "State-Owned",
    "GVR": "State-Owned",
    "PLX": "State-Owned",
    "POW": "State-Owned",
    "BVH": "State-Owned",
    "HVN": "State-Owned",
    "HPG": "Infrastructure",
    "PVT": "Infrastructure",
    "PVI": "State-Owned",
    "SZC": "Infrastructure",
    "DXS": "Infrastructure",
}

# VN30 + additional tickers for candidate discovery
VN30_TICKERS = [
    "ACB",
    "BCM",
    "BID",
    "BVH",
    "CTG",
    "FPT",
    "GAS",
    "GVR",
    "HDB",
    "HPG",
    "MBB",
    "MSN",
    "MWG",
    "PLX",
    "POW",
    "SAB",
    "SHB",
    "SSI",
    "STB",
    "TCB",
    "TPB",
    "VCB",
    "VHM",
    "VIB",
    "VIC",
    "VIX",
    "VNM",
    "VPB",
    "VRE",
    "NLG",
    "IDC",
    "KBC",
    "PVT",
    "PVI",
    "SZC",
    "DXS",
    "VCI",
    "HCM",
    "VND",
]

# Crypto-exposed stocks
CRYPTO_EXPOSED = {"TCB": "HIGH", "SSI": "HIGH", "MBB": "HIGH", "VPB": "HIGH", "VIX": "MEDIUM"}


_SCORE_TAG_RE = re.compile(r"\(([+-]\d+)\)")


class StockScore(BaseModel):
    """Score for a stock add/remove decision.

    SWI-295: ``score`` is a ``@computed_field`` derived from `(+N)`/`(-N)`
    tags in ``reasons``. The LLM never authors it — schema theater is gone.
    """

    ticker: str
    sector: str
    confidence: str  # high, medium, low
    reasons: list[str]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def score(self) -> int:
        return sum(int(match) for reason in self.reasons for match in _SCORE_TAG_RE.findall(reason))


class WatchlistUpdateResult(BaseModel):
    """Complete watchlist update recommendation."""

    market_summary: str
    hot_sectors: list[str]
    cold_sectors: list[str]
    rotation_signal: str
    removals: list[StockScore]
    additions: list[StockScore]
    weekly_outlook: str


def _should_block_removal(
    ticker: str,
    technicals: dict,
    holdings: set[str],
    catalyst_tickers: set[str],
) -> tuple[bool, str, float | None]:
    """Deterministic guard: return (block, reason, ret_5d) for a proposed removal.

    SWI-304: prevents the LLM from deactivating a watchlist ticker that is
    rallying, currently held, or attached to an active HIGH-confidence positive
    catalyst. Counterpart to the Phase-0 rally_readmit pre-pass.
    """
    ticker_data = technicals.get(ticker) or {}
    ret_5d = ticker_data.get("ret_5d")
    if ret_5d is None:
        ret_5d_value = None
    else:
        try:
            ret_5d_value = float(ret_5d)
        except (TypeError, ValueError):
            ret_5d_value = None

    if ret_5d_value is not None and ret_5d_value >= 0.05:
        return True, f"rally_block: ret_5d={ret_5d_value:.1%}", ret_5d_value
    if ticker in catalyst_tickers:
        return True, "active_high_catalyst", ret_5d_value
    if ticker in holdings:
        return True, "currently_held", ret_5d_value
    return False, "", ret_5d_value


async def apply_updates(
    result: dict,
    technicals: dict | None = None,
    holdings: set[str] | None = None,
    catalyst_tickers: set[str] | None = None,
) -> tuple[int, int, list[str]]:
    """Apply add/remove updates to database.

    Returns:
        (removed_count, added_count, pinned_skips)
    """
    from shared.neon import add_swing_stock, remove_swing_stock

    technicals = technicals or {}
    holdings = holdings or set()
    catalyst_tickers = catalyst_tickers or set()

    removed = 0
    added = 0
    pinned_skips: list[str] = []

    removals = result.get("removals", [])
    additions = result.get("additions", [])

    for removal in removals:
        ticker = removal["ticker"]
        blocked, reason, ret_5d_value = _should_block_removal(
            ticker, technicals, holdings, catalyst_tickers
        )
        if blocked:
            try:
                import logfire

                logfire.info(
                    "removal_blocked",
                    ticker=ticker,
                    reason=reason,
                    ret_5d=ret_5d_value,
                )
            except Exception:  # logfire optional in tests / dev
                logger.info("removal_blocked: %s reason=%s ret_5d=%s", ticker, reason, ret_5d_value)
            pinned_skips.append(f"{ticker}: {reason}")
            continue
        outcome = await remove_swing_stock(ticker)
        if isinstance(outcome, dict):
            if outcome.get("removed"):
                removed += 1
            elif outcome.get("pinned"):
                pinned_skips.append(f"{ticker}: {outcome.get('reason', 'pinned')}")
            else:
                logger.warning(
                    "Removal failed for %s: %s", ticker, outcome.get("reason", "unknown")
                )
        elif outcome:
            removed += 1

    for addition in additions:
        ticker = addition["ticker"]
        sector = addition.get("sector", SECTOR_MAP.get(ticker, "Other"))
        if await add_swing_stock(ticker, sector):
            added += 1
        else:
            logger.warning("Addition failed for %s (sector=%s)", ticker, sector)

    logger.info(
        "Persistence: %d/%d additions, %d/%d removals, %d pinned skips",
        added,
        len(additions),
        removed,
        len(removals),
        len(pinned_skips),
    )
    return (removed, added, pinned_skips)


def save_report(result: dict, date_str: str) -> Path:
    """Save weekly update report to JSON."""
    output_dir = Path(__file__).parent.parent.parent / "research" / "weekly-updates"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{date_str}.json"

    with open(output_file, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return output_file
