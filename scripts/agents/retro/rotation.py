"""
Sector Rotation Evaluator.

Compares morning rotation predictions (hot/cold sectors) against
actual sector performance at EOD.
"""

from datetime import date

from data.sector_rotation import SECTOR_MAP


def calculate_sector_returns(eod_prices: dict) -> dict:
    """
    Calculate average daily return per sector from EOD prices.

    Args:
        eod_prices: Dict of ticker -> {open, high, low, close, ...}

    Returns:
        Dict of sector -> average daily return (%)
    """
    sector_returns = {}

    for ticker, prices in eod_prices.items():
        sector = SECTOR_MAP.get(ticker)
        if not sector:
            continue

        open_price = prices.get("open")
        close_price = prices.get("close")

        if not open_price or not close_price or open_price == 0:
            continue

        daily_return = (close_price - open_price) / open_price * 100

        if sector not in sector_returns:
            sector_returns[sector] = []
        sector_returns[sector].append(daily_return)

    # Calculate average return per sector
    return {
        sector: round(sum(returns) / len(returns), 2)
        for sector, returns in sector_returns.items()
        if returns
    }


def evaluate_rotation(rotation: dict, sector_returns: dict) -> dict:
    """
    Compare hot/cold predictions vs actual sector performance.

    Accuracy criteria:
    - Hot sector is accurate if it outperformed market average
    - Cold sector is accurate if it underperformed market average

    Args:
        rotation: Dict with hot_sectors, cold_sectors lists
        sector_returns: Dict of sector -> daily return %

    Returns:
        Dict with evaluation metrics
    """
    hot_sectors = rotation.get("hot_sectors", [])
    cold_sectors = rotation.get("cold_sectors", [])
    market_regime = rotation.get("market_regime", "NEUTRAL")

    # Get returns for each predicted sector
    hot_returns = [sector_returns.get(s, 0) for s in hot_sectors if s in sector_returns]
    cold_returns = [sector_returns.get(s, 0) for s in cold_sectors if s in sector_returns]
    all_returns = list(sector_returns.values())

    # Calculate averages
    avg_hot = sum(hot_returns) / len(hot_returns) if hot_returns else 0
    avg_cold = sum(cold_returns) / len(cold_returns) if cold_returns else 0
    market_avg = sum(all_returns) / len(all_returns) if all_returns else 0

    # Calculate hit rates
    # Hot is accurate if outperformed market avg
    hot_accurate = sum(1 for r in hot_returns if r > market_avg)
    hot_hit_rate = hot_accurate / len(hot_returns) if hot_returns else 0

    # Cold is accurate if underperformed market avg
    cold_accurate = sum(1 for r in cold_returns if r < market_avg)
    cold_hit_rate = cold_accurate / len(cold_returns) if cold_returns else 0

    return {
        "hot_sectors": hot_sectors,
        "cold_sectors": cold_sectors,
        "market_regime": market_regime,
        "sector_returns": sector_returns,
        "hot_avg_return": round(avg_hot, 2),
        "cold_avg_return": round(avg_cold, 2),
        "market_avg_return": round(market_avg, 2),
        "hot_vs_market": round(avg_hot - market_avg, 2),
        "cold_vs_market": round(avg_cold - market_avg, 2),
        "hot_hit_rate": round(hot_hit_rate, 2),
        "cold_hit_rate": round(cold_hit_rate, 2),
        "overall_accuracy": round((hot_hit_rate + cold_hit_rate) / 2, 2),
        "rotation_effective": avg_hot > avg_cold,
    }


async def evaluate_rotation_for_day(scan_date: date, eod_prices: dict | None = None) -> dict | None:
    """
    Load sector rotation prediction from DB and evaluate against EOD prices.

    Args:
        scan_date: Date to evaluate
        eod_prices: Pre-loaded EOD prices (required)

    Returns:
        Evaluation dict, or None if data missing
    """
    from shared.neon import get_sector_rotation

    rotation = await get_sector_rotation(scan_date)
    if "error" in rotation:
        print(f"  No sector rotation data for {scan_date}")
        return None

    if eod_prices is None:
        print("  No EOD prices provided")
        return None

    # Calculate sector returns
    sector_returns = calculate_sector_returns(eod_prices)

    if not sector_returns:
        print("  No sector returns calculated (missing price data)")
        return None

    # Evaluate rotation
    evaluation = evaluate_rotation(rotation, sector_returns)

    return evaluation
