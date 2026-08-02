#!/usr/bin/env python3
"""
Shared configuration constants for the trading scripts.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Vietnam timezone (UTC+7) — GH Actions runs in UTC, so bare datetime.now()
# returns the wrong date for evening/night runs.
VIETNAM_TZ = timezone(timedelta(hours=7))

# API Configuration — OpenRouter for multi-provider failover
LLM_BASE_URL = "https://openrouter.ai/api/v1"

CHEAP_MODEL = "Qwen/Qwen2.5-7B-Instruct-Turbo"
_tier = os.environ.get("SWINGY_MODEL_TIER", "production")

# Single Python SSOT for the fleet primary model — agents.model.resolvers
# imports LLM_MODEL rather than redefining it, and the
# check_agent_yaml_model_parity hook asserts it matches the YAML majority.
#
# PRECONDITION (load-bearing): the provider-exclusion logic in
# agents/model/wrappers.py assumes a SINGLE-AUTHOR fleet — it deliberately
# never excludes the model-author slug because, when every agent shares one
# author, that would be a fleet-wide kill switch (the 2026-05-15 incident).
# If the fleet is ever split across multiple model authors, revisit
# RetryModel._should_fail_fast and emit_silent_provider_hang_span: an
# author-level exclusion becomes safe and useful again in that world.
LLM_MODEL = CHEAP_MODEL if _tier == "cheap" else "z-ai/glm-5.1"

# Trading parameters moved to trading_config table in DB.
# Use: from shared.trading_config import get_trading_config
MAX_ARTICLE_TOKENS = 40000

# No fallbacks - report errors if database unavailable

# Price multiplier: vnstock returns prices in thousands VND
PRICE_MULTIPLIER = 1000


def get_scan_date() -> str:
    """Return the scan date from SCAN_DATE env var or today's date in Vietnam time."""
    return os.environ.get("SCAN_DATE", datetime.now(VIETNAM_TZ).strftime("%Y-%m-%d"))


def get_yesterday_date() -> str:
    """Return yesterday's date in Vietnam timezone.

    Used as the default end_date for price/technical fetches so callers
    always get completed (closed) bars, never partial intraday bars.
    """
    return (datetime.now(VIETNAM_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")


def get_research_dir(base: Path | None = None) -> Path:
    """Return the research output directory for today's scan date.

    Args:
        base: Base research directory. Defaults to <repo_root>/research.
    """
    if base is None:
        base = Path(__file__).parent.parent.parent / "research"
    return base / get_scan_date()
