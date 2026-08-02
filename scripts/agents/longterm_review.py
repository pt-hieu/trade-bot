#!/usr/bin/env python3
"""
Long-Term Review Agent.

Monthly agent that refreshes company research, validates/adjusts entry zones (±10%),
adjusts conviction (±1 level), recommends new additions, flags removals.

Uses batched LLM calls (BATCH_SIZE tickers per call) to avoid output truncation.
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field, model_validator

from shared.agent_config import build_usage_limits, load_agent_config
from shared.rules.vnd_price_clamp import clamp_vnd_field

from .agent_factory import AgentDeps, create_agent
from .run_with_total_timeout import run_agent_with_total_timeout

BATCH_SIZE = 3


class ThesisPillar(BaseModel):
    """A single thesis pillar with status and evidence."""

    name: str = Field(description="Short name for this pillar (e.g., 'Dominant market share')")
    description: str = Field(description="1-2 sentences describing the pillar")
    status: str = Field(
        default="INTACT", description="INTACT / WEAKENING / BROKEN — based on most recent evidence"
    )
    evidence: str = Field(
        default="",
        description="Specific evidence supporting current status. "
        "WEAKENING: include path back to INTACT. INTACT: include specific weakening risk.",
    )


class KillCriterion(BaseModel):
    """A measurable condition that would invalidate the investment thesis."""

    condition: str = Field(
        description="Specific, measurable condition. "
        "Example: 'ROE below 8% for 3 consecutive quarters'"
    )
    status: str = Field(
        default="NOT_MET", description="NOT_MET / WARNING / TRIGGERED — current assessment"
    )
    rationale: str = Field(default="", description="Why this condition would break the thesis")


class MoatAssessment(BaseModel):
    """Structured moat rating along 4 dimensions."""

    network_effects: str = Field(
        description="Strength of network effects: STRONG/MODERATE/WEAK/NONE. "
        "Must match moat_evidence. NONE only if explicitly not applicable."
    )
    switching_costs: str = Field(
        description="Customer switching cost barriers: STRONG/MODERATE/WEAK/NONE. "
        "Must match moat_evidence."
    )
    scale_economies: str = Field(
        description="Scale-based cost advantages: STRONG/MODERATE/WEAK/NONE. "
        "Must match moat_evidence."
    )
    intangible_assets: str = Field(
        description="Brand/IP/license advantages: STRONG/MODERATE/WEAK/NONE. "
        "Must match moat_evidence."
    )
    fol_premium: bool = Field(
        description="True if stock benefits from FOL premium (foreign ownership limit)"
    )
    state_ownership: bool = Field(
        description="True if state ownership provides durable competitive advantages"
    )
    regulatory_license: bool = Field(
        description="True if company holds hard-to-obtain regulatory licenses (banking, insurance, etc.)"
    )
    moat_evidence: str = Field(
        description="1-2 sentences citing specific evidence for the STRONGEST dimension. "
        "Structured field ratings above MUST be consistent with this evidence."
    )


class StockResearch(BaseModel):
    """LLM review output for a single existing watchlist stock."""

    ticker: str
    overview: str = Field(description="2-4 sentence company overview, updated for current context")
    moat: str = Field(description="2-4 sentences on competitive moat and defensibility")
    growth: str = Field(description="2-4 sentences on key growth drivers and catalysts")
    risks: str = Field(description="2-4 sentences on main risks to the thesis")
    valuation: str = Field(description="2-4 sentences on current valuation vs historical and peers")
    thesis: str = Field(description="2-4 sentence investment thesis summary with key catalyst")
    entry_zone_adjustment_pct: float = Field(
        description="Adjustment to calculated entry zone: -10 to +10 (%). 0 = agree with formula. "
        "Positive = increase (stock warrants premium), negative = decrease (more margin of safety needed). "
        "You MUST explicitly choose a value — do not default to 0 without analysis.",
    )
    entry_zone_reason: str = Field(
        description="REQUIRED for every stock. If adjustment != 0: specific reason for override. "
        "If adjustment == 0: explain why formula assumptions still hold (e.g., 'Metrics stable, no divergence').",
    )
    conviction_adjustment: int = Field(
        description="Adjustment to calculated conviction level: -1, 0, or +1. "
        "0 = agree with formula. Use ±1 with strong specific reason. "
        "You MUST explicitly choose — do not default to 0 without analysis.",
    )
    conviction_reason: str = Field(
        description="REQUIRED for every stock. If adjustment != 0: specific reason. "
        "If adjustment == 0: explain why conviction level remains appropriate.",
    )
    moat_assessment: MoatAssessment | None = Field(
        default=None, description="Structured 4-dimension moat rating with Vietnam factors"
    )
    thesis_pillars: list[ThesisPillar] | None = Field(
        default=None,
        description="3-5 thesis pillars with INTACT/WEAKENING/BROKEN status and evidence",
    )
    kill_criteria: list[KillCriterion] | None = Field(
        default=None, description="2-3 measurable conditions that would invalidate the thesis"
    )


class BatchReviewResult(BaseModel):
    """LLM output for a single batch of stocks (no additions/removals/outlook)."""

    stocks: list[StockResearch]


class NewStockRecommendation(BaseModel):
    """Recommendation to add a new ticker to the longterm watchlist."""

    ticker: str
    sector: str
    suggested_entry_zone_vnd: int = Field(description="Suggested entry zone in VND (not thousands)")
    suggested_conviction: str = Field(
        description="One of: High, Medium-High, Medium, Medium-Low, Low"
    )
    suggested_tier: int = Field(default=2, description="1 = core, 2 = watch")
    thesis: str = Field(description="2-4 sentences: why add this stock, key moat, entry rationale")

    @model_validator(mode="after")
    def _normalize_suggested_entry_zone_vnd(self) -> NewStockRecommendation:
        """Catch LLM dropped-zeros (e.g. 44 → 44000 when thesis cites 44,000)."""
        clamp_vnd_field(self, "suggested_entry_zone_vnd", self.thesis, agent="longterm_review")
        return self


class RemovalFlag(BaseModel):
    """Flag a stock for potential removal from the longterm watchlist."""

    ticker: str
    reason: str = Field(
        description="Specific reason: thesis has broken (e.g., sustained ROE decline below 8% for 3Q+, "
        "governance failure, sector disruption). Not just current price being high."
    )


class CrossCuttingResult(BaseModel):
    """LLM output for portfolio-level decisions (additions, removals, market outlook)."""

    # HOOK-ALLOW: empty-output-permitted (no additions is a valid review outcome)
    additions: list[NewStockRecommendation] = Field(
        default_factory=list,
        description="New tickers recommended for addition (0-3 max)",
    )
    # HOOK-ALLOW: empty-output-permitted (no removals is a valid review outcome)
    removals: list[RemovalFlag] = Field(
        default_factory=list,
        description="Stocks flagged for removal due to clear thesis breaks",
    )
    market_outlook: str = Field(
        description="2-3 sentence outlook for Vietnamese long-term investing context, "
        "relevant to watchlist management (FTSE upgrade, macro, sector rotation)"
    )


class LongtermReviewResult(BaseModel):
    """Full output from the monthly longterm review agent."""

    stocks: list[StockResearch] = Field(
        description="Research updates for all existing active watchlist stocks"
    )
    # HOOK-ALLOW: empty-output-permitted (no additions is a valid review outcome)
    additions: list[NewStockRecommendation] = Field(
        default_factory=list,
        description="New tickers recommended for addition (0-3 max)",
    )
    # HOOK-ALLOW: empty-output-permitted (no removals is a valid review outcome)
    removals: list[RemovalFlag] = Field(
        default_factory=list,
        description="Stocks flagged for removal due to clear thesis breaks",
    )
    market_outlook: str = Field(
        description="2-3 sentence outlook for Vietnamese long-term investing context, "
        "relevant to watchlist management (FTSE upgrade, macro, sector rotation)"
    )


# ── Helpers ────────────────────────────────────────────────────────────────────


def _filter_summary_for_batch(deterministic_summary: str, batch_tickers: list[str]) -> str:
    """Extract deterministic summary lines for the given batch tickers only."""
    lines = deterministic_summary.splitlines()
    header = [lines[0]] if lines else []
    batch_set = set(batch_tickers)
    relevant = [line for line in lines[1:] if any(line.startswith(t) for t in batch_set)]
    return "\n".join(header + relevant)


def _format_candidates(candidates: list[dict]) -> str:
    """Format candidates list into a prompt string."""
    if not candidates:
        return ""
    rows = []
    for c in candidates[:8]:
        price_str = f", Price={c['current_price'] // 1000}k" if c.get("current_price") else ""
        rows.append(
            f"  {c['ticker']}: ROE={c['roe']:.1f}%, PE={c['pe']:.1f}, "
            f"Margin={c['net_margin'] * 100:.1f}%, Score={c['score']}, Sector={c['sector']}{price_str}"
        )
    return "\nScreened VN30 candidates (passed ROE>10%, PE<30, positive margin):\n" + "\n".join(
        rows
    )


# ── Runner ────────────────────────────────────────────────────────────────────


async def run_longterm_review(
    watchlist_tickers: list[str],
    candidates: list[dict],
    deterministic_summary: str,
    sector_summary: str = "",
    stock_sectors: dict[str, str] | None = None,
) -> LongtermReviewResult:
    """Run the longterm review agent with batched LLM calls.

    Splits tickers into batches of BATCH_SIZE to avoid output truncation,
    then makes a final cross-cutting call for additions/removals/outlook.

    Args:
        watchlist_tickers: Active tickers to review
        candidates: Screened VN30 candidates from screen_candidates()
        deterministic_summary: Pre-formatted string of deterministic calc results

    Returns:
        LongtermReviewResult with research, adjustments, additions, removals
    """
    config = await load_agent_config("longterm_review")
    candidates_str = _format_candidates(candidates)

    # ── Phase A: Per-batch stock reviews ──────────────────────────────────────
    all_stocks: list[StockResearch] = []
    batches = [
        watchlist_tickers[i : i + BATCH_SIZE] for i in range(0, len(watchlist_tickers), BATCH_SIZE)
    ]

    for batch_num, batch in enumerate(batches, 1):
        # HOOK-ALLOW: no-tickers-scope (longterm_review batches its own ticker list per call)
        batch_agent = create_agent(config, output_type=BatchReviewResult)
        batch_summary = _filter_summary_for_batch(deterministic_summary, batch)
        tickers_str = ", ".join(batch)

        prompt = f"""Conduct the monthly long-term watchlist review for this batch of stocks.

Active watchlist stocks to review (batch {batch_num}/{len(batches)}): {tickers_str}

Deterministic calculations (pre-computed baselines):
{batch_summary}

Gather data for ALL stocks in this batch using batch calls (pass all tickers at once where possible):
1. fundamental.get_valuation — financial ratios and valuation metrics
2. fundamental.get_valuation_history — PE/PB trends for forward earnings assessment
3. fundamental.get_earnings_quality — core earnings ratio and quality check
4. article.search — recent news and catalysts (per ticker)
5. portfolio.read_research — existing research context (per ticker)

Then for EACH stock:
- Generate updated research sections (overview, moat, growth, risks, valuation, thesis)
- Validate the pre-calculated entry zone and conviction — adjust where warranted

Return research updates for ALL {len(batch)} stocks in this batch."""

        # HOOK-ALLOW: outer-wall-helper rationale=SWI-306 batch agent orchestration; 900s spans multiple stocks per batch + research, not a single agent's failover stack.
        result = await run_agent_with_total_timeout(
            batch_agent,
            prompt,
            agent_name="longterm_review_batch",
            deps=AgentDeps(scan_date=None, agent_key="longterm_review_batch"),
            total_timeout_s=900,
            usage_limits=build_usage_limits(config),
        )
        all_stocks.extend(result.output.stocks)

    # ── Phase B: Portfolio-level decisions ────────────────────────────────────
    # HOOK-ALLOW: no-tickers-scope (cross-cutting agent operates on full reviewed set, not a single batch)
    cross_agent = create_agent(config, output_type=CrossCuttingResult)
    reviewed_tickers = ", ".join(s.ticker for s in all_stocks)

    # Build sector distribution for cross-agent awareness
    sector_dist_str = ""
    if stock_sectors:
        sector_counts = Counter(stock_sectors.get(t, "Unknown") for t in watchlist_tickers)
        total = len(watchlist_tickers)
        sector_dist_str = "\n".join(
            f"  {s}: {c}/{total} ({c / total * 100:.0f}%)" for s, c in sector_counts.most_common()
        )
        sector_dist_str = f"\nCurrent watchlist sector distribution:\n{sector_dist_str}"

    cross_prompt = f"""You have just reviewed the longterm watchlist stocks: {reviewed_tickers}

Now make portfolio-level decisions.

{sector_summary}
{sector_dist_str}
{candidates_str}

1. For top 3-5 screened candidates (if any), call fundamental.get_valuation and article.search for each
2. Prefer additions in UNDERWEIGHT sectors — do NOT add stocks to sectors already at or above target allocation
3. Flag any existing stocks for removal only if thesis has clearly broken (ROE decline 3Q+, leverage crisis, governance failure)
4. Write a market_outlook covering all sectors in the watchlist
5. CONCENTRATION RISK: If any sector exceeds 40% of the watchlist, flag it in market_outlook and avoid recommending additions in that sector

Return additions (0-3 max), removals, and market_outlook."""

    # HOOK-ALLOW: outer-wall-helper rationale=SWI-306 cross-stocks orchestration; 300s budget for whole-watchlist reasoning, not a single agent's failover hop.
    cross_result = await run_agent_with_total_timeout(
        cross_agent,
        cross_prompt,
        agent_name="longterm_review_cross",
        deps=AgentDeps(
            scan_date=None,
            agent_key="longterm_review_cross",
            tickers_in_scope=[s.ticker for s in all_stocks],
        ),
        total_timeout_s=300,
        usage_limits=build_usage_limits(config),
    )

    # ── Merge into final result ────────────────────────────────────────────────
    return LongtermReviewResult(
        stocks=all_stocks,
        additions=cross_result.output.additions,
        removals=cross_result.output.removals,
        market_outlook=cross_result.output.market_outlook,
    )
