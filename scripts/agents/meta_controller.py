#!/usr/bin/env python3
"""
Meta-Controller for adaptive workflow routing.

Analyzes trading context and routes to the appropriate workflow:
- FULL: Normal trading day, all analyses
- EXIT_ONLY: Low cash or crisis, exits only
- RESEARCH: Weekend/holiday, long-term research
- QUICK: Urgent alerts, minimal analysis
"""

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class WorkflowType(str, Enum):
    """Available workflow types."""

    FULL = "full"  # Normal trading day - all analyses
    EXIT_ONLY = "exit_only"  # Low cash/crisis - exits only
    RESEARCH = "research"  # Weekend/holiday - research mode
    QUICK = "quick"  # Urgent exits - quick scan


class RoutingContext(BaseModel):
    """Context used for routing decision."""

    scan_date: date
    is_trading_day: bool
    trading_mode: str  # NORMAL, LOW_CASH, REALLOCATION
    market_regime: str  # RISK_ON, NEUTRAL, RISK_OFF
    global_macro_regime: str  # CALM, CAUTIOUS, ELEVATED, CRISIS
    urgent_exits: int = 0
    deployable_cash: float = 0


class RoutingDecision(BaseModel):
    """Result of meta-controller routing."""

    workflow: WorkflowType
    reasoning: str
    context_summary: str
    # HOOK-ALLOW: empty-output-permitted (most workflows skip nothing — empty list is the common case)
    skip_agents: list[str] = Field(default_factory=list)
    # HOOK-ALLOW: empty-output-permitted (default routing has no priority overrides)
    priority_agents: list[str] = Field(default_factory=list)


def determine_workflow(
    trading_mode: str,
    market_regime: str,
    global_macro_regime: str,
    is_trading_day: bool,
    urgent_exits: int = 0,
    deployable_cash: float = 0,
) -> RoutingDecision:
    """
    Meta-controller routing logic.

    Determines the appropriate workflow based on trading context.

    Args:
        trading_mode: NORMAL, LOW_CASH, or REALLOCATION
        market_regime: RISK_ON, NEUTRAL, or RISK_OFF
        global_macro_regime: CALM, CAUTIOUS, ELEVATED, or CRISIS
        is_trading_day: Whether market is open
        urgent_exits: Count of high-urgency position alerts
        deployable_cash: Available cash for new positions

    Returns:
        RoutingDecision with workflow and context
    """
    reasons = []

    # Rule 1: Weekend/Holiday → Research only (sectors still run for Monday prep)
    if not is_trading_day:
        return RoutingDecision(
            workflow=WorkflowType.RESEARCH,
            reasoning="Market closed - research mode with sector news",
            context_summary="Non-trading day",
            skip_agents=["positions", "synthesis"],
            priority_agents=["macro", "sector_analysis"],
        )

    # Rule 2: Crisis → Exit only (sectors still run — news catalysts inform exit timing)
    if global_macro_regime == "CRISIS":
        return RoutingDecision(
            workflow=WorkflowType.EXIT_ONLY,
            reasoning="Global macro CRISIS - exit focus with sector news for context",
            context_summary=f"CRISIS mode, {trading_mode} trading",
            skip_agents=["longterm", "foreign_flow"],
            priority_agents=["positions", "market_level", "sector_analysis"],
        )

    # Rule 3: Low cash with no deployable → Exit focus (sectors for context)
    if trading_mode == "LOW_CASH" and deployable_cash <= 0:
        reasons.append("No deployable cash")
        return RoutingDecision(
            workflow=WorkflowType.EXIT_ONLY,
            reasoning="LOW_CASH with zero deployable - exit focus with sector news",
            context_summary="LOW_CASH mode, 0 VND deployable",
            skip_agents=["longterm"],
            priority_agents=["positions", "sector_analysis"],
        )

    # Rule 4: Elevated macro or Risk-off → Full analysis with elevated quality bar.
    # ELEVATED/RISK_OFF should raise the R:R requirement, not shut down analysis entirely.
    # The strategy_director circuit breaker enforces the quality bar downstream.
    # Only CRISIS (Rule 2 above) triggers a true defensive mode.
    if global_macro_regime == "ELEVATED" or market_regime == "RISK_OFF":
        # Phase 2 §2.8 — authoritative-first via shared formatter.
        from pipeline.context_blocks_macro import format_dual_regime_labels

        regime_info = format_dual_regime_labels(
            global_risk_regime=global_macro_regime,
            technical_regime=market_regime,
            style="compact",
        )
        return RoutingDecision(
            workflow=WorkflowType.FULL,
            reasoning=f"Elevated conditions ({regime_info}) — full analysis, higher quality bar",
            context_summary=f"Elevated: {regime_info}",
            skip_agents=[],
            priority_agents=["positions", "macro", "market_level"],
        )

    # Rule 5: Urgent exits pending → Quick scan first
    if urgent_exits > 0:
        return RoutingDecision(
            workflow=WorkflowType.QUICK,
            reasoning=f"{urgent_exits} urgent exit(s) pending - quick scan",
            context_summary=f"Urgent exits: {urgent_exits}",
            skip_agents=["longterm", "foreign_flow"],
            priority_agents=["positions"],
        )

    # Rule 6: Reallocation mode → Include exits in analysis
    if trading_mode == "REALLOCATION":
        return RoutingDecision(
            workflow=WorkflowType.FULL,
            reasoning="REALLOCATION mode - full analysis with exit focus",
            context_summary="Reallocation mode",
            skip_agents=[],
            priority_agents=["positions", "sector_analysis"],
        )

    # Rule 6b: Low cash with some deployable — skip research-only agents
    if trading_mode == "LOW_CASH" and deployable_cash > 0:
        return RoutingDecision(
            workflow=WorkflowType.FULL,
            reasoning="LOW_CASH with limited cash — full analysis, skip research agents",
            context_summary=f"LOW_CASH, {deployable_cash:.0f} VND deployable",
            skip_agents=["longterm", "foreign_flow"],
            priority_agents=["positions", "sector_analysis"],
        )

    # Default: Normal conditions → Full analysis
    # Phase 2 §2.8 — authoritative regime first via shared formatter.
    from pipeline.context_blocks_macro import format_dual_regime_labels

    regime_info = format_dual_regime_labels(
        global_risk_regime=global_macro_regime,
        technical_regime=market_regime,
        style="compact",
    )
    return RoutingDecision(
        workflow=WorkflowType.FULL,
        reasoning="Normal trading conditions - full analysis",
        context_summary=f"{regime_info}, {trading_mode}",
        skip_agents=[],
        priority_agents=[],
    )


def get_workflow_config(workflow: WorkflowType) -> dict:
    """
    Get configuration for a workflow type.

    Returns:
        Dict with agents to run, synthesis mode, etc.
    """
    configs = {
        WorkflowType.FULL: {
            "run_sectors": True,
            "run_longterm": False,
            "run_positions": True,
            "run_foreign_flow": True,
            "description": "Full analysis with all agents",
        },
        WorkflowType.EXIT_ONLY: {
            "run_sectors": True,
            "run_longterm": False,
            "run_positions": True,
            "run_foreign_flow": False,
            "description": "Exit focus with sector news for systemic context",
        },
        WorkflowType.RESEARCH: {
            "run_sectors": True,
            "run_longterm": True,
            "run_positions": False,
            "run_foreign_flow": False,
            "description": "Research mode - long-term + sector news for Monday prep",
        },
        WorkflowType.QUICK: {
            "run_sectors": False,
            "run_longterm": False,
            "run_positions": True,
            "run_foreign_flow": False,
            "description": "Quick scan - urgent alerts only",
        },
    }
    return configs.get(workflow, configs[WorkflowType.FULL])


def format_routing_summary(decision: RoutingDecision) -> str:
    """Format routing decision for logging."""
    config = get_workflow_config(decision.workflow)
    lines = [
        f"Workflow: {decision.workflow.value.upper()}",
        f"Reason: {decision.reasoning}",
        f"Context: {decision.context_summary}",
        f"Description: {config['description']}",
    ]
    if decision.skip_agents:
        lines.append(f"Skip: {', '.join(decision.skip_agents)}")
    if decision.priority_agents:
        lines.append(f"Priority: {', '.join(decision.priority_agents)}")
    return "\n".join(lines)
