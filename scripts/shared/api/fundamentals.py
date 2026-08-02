"""Financial statements and ratios — reads directly from vnstock API.

Replaces shared.neon.fundamentals for read operations.
Same function signatures as neon module — consumers change only their import path.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

from ..lint_markers import allow_single_ticker_fetcher
from ..vnstock_client import fetch_financial_ratios as _fetch_ratios
from ..vnstock_client import fetch_financial_statements as _fetch_statements

# ── Field name mapping: vnstock API → normalized dict keys ───────────────────
# Mirrors the KNOWN mapping in shared/neon/fundamentals.py (upsert side).
_KNOWN: dict[str, str] = {
    "ROE (%)": "roe",
    "ROA (%)": "roa",
    "After-tax Profit Margin (%)": "net_margin",
    "Gross Margin (%)": "gross_margin",
    "EBIT Margin (%)": "operating_margin",
    "EPS basic (VND)": "eps",
    "P/E": "pe",
    "P/B": "pb",
    "Debt to Equity": "debt_to_equity",
    "Current Ratio": "current_ratio",
    # snake_case API variants
    "roe": "roe",
    "roa": "roa",
    "pe": "pe",
    "pb": "pb",
    "net_margin": "net_margin",
    "gross_margin": "gross_margin",
    "operating_margin": "operating_margin",
    "debt_to_equity": "debt_to_equity",
    "current_ratio": "current_ratio",
}

_KNOWN_TARGETS = set(_KNOWN.values())

# Fields that are structural metadata, not ratio values
_META_FIELDS = frozenset(
    [
        "period",
        "yearReport",
        "year_report",
        "lengthReport",
        "length_report",
        "quarter",
        "fiscalDate",
        "fiscal_date",
        "year",
    ]
)


def _to_numeric(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _extract_period(record: dict, period_type: str = "quarter") -> str | None:
    """Extract report period string from a financial record.

    Handles vnstock 'period' column (e.g. '2025-Q3') and legacy fields.
    Identical logic to scripts/data/fundamentals.py:_extract_period().
    """
    period_val = record.get("period")
    if period_val and str(period_val) not in ("quarter", "year", "0"):
        return str(period_val)

    year = None
    for field in ["yearReport", "year_report", "year", "fiscalDate", "fiscal_date"]:
        if field in record and record[field] is not None:
            year = str(record[field])[:4]
            break
    if not year:
        return None

    if period_type == "quarter":
        for field in ["lengthReport", "length_report", "quarter"]:
            if field in record and record[field] is not None:
                q = str(record[field]).replace("Q", "").strip()
                try:
                    return f"{year}-Q{int(q)}"
                except ValueError:
                    pass
        return f"{year}-Q?"

    return year


def _normalize_ratio_record(record: dict, period_type: str = "quarter") -> dict | None:
    """Normalize a single ratio record from API format to standard dict shape.

    Returns {report_period, roe, roa, pe, pb, net_margin, ...} or None if no period.
    """
    report_period = _extract_period(record, period_type)
    if not report_period:
        return None

    normalized: dict = {
        "report_period": report_period,
        "period_type": period_type,
        "roe": None,
        "roa": None,
        "net_margin": None,
        "gross_margin": None,
        "operating_margin": None,
        "eps": None,
        "pe": None,
        "pb": None,
        "debt_to_equity": None,
        "current_ratio": None,
        "extra": {},
    }

    for k, v in record.items():
        if k in _KNOWN:
            normalized[_KNOWN[k]] = _to_numeric(v)
        elif k not in _META_FIELDS and k not in _KNOWN_TARGETS:
            normalized["extra"][k] = v

    # Normalize percentage fields from API decimal to whole-number %
    # vnstock API returns all ratios as decimal (roe=0.2827 for 28.27%)
    _PCT_FIELDS = {"roe", "roa", "net_margin", "gross_margin", "operating_margin"}
    for field in _PCT_FIELDS:
        if normalized[field] is not None:
            normalized[field] = round(normalized[field] * 100, 2)

    return normalized


# ── Public functions (same interface as shared.neon.fundamentals) ─────────────


_vnstock_semaphore = asyncio.Semaphore(3)


async def get_financial_ratios(ticker: str, periods: int = 4) -> list[dict]:
    """Get last N periods of ratios for a ticker (from vnstock API).

    Returns list of {report_period, roe, roa, pe, pb, net_margin, ...} dicts.
    Same shape as shared.neon.fundamentals.get_financial_ratios().
    """
    async with _vnstock_semaphore:
        try:
            resp = await _fetch_ratios(symbol=ticker.upper(), period="quarter", limit=periods)
            records = resp.get("data", [])
            result = []
            for record in records:
                normalized = _normalize_ratio_record(record, "quarter")
                if normalized:
                    result.append(normalized)
            return result[:periods]
        except Exception as e:
            logger.warning("get_financial_ratios(%s) failed: %s", ticker, e)
            return []


async def get_financial_ratios_batch(tickers: list[str]) -> dict[str, dict]:
    """Get latest ratios for multiple tickers (from vnstock API), fetched concurrently.

    Returns {ticker: latest_ratio_dict}.
    Same shape as shared.neon.fundamentals.get_financial_ratios_batch().
    """

    async def _fetch_one(ticker: str) -> tuple[str, dict]:
        ratios = await get_financial_ratios(ticker, periods=1)
        return ticker.upper(), ratios[0] if ratios else {}

    results = await asyncio.gather(*[_fetch_one(t) for t in tickers], return_exceptions=True)
    batch = {}
    for result in results:
        if isinstance(result, BaseException):
            continue
        ticker, data = result
        batch[ticker] = data
    return batch


@allow_single_ticker_fetcher  # vnstock statements API is single-symbol; no batch HTTP endpoint
async def get_latest_financial_statement(ticker: str, statement_type: str) -> dict | None:
    """Get latest financial statement for a ticker (from vnstock API).

    Returns {ticker, statement_type, report_period, data} or None.
    Same shape as shared.neon.fundamentals.get_latest_financial_statement().
    """
    try:
        resp = await _fetch_statements(
            symbol=ticker.upper(),
            statement_type=statement_type,
            period="quarter",
            limit=1,
        )
        records = resp.get("data", [])
        if not records:
            return None
        record = records[0]
        report_period = _extract_period(record, "quarter")
        return {
            "ticker": ticker.upper(),
            "statement_type": statement_type,
            "report_period": report_period or "unknown",
            "period_type": "quarter",
            "data": record,
        }
    except Exception as e:
        logger.warning(
            "get_latest_financial_statement(%s, %s) failed: %s", ticker, statement_type, e
        )
        return None


@allow_single_ticker_fetcher  # vnstock statements API is single-symbol; no batch HTTP endpoint
async def get_financial_statements(
    ticker: str,
    statement_type: str,
    periods: int = 4,
) -> list[dict]:
    """Get last N periods of a financial statement for a ticker (from vnstock API).

    Returns list of {report_period, data} dicts.
    Same shape as shared.neon.fundamentals.get_financial_statements().
    """
    try:
        resp = await _fetch_statements(
            symbol=ticker.upper(),
            statement_type=statement_type,
            period="quarter",
            limit=periods,
        )
        records = resp.get("data", [])
        result = []
        for record in records:
            report_period = _extract_period(record, "quarter")
            result.append({"report_period": report_period or "unknown", "data": record})
        return result[:periods]
    except Exception as e:
        logger.warning("get_financial_statements(%s, %s) failed: %s", ticker, statement_type, e)
        return []
