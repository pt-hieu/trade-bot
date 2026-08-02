"""SWI-125 Surface 1: structural completeness — find_nearest_levels keys ⊆ _PRICE_LEVEL_KEYS.

Catches the producer/consumer drift class where levels.py adds a new conditional
key but analysis._PRICE_LEVEL_KEYS allowlist is hand-maintained. The May 12
incident: nearest_swing_low / nearest_swing_target were emitted in thousand-VND
units because they were absent from the allowlist after SWI-289 added them to
find_nearest_levels.
"""

from __future__ import annotations

from data.technicals.analysis import _PRICE_LEVEL_KEYS
from data.technicals.levels import find_nearest_levels

# Non-price scalar keys emitted by find_nearest_levels that legitimately do NOT
# need ×1000 normalization. find_nearest_levels currently emits zero such keys
# (all returned values are price levels), but the test tolerates future additions
# (counts, ratios, booleans, strings) — only assert that any *price-level* key
# returned by find_nearest_levels is covered by the normalizer allowlist.
_NON_PRICE_SCALAR_KEYS: frozenset[str] = frozenset()


def _assert_keys_subset(levels: dict, price: float) -> None:
    price_keys = set(levels.keys()) - _NON_PRICE_SCALAR_KEYS
    missing = price_keys - set(_PRICE_LEVEL_KEYS)
    assert not missing, (
        f"find_nearest_levels emitted price-level keys {missing} that are NOT in "
        f"_PRICE_LEVEL_KEYS — these would leak in thousand-VND units. "
        f"Add to scripts/data/technicals/analysis.py::_PRICE_LEVEL_KEYS."
    )
    # Sanity: each level value is below 1000 (thousand-VND scale, pre-normalize).
    for key in price_keys:
        assert levels[key] < 1000, (
            f"Test fixture price-scale invariant broken: {key}={levels[key]} >= 1000"
        )


def test_find_nearest_levels_uptrend_keys_subset_of_normalizer() -> None:
    # Uptrend: price between MAs and a higher swing high; lower swing_low present.
    levels = find_nearest_levels(
        price=50.0,
        ma20=48.0,
        ma50=46.0,
        swing_high=55.0,
        swing_low=45.0,
        range_high=54.0,
        range_low=46.5,
    )
    _assert_keys_subset(levels, price=50.0)
    assert "nearest_swing_target" in levels
    assert "nearest_swing_low" in levels


def test_find_nearest_levels_downtrend_keys_subset_of_normalizer() -> None:
    levels = find_nearest_levels(
        price=50.0,
        ma20=52.0,
        ma50=54.0,
        swing_high=60.0,
        swing_low=44.0,
        range_high=58.0,
        range_low=46.0,
    )
    _assert_keys_subset(levels, price=50.0)
    assert "nearest_swing_target" in levels
    assert "nearest_swing_low" in levels


def test_find_nearest_levels_sideways_keys_subset_of_normalizer() -> None:
    levels = find_nearest_levels(
        price=50.0,
        ma20=50.0,
        ma50=50.0,
        swing_high=53.0,
        swing_low=47.0,
        range_high=52.0,
        range_low=48.0,
    )
    _assert_keys_subset(levels, price=50.0)


def test_swing_keys_listed_in_price_normalizer() -> None:
    """Explicit regression guard for the SWI-125 root cause."""
    assert "nearest_swing_low" in _PRICE_LEVEL_KEYS
    assert "nearest_swing_target" in _PRICE_LEVEL_KEYS
