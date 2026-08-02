"""Async functions for use in PydanticAI agents (with prose-wrapped returns)."""

from __future__ import annotations

from datetime import date

from .formatters import (
    _format_macro_history_prose,
    _format_macro_prose,
    _format_regime_history_prose,
    _format_regime_prose,
    _format_rotation_prose,
)


async def get_market_regime_async(scan_date: date | None = None) -> dict:
    """Get market regime - async version for PydanticAI agents."""
    from shared.neon import get_market_regime as neon_get_market_regime

    if scan_date is None:
        scan_date = date.today()

    try:
        result = await neon_get_market_regime(scan_date)
        result["prose"] = _format_regime_prose(result)
        return result
    except Exception as e:
        return {
            "error": f"Failed to get market regime: {e}",
            "prose": f"Market Regime: Failed to fetch - {e}",
        }


async def get_sector_rotation_async(scan_date: date | None = None) -> dict:
    """Get sector rotation - async version for PydanticAI agents."""
    from shared.neon import get_sector_rotation as neon_get_sector_rotation

    if scan_date is None:
        scan_date = date.today()

    try:
        result = await neon_get_sector_rotation(scan_date)
        result["prose"] = _format_rotation_prose(result)
        return result
    except Exception as e:
        return {
            "error": f"Failed to get sector rotation: {e}",
            "prose": f"Sector Rotation: Failed to fetch - {e}",
        }


async def get_macro_metrics_async(scan_date: date | None = None) -> dict:
    """Get global macro metrics - async version for PydanticAI agents."""
    from shared.neon import get_macro_metrics as neon_get_macro_metrics

    if scan_date is None:
        scan_date = date.today()

    try:
        result = await neon_get_macro_metrics(scan_date)
        result["prose"] = _format_macro_prose(result)
        return result
    except Exception as e:
        return {
            "error": f"Failed to get macro metrics: {e}",
            "prose": f"Global Macro: Failed to fetch - {e}",
        }


async def get_regime_history_async(days: int = 5) -> dict:
    """Get regime history - async version for PydanticAI agents."""
    from shared.neon import get_regime_history as neon_get_regime_history

    try:
        history = await neon_get_regime_history(days)
        return {"history": history, "prose": _format_regime_history_prose(history)}
    except Exception as e:
        return {
            "error": f"Failed to get regime history: {e}",
            "history": [],
            "prose": f"Regime History: Failed to fetch - {e}",
        }


async def get_macro_history_async(days: int = 5) -> dict:
    """Get macro regime history - async version for PydanticAI agents."""
    from shared.neon import get_macro_history as neon_get_macro_history

    try:
        history = await neon_get_macro_history(days)
        return {"history": history, "prose": _format_macro_history_prose(history)}
    except Exception as e:
        return {
            "error": f"Failed to get macro history: {e}",
            "history": [],
            "prose": f"Macro History: Failed to fetch - {e}",
        }


async def tool_get_regime(scan_date: date | None = None) -> str:
    """Get market regime classification — returns prose for LLM agents."""
    result = await get_market_regime_async(scan_date)
    return result.get("prose", str(result))


async def tool_get_rotation(scan_date: date | None = None) -> str:
    """Get sector rotation analysis — returns prose for LLM agents."""
    result = await get_sector_rotation_async(scan_date)
    return result.get("prose", str(result))


async def tool_get_macro(scan_date: date | None = None) -> str:
    """Get global macro metrics — returns prose for LLM agents."""
    result = await get_macro_metrics_async(scan_date)
    return result.get("prose", str(result))


async def tool_get_regime_history(days: int = 5) -> str:
    """Get market regime history — returns prose for LLM agents."""
    result = await get_regime_history_async(days)
    return result.get("prose", str(result))


async def tool_get_macro_history(days: int = 5) -> str:
    """Get macro regime history — returns prose for LLM agents."""
    result = await get_macro_history_async(days)
    return result.get("prose", str(result))
