"""
News keyword filter for catalyst/event discovery.

Loads today's articles from DB and returns those matching
catalyst or capital event keywords.
"""

import re
from datetime import date

from shared.neon.articles import list_articles_range

CATALYST_KEYWORDS = [
    "giải ngân đầu tư công",
    "luật đất đai",
    "nâng hạng",
    "ftse",
    "msci",
    "lãi suất",
    "fdi",
    "nợ xấu",
    "infrastructure",
    "banking regulation",
    "real estate law",
    "public investment",
    "npl",
    "chính sách",
    "quy định",
    "nghị định",
    "thông tư",
    "đầu tư công",
    # Macro / monetary
    "lạm phát",
    "gdp",
    "tỷ giá",
    "thuế",
    "thuế quan",
    "tariff",
    "fed",
    "forex",
    "ngân hàng trung ương",
    "sbv",
    "phá sản",
    "tái cơ cấu",
    # Geopolitical / oil crisis
    "chiến tranh",
    "xung đột",
    "địa chính trị",
    "eo biển hormuz",
    "hormuz",
    "strait of hormuz",
    "dầu thô",
    "giá dầu",
    "oil price",
    "crude oil",
    "trung đông",
    "middle east",
    "iran",
    "opec",
    "cấm vận",
    "sanctions",
]

CAPITAL_EVENT_KEYWORDS = [
    "tăng vốn",
    "phát hành",
    "chia cổ tức",
    "sáp nhập",
    "mua lại",
    "thâu tóm",
    "mua cổ phiếu quỹ",
    "niêm yết",
    "niêm yết bổ sung",
    "ipo",
    "capital increase",
    "rights issue",
    "dividend",
    "merger",
    "acquisition",
    "buyback",
    "stock split",
    "phát hành cổ phiếu",
    "phát hành riêng lẻ",
    "tách cổ phiếu",
    "cổ tức",
    "trái phiếu",
    "huy động vốn",
    "cổ phần hóa",
    "thoái vốn",
    "chuyển nhượng",
    "esop",
    "warrant",
    "quyền mua",
]

ALL_KEYWORDS = CATALYST_KEYWORDS + CAPITAL_EVENT_KEYWORDS
_KEYWORD_PATTERNS = [
    (kw, re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)) for kw in ALL_KEYWORDS
]


async def filter_articles(scan_date: date) -> list[dict]:
    """Return today's articles matching any catalyst/event keyword.

    Args:
        scan_date: Date to filter articles for

    Returns:
        List of dicts: {id, title, summary, source, matched_keywords}
    """
    articles = await list_articles_range(scan_date, scan_date)
    results = []

    for article in articles:
        text = f"{article.get('title', '')} {article.get('summary', '')}"
        matched = [kw for kw, pattern in _KEYWORD_PATTERNS if pattern.search(text)]
        if matched:
            results.append(
                {
                    "id": article["id"],
                    "title": article.get("title", ""),
                    "summary": article.get("summary", ""),
                    "source": article.get("source", ""),
                    "matched_keywords": matched,
                }
            )

    return results
