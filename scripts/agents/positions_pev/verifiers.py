"""Rule-based + LLM verification for position monitoring data."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from shared.agent_config import load_agent_config

from ..agent_factory import AgentDeps, create_agent
from ..model.wrappers import OUTER_FALLBACK_STACK_WALL_S
from ..run_with_total_timeout import run_agent_with_total_timeout


class VerificationResult(BaseModel):
    """Result from verifying position data."""

    is_valid: bool = Field(description="Whether the data passed verification")
    confidence: Literal["high", "medium", "low"] = Field(
        description="Confidence level in the data quality"
    )
    # HOOK-ALLOW: empty-output-permitted — clean verification legitimately
    # has zero issues; emptiness is a passing signal here, not a defect.
    issues: list[str] = Field(
        default_factory=list, description="List of issues found during verification"
    )
    suggestion: str | None = Field(
        default=None, description="Suggested action if verification failed"
    )


def verify_technicals(ticker: str, data: dict) -> VerificationResult:
    """Verify technical data quality."""
    issues = []
    confidence = "high"

    if data.get("error"):
        return VerificationResult(
            is_valid=False,
            confidence="low",
            issues=[f"Technical data error: {data['error']}"],
            suggestion="Skip technicals, use price-only analysis",
        )

    if data.get("rsi") is None:
        issues.append("Missing RSI")
        confidence = "medium"

    if data.get("macd") is None:
        issues.append("Missing MACD")
        confidence = "medium"

    levels = data.get("levels", {})
    if not levels.get("nearest_support") and not levels.get("swing_low"):
        issues.append("Missing support levels")
        confidence = "medium"

    if not levels.get("nearest_resistance") and not levels.get("swing_high"):
        issues.append("Missing resistance levels")
        confidence = "medium"

    rsi = data.get("rsi")
    macd_hist = data.get("macd_histogram")
    if rsi is not None and macd_hist is not None:
        rsi_signal = "bullish" if rsi < 40 else "bearish" if rsi > 60 else "neutral"
        macd_signal = "bullish" if macd_hist > 0 else "bearish"

        if rsi_signal != "neutral" and rsi_signal != macd_signal:
            issues.append(f"Conflicting signals: RSI {rsi_signal}, MACD {macd_signal}")
            confidence = "medium" if confidence == "high" else "low"

    if rsi is not None and (rsi < 5 or rsi > 95):
        issues.append(f"Extreme RSI value: {rsi}")
        confidence = "low"

    price = data.get("close") or data.get("price")
    if price is not None and price <= 0:
        issues.append(f"Invalid price: {price}")
        return VerificationResult(
            is_valid=False, confidence="low", issues=issues, suggestion="Re-fetch price data"
        )

    stop = levels.get("swing_low") or levels.get("range_20d_low")
    target = levels.get("swing_high") or levels.get("range_20d_high")
    if price and stop and target:
        if stop >= price:
            issues.append(f"Stop ({stop}) >= current price ({price})")
            confidence = "low"
        if target <= price:
            issues.append(f"Target ({target}) <= current price ({price})")
            confidence = "low"

    return VerificationResult(
        is_valid=len([i for i in issues if "Invalid" in i or "error" in i.lower()]) == 0,
        confidence=confidence,
        issues=issues,
        suggestion="Use partial data with caution" if issues else None,
    )


def verify_position_context(
    position: dict, longterm_config: dict | None, technicals: dict | None
) -> VerificationResult:
    """Verify position context makes sense."""
    issues = []
    confidence = "high"

    ticker = position.get("ticker") or position.get("name")
    if not ticker:
        return VerificationResult(
            is_valid=False,
            confidence="low",
            issues=["Position missing ticker"],
            suggestion="Skip this position",
        )

    pl_pct = position.get("pl_pct") or position.get("P/L %")
    if pl_pct is None:
        issues.append("Missing P/L percentage")
        confidence = "medium"
    elif isinstance(pl_pct, str):
        try:
            pl_pct = float(pl_pct.replace("%", "").replace(",", ""))
        except ValueError:
            issues.append(f"Invalid P/L format: {pl_pct}")
            confidence = "medium"

    if isinstance(pl_pct, (int, float)) and (pl_pct < -50 or pl_pct > 100):
        issues.append(f"Extreme P/L: {pl_pct}% - verify accuracy")
        confidence = "low"

    if longterm_config and longterm_config.get("is_longterm"):
        entry_zone = longterm_config.get("entry_zone")
        if entry_zone and technicals:
            price = technicals.get("close") or technicals.get("price")
            if price and entry_zone:
                try:
                    if "-" in str(entry_zone):
                        low, high = str(entry_zone).replace(",", "").split("-")
                        zone_low, _zone_high = float(low), float(high)
                    else:
                        zone_low = float(str(entry_zone).replace(",", ""))

                    if price < zone_low * 0.7:
                        issues.append(f"Price ({price}) far below entry zone ({entry_zone})")
                except (ValueError, TypeError):
                    pass

    return VerificationResult(
        is_valid=True,
        confidence=confidence,
        issues=issues,
        suggestion="Review position data" if issues else None,
    )


async def create_verifier_agent() -> Agent[AgentDeps, VerificationResult]:
    """Create LLM-based verifier for complex edge cases."""
    config = await load_agent_config("positions_pev_verifier")
    # HOOK-ALLOW: no-broker-tools (verifier reads pre-computed inputs only)
    return create_agent(config, output_type=VerificationResult)


async def llm_verify_complex_case(
    position: dict, technicals: dict, proposed_action: str
) -> VerificationResult:
    """Use LLM to verify complex edge cases."""
    agent = await create_verifier_agent()

    pl_pct = position.get("pct_from_entry")
    pl_repr = f"{pl_pct:+.1f}%" if isinstance(pl_pct, (int, float)) else "N/A"

    prompt = f"""Verify this position analysis:

Position: {position.get("ticker")} ({position.get("type", "Stock")})
P/L: {pl_repr}
Current Price: {technicals.get("close", "N/A")}

Technical Data:
- RSI: {technicals.get("rsi", "N/A")}
- MACD Histogram: {technicals.get("macd_histogram", "N/A")}
- Trend: {technicals.get("trend", {}).get("trend", "N/A")}
- Pattern: {technicals.get("pattern", {}).get("pattern", "N/A")}

Support/Resistance:
- Swing Low: {technicals.get("levels", {}).get("swing_low", "N/A")}
- Swing High: {technicals.get("levels", {}).get("swing_high", "N/A")}

Proposed Action: {proposed_action}

Is this recommendation appropriate given the data? Check for any inconsistencies."""

    # HOOK-ALLOW: silent-swallow rationale=SWI-306 follow-up; agent treats all errors as fallback-eligible. Switching to typed handler requires per-agent degradation review.
    try:
        result = await run_agent_with_total_timeout(
            agent,
            prompt,
            agent_name="positions_pev_verifier",
            deps=AgentDeps(
                scan_date=None,
                agent_key="positions_pev_verifier",
                tickers_in_scope=[position.get("ticker") or "UNKNOWN"],
            ),
            total_timeout_s=float(OUTER_FALLBACK_STACK_WALL_S),
        )
        return result.output
    except Exception as e:
        return VerificationResult(
            is_valid=True,
            confidence="medium",
            issues=[f"LLM verification failed: {e}"],
            suggestion="Proceed with caution",
        )
