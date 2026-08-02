"""Sector groupings + ticker universe used by the watchlist ensemble."""

from __future__ import annotations

from ..watchlist_update import SECTOR_MAP, VN30_TICKERS

# Single source of truth for which sector labels belong to each group
GROUP_SECTOR_LABELS: dict[str, list[str]] = {
    "banking": ["Banking"],
    "securities": ["Securities"],
    "property_infra": ["Real Estate", "Infrastructure"],
    "consumer_soe": ["Consumer", "State-Owned", "Technology"],
}

# Only include tickers tracked in VN30_TICKERS candidate universe
_VN30_SET = set(VN30_TICKERS)
SECTOR_GROUPS: dict[str, list[str]] = {
    group: [t for t, s in SECTOR_MAP.items() if s in labels and t in _VN30_SET]
    for group, labels in GROUP_SECTOR_LABELS.items()
}

# Stable candidate list: VN30 tickers deduplicated in original order
_ALL_TICKERS: list[str] = list(dict.fromkeys(VN30_TICKERS))
