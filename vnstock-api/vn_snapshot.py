"""VN economy snapshot — extract CPI, credit, GDP, FDI from vnstock_data.Macro().

Helpers for /macro/vn-snapshot endpoint. Separated to keep routes_macro.py under 300 lines.
"""

import gc
import logging
import math
from datetime import datetime, timedelta

logger = logging.getLogger("routes_macro")

# ── In-memory cache ────────────────────────────────────────────────────
_vn_snapshot_cache: dict = {"data": None, "fetched_at": None}
_VN_SNAPSHOT_CACHE_TTL_HOURS = 24

# ── Vietnamese indicator name constants ────────────────────────────────
# Hardcoded row values from vnstock_data.Macro() DataFrames.
CPI_HEADLINE = "Chỉ số giá tiêu dùng"
CPI_YOY = "So sánh với cùng kỳ năm trước"
CREDIT_NAME = "Tín dụng"
M2_SUPPLY_NAME = "Cung tiền M2"
GDP_HEADLINE = "Tổng GDP"
FDI_DISBURSED = "Giải ngân"
FDI_REGISTERED = "Đăng ký"

# Candidate column names for the indicator name field across vnstock_data versions
_NAME_COLUMN_CANDIDATES = ("name", "indicator", "chỉ_tiêu")


def fetch_vn_snapshot() -> dict:
    """Build VN economy snapshot with 24h in-memory cache."""
    now = datetime.now()
    if (
        _vn_snapshot_cache["data"]
        and _vn_snapshot_cache["fetched_at"]
        and (now - _vn_snapshot_cache["fetched_at"]).total_seconds()
        < _VN_SNAPSHOT_CACHE_TTL_HOURS * 3600
    ):
        return _vn_snapshot_cache["data"]

    from vnstock_data import Macro

    macro = Macro()
    end_date = now.strftime("%Y-%m")
    start_date = (now - timedelta(days=400)).strftime("%Y-%m")

    result: dict = {"timestamp": now.isoformat()}

    _fetch_cpi(macro, start_date, end_date, result)
    _fetch_credit(macro, start_date, end_date, result)
    _fetch_gdp(macro, start_date, end_date, result)
    _fetch_fdi(macro, start_date, end_date, result)

    _vn_snapshot_cache["data"] = result
    _vn_snapshot_cache["fetched_at"] = now
    return result


# ── Per-indicator fetchers ─────────────────────────────────────────────


def _fetch_cpi(macro, start_date: str, end_date: str, result: dict) -> None:
    try:
        cpi_dataframe = macro.cpi(start=start_date, end=end_date, period="month")
        if cpi_dataframe is not None and not cpi_dataframe.empty:
            _extract_cpi(cpi_dataframe, result)
            del cpi_dataframe
    except Exception as cpi_error:
        logger.warning("CPI fetch failed: %s", cpi_error)
    gc.collect()


def _fetch_credit(macro, start_date: str, end_date: str, result: dict) -> None:
    try:
        money_dataframe = macro.money_supply(start=start_date, end=end_date, period="month")
        if money_dataframe is not None and not money_dataframe.empty:
            _extract_credit(money_dataframe, result)
            del money_dataframe
    except Exception as credit_error:
        logger.warning("Credit/M2 fetch failed: %s", credit_error)
    gc.collect()


def _fetch_gdp(macro, start_date: str, end_date: str, result: dict) -> None:
    try:
        gdp_dataframe = macro.gdp(start=start_date, end=end_date, period="quarter")
        if gdp_dataframe is not None and not gdp_dataframe.empty:
            _extract_gdp(gdp_dataframe, result)
            del gdp_dataframe
    except Exception as gdp_error:
        logger.warning("GDP fetch failed: %s", gdp_error)
    gc.collect()


def _fetch_fdi(macro, start_date: str, end_date: str, result: dict) -> None:
    try:
        fdi_dataframe = macro.fdi(start=start_date, end=end_date, period="month")
        if fdi_dataframe is not None and not fdi_dataframe.empty:
            _extract_fdi(fdi_dataframe, result)
            del fdi_dataframe
    except Exception as fdi_error:
        logger.warning("FDI fetch failed: %s", fdi_error)
    gc.collect()


# ── DataFrame extraction helpers ───────────────────────────────────────


def _find_name_column(dataframe, label: str) -> str | None:
    """Find the indicator-name column in a vnstock_data macro DataFrame."""
    for candidate in _NAME_COLUMN_CANDIDATES:
        if candidate in dataframe.columns:
            return candidate
    logger.warning("%s DataFrame has no name column: %s", label, list(dataframe.columns))
    return None


def _find_value_column(dataframe) -> str | None:
    """Find the numeric value column in a vnstock_data macro DataFrame."""
    for candidate in ("value", "giá_trị", "gia_tri"):
        if candidate in dataframe.columns:
            return candidate
    numeric_columns = dataframe.select_dtypes(include=["number"]).columns.tolist()
    if numeric_columns:
        return numeric_columns[-1]
    return None


def _safe_float(value) -> float | None:
    """Convert to float, returning None for NaN/Inf/None."""
    if value is None:
        return None
    try:
        float_value = float(value)
        if math.isnan(float_value) or math.isinf(float_value):
            return None
        return float_value
    except (ValueError, TypeError):
        return None


def _extract_as_of(dataframe) -> str:
    """Extract as_of date string from DataFrame index."""
    last_index = dataframe.index[-1]
    if hasattr(last_index, "strftime"):
        return last_index.strftime("%Y-%m")
    return str(last_index)


def _extract_cpi(cpi_dataframe, result: dict) -> None:
    """Extract CPI MoM and YoY from CPI DataFrame into result dict."""
    name_column = _find_name_column(cpi_dataframe, "CPI")
    if name_column is None:
        return

    headline_rows = cpi_dataframe[cpi_dataframe[name_column] == CPI_HEADLINE]
    yoy_rows = cpi_dataframe[cpi_dataframe[name_column] == CPI_YOY]

    if not headline_rows.empty:
        value_column = _find_value_column(headline_rows)
        if value_column:
            result["cpi_mom_pct"] = _safe_float(headline_rows.iloc[-1][value_column])
            result["cpi_as_of"] = _extract_as_of(headline_rows)

    if not yoy_rows.empty:
        value_column = _find_value_column(yoy_rows)
        if value_column:
            result["cpi_yoy_pct"] = _safe_float(yoy_rows.iloc[-1][value_column])
            if "cpi_as_of" not in result:
                result["cpi_as_of"] = _extract_as_of(yoy_rows)


def _extract_credit(money_dataframe, result: dict) -> None:
    """Extract credit and M2 supply from money_supply DataFrame."""
    name_column = _find_name_column(money_dataframe, "Money supply")
    if name_column is None:
        return

    credit_rows = money_dataframe[money_dataframe[name_column] == CREDIT_NAME]
    if not credit_rows.empty:
        value_column = _find_value_column(credit_rows)
        if value_column:
            # vnstock returns credit in Tỷ VNĐ (billion VND) — convert to trillion
            raw_credit = _safe_float(credit_rows.iloc[-1][value_column])
            result["credit_trillion_vnd"] = round(raw_credit / 1000, 1) if raw_credit else None
            result["credit_as_of"] = _extract_as_of(credit_rows)

    m2_rows = money_dataframe[money_dataframe[name_column] == M2_SUPPLY_NAME]
    if not m2_rows.empty:
        value_column = _find_value_column(m2_rows)
        if value_column:
            result["m2_trillion_vnd"] = _safe_float(m2_rows.iloc[-1][value_column])
            if "credit_as_of" not in result:
                result["credit_as_of"] = _extract_as_of(m2_rows)


def _extract_gdp(gdp_dataframe, result: dict) -> None:
    """Extract headline GDP growth from GDP DataFrame."""
    name_column = _find_name_column(gdp_dataframe, "GDP")
    if name_column is None:
        return

    gdp_rows = gdp_dataframe[gdp_dataframe[name_column] == GDP_HEADLINE]
    if not gdp_rows.empty:
        value_column = _find_value_column(gdp_rows)
        if value_column:
            result["gdp_growth_pct"] = _safe_float(gdp_rows.iloc[-1][value_column])
            last_index = gdp_rows.index[-1]
            # Index may be datetime or string — handle both
            try:
                from datetime import date as _date

                if hasattr(last_index, "month"):
                    quarter = (last_index.month - 1) // 3 + 1
                    result["gdp_quarter"] = f"Q{quarter}-{last_index.year}"
                else:
                    # Parse string like "2025-09-01"
                    parsed_date = _date.fromisoformat(str(last_index)[:10])
                    quarter = (parsed_date.month - 1) // 3 + 1
                    result["gdp_quarter"] = f"Q{quarter}-{parsed_date.year}"
            except (ValueError, AttributeError):
                result["gdp_quarter"] = str(last_index)


def _extract_fdi(fdi_dataframe, result: dict) -> None:
    """Extract FDI disbursed and registered from FDI DataFrame."""
    name_column = _find_name_column(fdi_dataframe, "FDI")
    if name_column is None:
        return

    disbursed_rows = fdi_dataframe[fdi_dataframe[name_column] == FDI_DISBURSED]
    registered_rows = fdi_dataframe[fdi_dataframe[name_column] == FDI_REGISTERED]

    if not disbursed_rows.empty:
        value_column = _find_value_column(disbursed_rows)
        if value_column:
            result["fdi_disbursed_billion_usd"] = _safe_float(disbursed_rows.iloc[-1][value_column])
            result["fdi_as_of"] = _extract_as_of(disbursed_rows)

    if not registered_rows.empty:
        value_column = _find_value_column(registered_rows)
        if value_column:
            result["fdi_registered_billion_usd"] = _safe_float(
                registered_rows.iloc[-1][value_column]
            )
            if "fdi_as_of" not in result:
                result["fdi_as_of"] = _extract_as_of(registered_rows)
