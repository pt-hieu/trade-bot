"""Alert schema + LLM-driven alert generation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from shared.agent_config import load_agent_config

from ..agent_factory import AgentDeps, create_agent
from ..model.wrappers import OUTER_FALLBACK_STACK_WALL_S
from ..run_with_total_timeout import run_agent_with_total_timeout
from .verifiers import VerificationResult


class PositionAlert(BaseModel):
    """Alert for a single position."""

    ticker: str
    action: str  # HOLD, TRIM, ADD, EXIT
    urgency: str  # high, medium, low
    reason: str
    target: str  # Price target or "N/A"
    stop: str  # Stop-loss or "N/A"
    confidence: Literal["high", "medium", "low"] = "high"
    verification_notes: str = ""


class PositionMonitorResult(BaseModel):
    """Result from PEV position monitoring."""

    alerts: list[PositionAlert]
    summary: str
    # HOOK-ALLOW: empty-output-permitted — verification stats are
    # supplementary; an empty dict means no special-case stats to report.
    verification_stats: dict = Field(
        default_factory=dict, description="Stats on verification passes/failures"
    )


async def create_alert_agent() -> Agent[AgentDeps, PositionAlert]:
    """Create alert generation agent."""
    config = await load_agent_config("positions_pev_alert")
    # HOOK-ALLOW: no-broker-tools (alert agent reads pre-computed inputs only)
    return create_agent(config, output_type=PositionAlert)


async def generate_alert_with_agent(
    position: dict,
    longterm_config: dict | None,
    technicals: dict,
    verification: VerificationResult,
) -> PositionAlert:
    """Generate alert using LLM with verified data."""
    agent = await create_alert_agent()

    ticker = position.get("ticker") or position.get("name", "UNKNOWN")
    position_type = (
        "long-term" if longterm_config and longterm_config.get("is_longterm") else "swing"
    )

    levels = technicals.get("levels", {})
    stop_level = levels.get("swing_low") or levels.get("range_20d_low")
    target_level = levels.get("swing_high") or levels.get("range_20d_high")

    pl_pct = position.get("pct_from_entry")
    pl_repr = f"{pl_pct:+.1f}%" if isinstance(pl_pct, (int, float)) else "0.0%"

    prompt = f"""Generate alert for {ticker}:

Position Type: {position_type}
P/L: {pl_repr}
Shares: {position.get("shares", "N/A")}

Technicals:
- Price: {technicals.get("close", "N/A")}
- RSI: {technicals.get("rsi", "N/A")}
- MACD: {technicals.get("macd_histogram", "N/A")}
- Trend: {technicals.get("trend", {}).get("trend", "N/A")}
- Analysis: {technicals.get("analysis", "N/A")}

Levels:
- Stop (swing_low): {stop_level}
- Target (swing_high): {target_level}

{"Long-term config: " + str(longterm_config) if longterm_config else ""}

Verification confidence: {verification.confidence}
{"Verification issues: " + ", ".join(verification.issues) if verification.issues else ""}

Generate the appropriate alert with action, urgency, reason, target, and stop."""

    # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
    try:
        result = await run_agent_with_total_timeout(
            agent,
            prompt,
            agent_name="positions_pev_alert",
            deps=AgentDeps(
                scan_date=None,
                agent_key="positions_pev_alert",
                tickers_in_scope=[ticker],
            ),
            total_timeout_s=float(OUTER_FALLBACK_STACK_WALL_S),
        )
        alert = result.output
        alert.confidence = verification.confidence
        alert.verification_notes = ", ".join(verification.issues) if verification.issues else ""
        return alert
    except Exception as e:
        return PositionAlert(
            ticker=ticker,
            action="HOLD",
            urgency="low",
            reason=f"Alert generation failed: {e}",
            target="N/A",
            stop="N/A",
            confidence="low",
            verification_notes="Alert generation error",
        )
