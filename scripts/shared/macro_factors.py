"""Canonical macro factor taxonomy for deterministic keyword extraction.

Maps macro themes to standardized factor keys, with Vietnamese + English keywords
for text matching. Used by data/articles_intl/filtering.py to build the intl macro allowlist.
"""

# factor_key → metadata (label for display, keywords for text matching)
MACRO_FACTORS: dict[str, dict] = {
    # Commodities
    "oil_price": {
        "label": "Oil Price",
        "keywords": ["dầu thô", "dầu mỏ", "crude oil", "brent", "wti", "xăng dầu", "opec"],
    },
    "steel_price": {
        "label": "Steel Price",
        "keywords": ["giá thép", "steel price", "thép xây dựng", "hrc", "crc"],
    },
    "iron_ore": {
        "label": "Iron Ore",
        "keywords": ["quặng sắt", "iron ore"],
    },
    "copper": {
        "label": "Copper",
        "keywords": ["giá đồng", "copper price"],
    },
    "rubber": {
        "label": "Rubber",
        "keywords": ["cao su", "rubber price", "giá cao su"],
    },
    # Monetary / credit
    "interest_rate": {
        "label": "Interest Rate",
        "keywords": [
            "lãi suất",
            "lai suat",
            "interest rate",
            "sbv",
            "ngân hàng nhà nước",
            "chính sách tiền tệ",
            "monetary policy",
        ],
    },
    "credit_growth": {
        "label": "Credit Growth",
        "keywords": ["tín dụng", "tin dung", "credit growth", "tăng trưởng tín dụng"],
    },
    # FX
    "usd_vnd": {
        "label": "USD/VND",
        "keywords": ["tỷ giá", "ty gia", "usd/vnd", "usd-vnd", "exchange rate"],
    },
    "dxy": {
        "label": "Dollar Index",
        "keywords": ["dxy", "dollar index", "chỉ số đô la"],
    },
    # Investment flows
    "fdi": {
        "label": "FDI Inflows",
        "keywords": ["fdi", "đầu tư nước ngoài", "dau tu nuoc ngoai", "foreign direct investment"],
    },
    "public_investment": {
        "label": "Public Investment",
        "keywords": [
            "đầu tư công",
            "dau tu cong",
            "public investment",
            "giải ngân đầu tư công",
            "giai ngan",
        ],
    },
    # Trade partners
    "china_demand": {
        "label": "China Demand",
        "keywords": [
            "trung quốc",
            "trung quoc",
            "trung hoa",
            "china demand",
            "china trade",
            "china economy",
        ],
    },
    "us_demand": {
        "label": "US Demand",
        "keywords": [
            "hoa kỳ",
            "hoa ky",
            "nước mỹ",
            "kinh tế mỹ",
            "thị trường mỹ",
            "thương mại mỹ",
            "united states",
            "us market",
            "american",
        ],
    },
    "japan_demand": {
        "label": "Japan Demand",
        "keywords": ["nhật bản", "nhat ban", "japan"],
    },
    # Regulatory
    "land_law": {
        "label": "Land Law",
        "keywords": ["luật đất đai", "luat dat dai", "land law", "bất động sản", "bat dong san"],
    },
    "banking_regulation": {
        "label": "Banking Regulation",
        "keywords": [
            "thông tư",
            "thong tu",
            "quy định ngân hàng",
            "banking regulation",
        ],
    },
    "npl_rules": {
        "label": "NPL Rules",
        "keywords": ["nợ xấu", "no xau", "npl", "bad debt", "xử lý nợ"],
    },
    "securities_regulation": {
        "label": "Securities Regulation",
        "keywords": [
            "nâng hạng",
            "nang hang",
            "ftse",
            "msci",
            "thị trường chứng khoán",
            "securities regulation",
        ],
    },
    # Technology disruption
    "ai_disruption": {
        "label": "AI Disruption",
        "keywords": [
            "ai replace",
            "ai thay thế",
            "ai coding",
            "ai agent",
            "github copilot",
            "copilot",
            "ai outsourcing",
            "automation replace",
            "tự động hóa thay thế",
            "ai layoff",
            "ai cắt giảm",
            "software automation",
            "ai threat",
        ],
    },
    # Sentiment / global risk
    "vix": {
        "label": "VIX",
        "keywords": ["vix", "volatility index"],
    },
    "global_risk": {
        "label": "Global Risk",
        "keywords": [
            "trade war",
            "chiến tranh thương mại",
            "tariff",
            "thuế quan",
            "geopolitical",
            "địa chính trị",
            "trung đông",
            "middle east",
        ],
    },
}

# Reverse index: keyword (lowered) → factor key for O(1) lookup
KEYWORD_TO_FACTOR: dict[str, str] = {}
for _factor_key, _meta in MACRO_FACTORS.items():
    for _kw in _meta["keywords"]:
        _kw_lower = _kw.lower()
        assert _kw_lower not in KEYWORD_TO_FACTOR, (
            f"Duplicate keyword '{_kw}': already mapped to '{KEYWORD_TO_FACTOR[_kw_lower]}', "
            f"now '{_factor_key}'"
        )
        KEYWORD_TO_FACTOR[_kw_lower] = _factor_key
