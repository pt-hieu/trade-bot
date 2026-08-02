"""
Data module - Price, technical, and article fetching.

Usage:
    from data.prices import fetch_prices
    from data.technicals import fetch_technicals
    from data.articles import search_articles, articles_exist_in_db
    from data.sector_rotation import detect_rotation, run_sector_rotation
"""

from .articles import (
    articles_exist_in_db,
    search_articles,
)
from .prices import fetch_prices
from .sector_rotation import (
    CYCLICAL_SECTORS,
    DEFENSIVE_SECTORS,
    GROWTH_SECTORS,
    SECTOR_MAP,
    detect_rotation,
    run_sector_rotation,
)
from .technicals import fetch_technicals

__all__ = [
    # Prices
    "fetch_prices",
    # Technicals
    "fetch_technicals",
    # Articles
    "search_articles",
    "articles_exist_in_db",
    # Sector Rotation
    "detect_rotation",
    "run_sector_rotation",
    "SECTOR_MAP",
    "DEFENSIVE_SECTORS",
    "GROWTH_SECTORS",
    "CYCLICAL_SECTORS",
]
