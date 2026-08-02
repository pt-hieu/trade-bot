"""PEV (Plan-Execute-Verify) Position Monitor Agent.

Adds verification layer to catch data quality issues and signal conflicts.
More robust than single-shot position monitoring.

Module layout (post-modularisation, SWI-212):
  * ``verifiers.py`` — VerificationResult + verify_technicals/context + LLM verifier.
  * ``alerts.py`` — PositionAlert/PositionMonitorResult + alert agent + generator.
  * ``__init__.py`` — monitor_positions_pev orchestrator + re-exports.
"""

from __future__ import annotations

from datetime import date

from ..tools.portfolio import get_holdings_async, get_longterm_watchlist_async
from ..tools.technicals import get_ticker_data_async
from .alerts import (
    PositionAlert,
    PositionMonitorResult,
    create_alert_agent,
    generate_alert_with_agent,
)
from .verifiers import (
    VerificationResult,
    create_verifier_agent,
    llm_verify_complex_case,
    verify_position_context,
    verify_technicals,
)


async def monitor_positions_pev(scan_date: date | None = None, max_retries: int = 2) -> dict:
    """PEV-based position monitoring with verification.

    Flow per position:
    1. PLAN: Determine what data to fetch
    2. EXECUTE: Fetch technicals, longterm config
    3. VERIFY: Validate data quality and consistency
    4. If invalid, retry with fallback
    5. GENERATE: Create alert with verified data
    """
    if scan_date is None:
        scan_date = date.today()

    holdings_data = await get_holdings_async()
    if holdings_data.get("error"):
        return {
            "alerts": [],
            "summary": f"Failed to get holdings: {holdings_data['error']}",
            "verification_stats": {"error": True},
        }

    if isinstance(holdings_data, dict) and "holdings" not in holdings_data:
        holdings = [
            {"ticker": ticker, **data}
            for ticker, data in holdings_data.items()
            if ticker not in ("error",)
        ]
    else:
        holdings = holdings_data.get("holdings", [])

    longterm_watchlist = await get_longterm_watchlist_async()

    alerts = []
    stats = {
        "total_positions": len(holdings),
        "verified_high": 0,
        "verified_medium": 0,
        "verified_low": 0,
        "verification_failures": 0,
        "retries_needed": 0,
    }

    for position in holdings:
        ticker = position.get("ticker") or position.get("name")
        position_type = position.get("type", "Stock")

        if not ticker:
            print(f"  [positions_pev] Skipping position with no ticker/name: {position}")
            continue

        if position_type in ("ETF", "Fund"):
            alerts.append(
                PositionAlert(
                    ticker=ticker,
                    action="HOLD",
                    urgency="low",
                    reason="Long-term investment fund",
                    target="N/A",
                    stop="N/A",
                    confidence="high",
                    verification_notes="",
                )
            )
            continue

        alert = None
        for attempt in range(max_retries):
            technicals = await get_ticker_data_async(ticker, scan_date)

            longterm_config = None
            if isinstance(longterm_watchlist, dict) and ticker.upper() in longterm_watchlist:
                longterm_config = longterm_watchlist[ticker.upper()]
                longterm_config["is_longterm"] = True

            tech_verification = verify_technicals(ticker, technicals)
            context_verification = verify_position_context(position, longterm_config, technicals)

            all_issues = tech_verification.issues + context_verification.issues
            combined_confidence = (
                "low"
                if tech_verification.confidence == "low" or context_verification.confidence == "low"
                else (
                    "medium"
                    if tech_verification.confidence == "medium"
                    or context_verification.confidence == "medium"
                    else "high"
                )
            )

            combined_verification = VerificationResult(
                is_valid=tech_verification.is_valid and context_verification.is_valid,
                confidence=combined_confidence,
                issues=all_issues,
                suggestion=tech_verification.suggestion or context_verification.suggestion,
            )

            if combined_verification.is_valid or attempt == max_retries - 1:
                alert = await generate_alert_with_agent(
                    position, longterm_config, technicals, combined_verification
                )

                if combined_verification.confidence == "high":
                    stats["verified_high"] += 1
                elif combined_verification.confidence == "medium":
                    stats["verified_medium"] += 1
                else:
                    stats["verified_low"] += 1

                if attempt > 0:
                    stats["retries_needed"] += 1

                break
            else:
                stats["verification_failures"] += 1

        if alert:
            alerts.append(alert)

    actionable = [a for a in alerts if a.action in ("EXIT", "TRIM", "ADD")]
    high_urgency = [a for a in alerts if a.urgency == "high"]

    summary_parts = [
        f"Analyzed {len(holdings)} positions.",
        f"{len(actionable)} actionable alerts ({len(high_urgency)} high urgency).",
    ]

    if stats["verification_failures"] > 0:
        summary_parts.append(
            f"Data quality: {stats['verification_failures']} verification retries."
        )

    low_confidence = [a for a in alerts if a.confidence == "low"]
    if low_confidence:
        summary_parts.append(
            f"Low confidence alerts: {', '.join(a.ticker for a in low_confidence)}"
        )

    return {
        "alerts": [alert.model_dump() for alert in alerts],
        "summary": " ".join(summary_parts),
        "verification_stats": stats,
    }


__all__ = [
    "PositionAlert",
    "PositionMonitorResult",
    "VerificationResult",
    "create_alert_agent",
    "create_verifier_agent",
    "generate_alert_with_agent",
    "llm_verify_complex_case",
    "monitor_positions_pev",
    "verify_position_context",
    "verify_technicals",
]
