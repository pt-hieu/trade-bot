"""Shared utilities for macro data extraction."""

# Candidate column names for the indicator name field across vnstock_data versions.
_NAME_COLUMN_CANDIDATES = ("name", "indicator", "chỉ_tiêu")

# SBV central rate identifier substring (case-insensitive).
_CENTRAL_RATE_MARKER = "trung t"

# Valid USD/VND range for sanity checking raw values.
_USD_VND_MIN = 20000
_USD_VND_MAX = 30000


def extract_sbv_central_rate(data_rows: list[dict]) -> float | None:
    """Extract the most recent SBV central rate from exchange rate data rows.

    Scans rows newest-first for "Tỷ giá trung tâm" (central rate) and returns
    the first valid value in the 20,000-30,000 VND range.

    Used by both the live pipeline (macro.py) and the backfill script to ensure
    consistent extraction logic.
    """
    for row in reversed(data_rows):
        name = ""
        for name_key in _NAME_COLUMN_CANDIDATES:
            if name_key in row:
                name = str(row[name_key]).lower()
                break
        if _CENTRAL_RATE_MARKER not in name:
            continue
        for val in row.values():
            if isinstance(val, (int, float)) and _USD_VND_MIN < val < _USD_VND_MAX:
                return float(val)
    return None
