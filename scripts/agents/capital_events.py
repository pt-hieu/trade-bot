#!/usr/bin/env python3
"""
Capital Events Discovery Agent using PydanticAI.

Discovers capital events (IPOs, rights issues, splits) from scraped news.
Persists to `capital_events` table via shared.neon.catalysts.
"""

import asyncio
import logging
import re
from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent

from shared.agent_config import AgentConfig, build_usage_limits, load_agent_config
from shared.neon.catalysts import (
    get_upcoming_capital_events_db,
    upsert_capital_event,
)
from shared.observability import span
from shared.ticker_extract import TICKER_SENTINEL_REJECTS

from .agent_factory import AgentDeps, create_agent
from .model.wrappers import OUTER_FALLBACK_STACK_WALL_S
from .run_with_total_timeout import run_agent_with_total_timeout

logger = logging.getLogger(__name__)


_VN_TICKER_SHAPE = re.compile(r"^[A-Z0-9]{3,5}$")


def _is_invalid_ticker(raw: str | None) -> bool:
    """SWI-125 Surface 7: reject empty / sentinel / malformed VN tickers."""
    if raw is None:
        return True
    stripped = (raw or "").strip().upper()
    if stripped in TICKER_SENTINEL_REJECTS:
        return True
    return not _VN_TICKER_SHAPE.fullmatch(stripped)


class CapitalEvent(BaseModel):
    """A capital event discovered from news."""

    ticker: Annotated[str, Field(min_length=1)]
    event_type: str  # capital_increase, ipo, stock_split, ma, buyback, dividend
    description: str
    amount: str = ""
    expected_date: str
    dilution_pct: float = 0.0
    impact: str  # POSITIVE, NEGATIVE_SHORT_TERM, NEGATIVE_LONG_TERM, WATCH
    source: str

    @field_validator("ticker", mode="before")
    @classmethod
    def _normalize_ticker(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError(f"ticker must be a string, got {type(value).__name__}")
        if _is_invalid_ticker(value):
            raise ValueError(
                f"Invalid ticker {value!r}: must be a 3-5 char uppercase VN ticker, "
                f"not empty / whitespace / sentinel ({sorted(TICKER_SENTINEL_REJECTS)})"
            )
        return value.strip().upper()


class CapitalEventDiscovery(BaseModel):
    """Complete capital event discovery result."""

    events: list[CapitalEvent]


async def _create_capital_events_agent() -> tuple[
    Agent[AgentDeps, CapitalEventDiscovery], AgentConfig
]:
    """Create a capital events discovery agent with tool_get_current_events."""
    config = await load_agent_config("capital_events")
    # HOOK-ALLOW: no-tickers-scope (capital_events discovers tickers from listings)
    agent = create_agent(config, output_type=CapitalEventDiscovery)

    @agent.tool_plain
    async def tool_get_current_events() -> list[dict]:
        """Get currently tracked capital events from DB."""
        rows = await get_upcoming_capital_events_db()
        return [
            {
                "id": r["event_key"],
                "ticker": r["ticker"],
                "event_type": r["event_type"],
                "expected_date": r["expected_date"],
                "status": r["status"],
            }
            for r in rows
        ]

    return agent, config


async def discover_capital_events_with_agent(
    classified_articles: list[dict],
    scan_date: date | None = None,
) -> dict:
    """Discover capital events from pre-classified article facts.

    Args:
        classified_articles: ArticleClassification dicts (classification in capital_event/both)
            Each has: article_id, classification, extracted_facts, affected_tickers, confidence
        scan_date: Trading date
    """
    if scan_date is None:
        scan_date = date.today()

    agent, config = await _create_capital_events_agent()

    articles_text = []
    for art in classified_articles:
        facts = "\n".join(f"  - {f}" for f in art.get("extracted_facts", []))
        tickers = ", ".join(art.get("affected_tickers", [])) or "none identified"
        articles_text.append(
            f"Article {art['article_id']} [{art.get('confidence', 'MEDIUM')}]:\n"
            f"Facts:\n{facts}\n"
            f"Affected tickers: {tickers}"
        )

    prompt = f"""Discover capital events from pre-classified news facts.

DATE: {scan_date}

PRE-CLASSIFIED ARTICLE FACTS:
{"=" * 60}
{chr(10).join(chr(10).join(["", a, "---"]) for a in articles_text)}

## Your Tasks

1. Get current tracked events via tool_get_current_events()
2. For each article fact set above, identify new capital events:
   - Capital increases, rights issues, private placements
   - IPOs, stock splits, M&A, buybacks, dividends

Avoid duplicates - check against current tracked events.
Only include events with clear timing."""

    with span("capital_event_discovery", scan_date=str(scan_date)):
        for attempt in range(2):
            # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
            try:
                result = await run_agent_with_total_timeout(
                    agent,
                    prompt,
                    agent_name="capital_events",
                    deps=AgentDeps(scan_date=scan_date, agent_key="capital_events"),
                    total_timeout_s=float(OUTER_FALLBACK_STACK_WALL_S),
                    usage_limits=build_usage_limits(config),
                )
            except Exception as error:
                if attempt == 0:
                    logger.warning(
                        "Capital events discovery failed (attempt 1): %s — retrying in 5s",
                        error,
                    )
                    await asyncio.sleep(5)
                    continue
                logger.warning(
                    "Capital events discovery failed after 2 attempts: %s — returning empty",
                    error,
                )
                return {"events": []}

            discoveries = {"events": [e.model_dump() for e in result.output.events]}
            await _persist_discoveries(discoveries, scan_date)
            return discoveries

        return {"events": []}  # unreachable


async def _persist_discoveries(discoveries: dict, scan_date: date | None = None) -> None:
    """Write discovery results to capital_events DB table.

    The Pydantic ``CapitalEvent`` validator rejects empty/sentinel tickers
    upstream, but ``discoveries`` is dict-shaped (``model_dump`` output) by
    the time it reaches here. The same guard runs once more so legacy
    callers or hand-built dicts cannot bypass it (SWI-125 Surface 7).
    """
    today = scan_date or date.today()
    for event in discoveries.get("events", []):
        ticker_raw = event.get("ticker")
        if _is_invalid_ticker(ticker_raw if isinstance(ticker_raw, str) else None):
            logger.warning(
                "Dropping capital event with invalid ticker: %r (event=%s)",
                ticker_raw,
                event,
            )
            continue
        ticker = (ticker_raw or "").strip().upper()
        event_type = event.get("event_type", "event")
        event_key = f"{ticker}_{event_type}_{today.isoformat()}"

        await upsert_capital_event(
            {
                "event_key": event_key,
                "ticker": ticker,
                "event_type": event_type,
                "description": event.get("description", ""),
                "amount": event.get("amount", ""),
                "expected_date": event.get("expected_date", ""),
                "dilution_pct": event.get("dilution_pct"),
                "impact": event.get("impact", "WATCH"),
                "source": event.get("source", "agent discovery"),
                "added_date": today,
            }
        )
