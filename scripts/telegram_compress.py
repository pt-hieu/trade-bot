"""Telegram-specific compression for morning brief sections.

Deterministic post-processing — no LLM, no async.
Filters SKIP THESE to remove held stocks for phone readability.
"""

import re

# Words that match [A-Z]{2,5} but are NOT stock tickers
_NON_TICKER_WORDS = frozenset(
    {
        "EXIT",
        "TRIM",
        "HOLD",
        "ADD",
        "BUY",
        "SELL",
        "SKIP",
        "WAIT",
        "WATCH",
        "MY",
        "THE",
        "AND",
        "FOR",
        "RSI",
        "ROE",
        "ROA",
        "EPS",
        "ATR",
        "VND",
        "VIX",
        "DXY",
        "MISS",
        "RISK",
        "PE",
        "PL",
        "MACD",
        "CASA",
        "NIM",
        "NPL",
        "SOE",
        "IT",
        "USD",
    }
)

_HOLDINGS_ACTIONS_RE = re.compile(r"^([A-Z]{2,5})\s*[—\-]+\s*(HOLD|EXIT|TRIM|ADD)\b")


def extract_holdings_tickers(holdings_content: str) -> set[str]:
    """Extract ticker symbols from MY HOLDINGS section content."""
    tickers: set[str] = set()
    for line in holdings_content.splitlines():
        match = _HOLDINGS_ACTIONS_RE.match(line.strip())
        if match:
            tickers.add(match.group(1))
    return tickers


def _extract_tickers_from_header(line: str) -> set[str]:
    """Extract likely stock tickers from a SKIP block header line.

    Filters out common financial abbreviations that match [A-Z]{2,5}.
    """
    candidates = set(re.findall(r"\b([A-Z]{2,5})\b", line))
    return candidates - _NON_TICKER_WORDS


def filter_skip_holdings(skip_content: str, holdings_tickers: set[str]) -> str:
    """Remove held stock entries from SKIP THESE content.

    Entries are multi-line blocks starting with ticker name(s).
    """
    if not holdings_tickers or not skip_content:
        return skip_content

    filtered_lines: list[str] = []
    skip_block = False

    for line in skip_content.splitlines():
        stripped = line.strip()
        if not stripped:
            skip_block = False
            if filtered_lines and filtered_lines[-1] != "":
                filtered_lines.append("")
            continue

        if not line.startswith(" ") and not line.startswith("\t"):
            mentioned_tickers = _extract_tickers_from_header(stripped)
            remaining_tickers = mentioned_tickers - holdings_tickers
            if mentioned_tickers and not remaining_tickers:
                skip_block = True
                continue
            skip_block = False

        if not skip_block:
            filtered_lines.append(line)

    return "\n".join(filtered_lines).strip()
