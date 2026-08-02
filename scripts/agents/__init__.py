"""
PydanticAI agents for trading analysis.
"""

from shared.market_calendar import is_trading_day as is_vn_trading_day

from .advocate_reviewer import run_bear_reviewer, run_bull_reviewer
from .critic import CritiqueResult, create_critic_agent, critique_with_agent
from .entry_strategist import generate_entry_strategy
from .foreign_flow import fetch_flow_with_agent
from .longterm import analyze_longterm_with_agent
from .macro import fetch_macro_metrics
from .market_level import classify_regime_with_agent
from .meta_controller import (
    RoutingDecision,
    WorkflowType,
    determine_workflow,
    get_workflow_config,
)
from .midday import create_midday_agent, run_midday_check_async
from .model import resolve_model  # noqa: F401
from .position_strategist import generate_position_guidance
from .positions_ensemble import monitor_positions_ensemble
from .positions_pev import monitor_positions_pev
from .retro import (
    evaluate_day_with_agent,
    evaluate_macro_for_day,
    evaluate_rotation_for_day,
    extract_patterns,
    generate_retro_with_agent,
)
from .sector import analyze_sector_with_agent
from .sector_rotation import detect_rotation_with_agent
from .strategy_director import generate_strategy_directive
from .synthesis import synthesize_with_agent
from .trade_simulator import (
    TradeSimulation,
    calculate_volatility,
    get_trend_drift,
    simulate_multiple_trades,
    simulate_trade,
)
from .trading_mode import determine_trading_mode
from .watchlist_ensemble import run_watchlist_update_ensemble
from .watchlist_update import apply_updates, save_report

__all__ = [
    # Sector
    "analyze_sector_with_agent",
    # Positions (PEV)
    "monitor_positions_pev",
    # Positions (Ensemble)
    "monitor_positions_ensemble",
    # Trade Simulator
    "simulate_trade",
    "simulate_multiple_trades",
    "TradeSimulation",
    "calculate_volatility",
    "get_trend_drift",
    # Meta-Controller
    "determine_workflow",
    "get_workflow_config",
    "is_vn_trading_day",
    "WorkflowType",
    "RoutingDecision",
    # Long-term
    "analyze_longterm_with_agent",
    # Market Level
    "classify_regime_with_agent",
    # Sector Rotation
    "detect_rotation_with_agent",
    # Foreign Flow
    "fetch_flow_with_agent",
    # Global Macro
    "fetch_macro_metrics",
    # Trading Mode
    "determine_trading_mode",
    # Strategy Director + Split Agents
    "generate_strategy_directive",
    "generate_position_guidance",
    "generate_entry_strategy",
    # Midday
    "run_midday_check_async",
    "create_midday_agent",
    # Advocate Reviewers
    "run_bull_reviewer",
    "run_bear_reviewer",
    # Synthesis
    "synthesize_with_agent",
    # Reflection (Critic — narrative quality only)
    "critique_with_agent",
    "create_critic_agent",
    "CritiqueResult",
    # Watchlist Update
    "run_watchlist_update_ensemble",
    "apply_updates",
    "save_report",
    # Retrospective
    "evaluate_day_with_agent",
    "extract_patterns",
    "generate_retro_with_agent",
    "evaluate_rotation_for_day",
    "evaluate_macro_for_day",
]
