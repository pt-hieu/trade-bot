"""Narrative labeling agent using PydanticAI."""

import logging
from datetime import date
from typing import Literal

from pydantic import BaseModel

from shared.agent_config import load_agent_config
from shared.anchor_tickers import prime_and_render_vn_prompt_header
from shared.observability import span
from shared.observability_post_llm import emit_rule_outcome
from shared.vn_universe import filter_vn_tickers

from .agent_factory import AgentDeps, create_agent
from .model.wrappers import OUTER_FALLBACK_STACK_WALL_S
from .run_with_total_timeout import run_agent_with_total_timeout

logger = logging.getLogger(__name__)


class NarrativeLabel(BaseModel):
    """LLM-generated label for a new narrative thread."""

    narrative_key: str
    theme: str
    narrative_type: Literal[
        "earnings", "regulatory", "macro", "corporate", "sector", "geopolitical", "general"
    ]
    affected_tickers: list[str]
    affected_sectors: list[str]
    trading_implication: str
    half_life_days: int


def collapse_macro_narrative_scope(label: NarrativeLabel) -> NarrativeLabel:
    """Backstop the prompt rule: macro/geopolitical narratives → ["VN-INDEX"] (SWI-195).

    A macro/geopolitical story affects the market broadly; the prompt asks for
    the ["VN-INDEX"] placeholder, but when the LLM emits specific tickers a
    mislabeled multi-ticker macro narrative over-attributes to individual names.
    Pure + deterministic so it is unit-testable and called from label_narrative
    after VN-universe filtering. Returns the (possibly mutated) label.
    """
    if label.narrative_type in ("macro", "geopolitical") and label.affected_tickers != ["VN-INDEX"]:
        emit_rule_outcome(
            "narrative_affected_scope",
            "coerced",
            agent="narrative_labeler",
            boundary="output_validator",
            fields_changed=("affected_tickers",),
            metadata={"narrative_type": label.narrative_type},
        )
        label.affected_tickers = ["VN-INDEX"]
    return label


async def label_narrative(article: dict, scan_date: date) -> NarrativeLabel:
    """Label a new narrative from a seed article using LLM.

    Primes + injects the VN ticker anchor so the LLM cannot drift toward
    non-VN codes (AUDIT-2026-04-24-001 / ISSUE-2026-04-24-005). Output
    is post-filtered through the VN universe before returning.
    """
    config = await load_agent_config("narrative_labeler")
    # HOOK-ALLOW: no-tickers-scope (narrative_labeler labels narratives, not ticker-scoped)
    agent = create_agent(config, output_type=NarrativeLabel)

    vn_header = await prime_and_render_vn_prompt_header()

    tickers = ", ".join(article.get("affected_tickers") or []) or "none identified"
    sectors = ", ".join(article.get("affected_sectors") or []) or "none identified"
    prompt = f"""{vn_header}

Label the following news article as a narrative thread for swing trading.

DATE: {scan_date}

ARTICLE:
Title: {article.get("title") or ""}
Summary: {article.get("summary") or ""}
Domain: {article.get("domain") or ""}
Affected tickers: {tickers}
Affected sectors: {sectors}
Sentiment score: {article.get("sentiment_score") or 0}

RULES:
- narrative_key: snake_case, max 40 chars, specific to this story (not generic)
- affected_tickers: output only VN-listed tickers from the anchor + hint map
  above. For macro or geopolitical stories that affect the Vietnamese market
  broadly, output the single placeholder ["VN-INDEX"] instead of listing
  tickers. Never return a non-VN code (US, HK, EU). Never return empty if the
  article clearly names a VN-listed company.
- affected_sectors: at least one sector (e.g., banking, real_estate, technology, energy, retail)
- trading_implication: one sentence on how this affects stock prices
- half_life_days: how long this narrative stays market-relevant (earnings=3, corporate=7, sector=7, regulatory=10, geopolitical=10, macro=14)"""

    with span("narrative_labeling", scan_date=str(scan_date)):
        result = await run_agent_with_total_timeout(
            agent,
            prompt,
            agent_name="narrative_labeler",
            deps=AgentDeps(scan_date=scan_date, agent_key="narrative_labeler"),
            total_timeout_s=float(OUTER_FALLBACK_STACK_WALL_S),
        )

    label = result.output
    label.affected_tickers = filter_vn_tickers(label.affected_tickers, context="narrative_labeler")
    return collapse_macro_narrative_scope(label)
