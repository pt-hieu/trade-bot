"""
Memory system for trading agents.

Provides episodic memory (similar past days) and semantic memory (trading rules).
"""

from .embeddings import embed_context, format_context_for_embedding

__all__ = [
    "embed_context",
    "format_context_for_embedding",
]
