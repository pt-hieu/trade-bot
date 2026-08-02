"""Canonical unit conversion utilities.

Convention (rule 18 in CLAUDE.md):
- Prices: VND integers (e.g., 30500)
- Display %: Whole number (e.g., 2.15 means +2.15%)
- Rates: Decimal 0-1 (e.g., 0.65 means 65%)
- Ratios: As-is (e.g., pe=12.5)

vnstock API returns prices in THOUSANDS VND and financial ratios as DECIMAL.
These functions convert at the normalization boundary.
"""


def thousands_to_vnd(v: float) -> int:
    """Convert vnstock API price (thousands VND) to canonical VND integer."""
    return int(round(v * 1000))


def vnd_to_thousands(v: int) -> float:
    """Convert VND integer to thousands for display (e.g., '30.5k')."""
    return v / 1000


def rate_to_pct(v: float) -> float:
    """Convert decimal rate (0-1) to whole-number percentage for display."""
    return round(v * 100, 2)
