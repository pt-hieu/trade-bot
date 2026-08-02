"""
Embedding generation for memory similarity search.

Uses sentence-transformers (all-MiniLM-L6-v2) for local embedding generation.
No API costs - runs entirely on CPU.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Lazy-loaded model (384 dimensions)
_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    """Get or initialize the embedding model.

    Uses all-MiniLM-L6-v2 which produces 384-dimensional embeddings.
    Model is cached after first load (~90MB download on first use).
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model: all-MiniLM-L6-v2")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedding model loaded successfully")
    return _model


def embed_context(context: dict) -> list[float] | None:
    """Embed a trading context for similarity search.

    Args:
        context: Dict with market context fields like:
            - market_regime: RISK_ON, NEUTRAL, RISK_OFF
            - global_macro: CALM, CAUTIOUS, ELEVATED, CRISIS
            - hot_sectors: List of hot sector names
            - cold_sectors: List of cold sector names
            - vix: VIX value
            - trading_mode: NORMAL, LOW_CASH, REALLOCATION

    Returns:
        384-dimensional embedding as list of floats, or None on failure
    """
    try:
        model = get_embedding_model()
    except Exception as e:
        logger.warning("Failed to load embedding model: %s", e)
        return None

    # Format context as natural language for embedding
    text = format_context_for_embedding(context)

    # Generate embedding
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def embed_text(text: str) -> list[float] | None:
    """Embed arbitrary text for similarity search.

    Args:
        text: Any text to embed

    Returns:
        384-dimensional embedding as list of floats, or None on failure
    """
    try:
        model = get_embedding_model()
    except Exception as e:
        logger.warning("Failed to load embedding model: %s", e)
        return None
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def format_context_for_embedding(context: dict) -> str:
    """Format context dict as natural language for embedding.

    Converts structured trading context into a sentence that captures
    the semantic meaning for similarity search.

    Args:
        context: Dict with market context fields

    Returns:
        Natural language description of the context
    """
    parts = []

    # Market regime
    if regime := context.get("market_regime"):
        regime_desc = {
            "RISK_ON": "bullish and risk-seeking",
            "RISK_OFF": "bearish and risk-averse",
            "NEUTRAL": "neutral and mixed",
        }.get(regime, regime)
        parts.append(f"Market regime is {regime_desc}")

    # Global macro
    if macro := context.get("global_macro"):
        macro_desc = {
            "CALM": "calm with low volatility",
            "CAUTIOUS": "cautious with moderate concerns",
            "ELEVATED": "elevated risk with high volatility",
            "CRISIS": "crisis mode with extreme fear",
        }.get(macro, macro)
        parts.append(f"Global macro is {macro_desc}")

    # Hot sectors
    if (hot := context.get("hot_sectors")) and isinstance(hot, list) and hot:
        parts.append(f"Hot sectors showing strength: {', '.join(hot)}")

    # Cold sectors
    if (cold := context.get("cold_sectors")) and isinstance(cold, list) and cold:
        parts.append(f"Cold sectors showing weakness: {', '.join(cold)}")

    # VIX level
    if vix := context.get("vix"):
        try:
            vix_val = float(vix)
            if vix_val > 30:
                level = "extreme fear"
            elif vix_val > 25:
                level = "high fear"
            elif vix_val > 18:
                level = "moderate caution"
            else:
                level = "low complacency"
            parts.append(f"VIX at {vix_val:.1f} indicating {level}")
        except (ValueError, TypeError):
            pass

    # Trading mode
    if mode := context.get("trading_mode"):
        mode_desc = {
            "NORMAL": "normal with available capital",
            "LOW_CASH": "low cash requiring exits",
            "REALLOCATION": "reallocation mode",
        }.get(mode, mode)
        parts.append(f"Trading mode is {mode_desc}")

    # Pattern description (for pattern embeddings)
    if pattern := context.get("pattern"):
        parts.append(f"Pattern: {pattern}")

    # Fallback if no fields
    if not parts:
        return "Unknown market context"

    return ". ".join(parts) + "."


def format_rule_for_embedding(rule: dict) -> str:
    """Format a trading rule for embedding.

    Args:
        rule: Dict with rule fields like:
            - rule_name: Short name
            - description: Full description
            - action: What to do
            - condition_regime: List of regimes
            - condition_sectors: List of sectors

    Returns:
        Natural language description of the rule
    """
    parts = []

    if name := rule.get("rule_name"):
        parts.append(f"Rule: {name}")

    if desc := rule.get("description"):
        parts.append(desc)

    if action := rule.get("action"):
        parts.append(f"Action: {action}")

    if (regimes := rule.get("condition_regime")) and isinstance(regimes, list) and regimes:
        parts.append(f"Applies in {', '.join(regimes)} regime")

    if (sectors := rule.get("condition_sectors")) and isinstance(sectors, list) and sectors:
        parts.append(f"For sectors: {', '.join(sectors)}")

    return ". ".join(parts) + "." if parts else "Unknown rule"
