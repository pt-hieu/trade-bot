"""
Neon (PostgreSQL) helpers for Trading Hub integration.

Async database queries for all trading data.
Re-exports all public symbols from submodules for backwards compatibility.
"""

# ── Utilities ───────────────────────────────────────────────────────────────
# ── Types ───────────────────────────────────────────────────────────────────
from ._types import (
    AfternoonAction,
    AfternoonActionConfidence,
    AfternoonActionKind,
    ClosedTradeEntry,
    GoalData,
    HoldingData,
    LongtermWatchlistEntry,
    MacroHistoryEntry,
    MacroMetricsData,
    MarketRegimeData,
    MiddayBigMover,
    MiddayCheckData,
    MiddayEntryHit,
    MiddayPositionAlert,
    OpenedTradeEntry,
    RegimeHistoryEntry,
    RemoveStockResult,
    SectorRotationData,
    SwingTradeStats,
    SwingWatchlistRsiEntry,
    TradeData,
    TradesForDateData,
)
from ._utils import safe_float, safe_round

# ── Watchlist ────────────────────────────────────────────────────────────────
# ── Checkpoints ────────────────────────────────────────────────────────────
# ── Beliefs ─────────────────────────────────────────────────────────────────
# ── Alerts ──────────────────────────────────────────────────────────────────
from .alerts import (
    cancel_alerts_for_date,
    cancel_alerts_for_date_sync,
    expire_stale_alerts,
    expire_stale_alerts_sync,
    get_active_alerts,
    get_active_alerts_sync,
    get_alerts_for_web,
    get_alerts_for_web_sync,
    get_recent_trigger_times,
    register_alert,
    # sync
    register_alert_sync,
    register_alerts_batch,
    trigger_alert,
)

# ── Articles ─────────────────────────────────────────────────────────────────
from .articles import (
    get_issued_query_names,
    list_articles,
    list_articles_by_ticker,
    list_articles_range,
    load_articles_for_scan_date,
    read_article,
    search_articles,
)
from .beliefs import (
    get_agent_belief_accuracy,
    get_all_belief_accuracy,
    get_latest_aggregated_beliefs,
    get_prior_beliefs,
    get_stale_beliefs,
    get_unresolved_beliefs,
    insert_agent_beliefs,
    resolve_beliefs,
    tombstone_beliefs,
)

# ── Catalysts & Capital Events ──────────────────────────────────────────────
from .catalysts import (
    complete_catalyst,
    complete_catalyst_sync,
    get_active_catalysts_db,
    # sync
    get_active_catalysts_db_sync,
    get_upcoming_capital_events_db,
    get_upcoming_capital_events_db_sync,
    link_catalyst_articles,
    refresh_catalyst_lifecycle,
    update_catalyst_field,
    upsert_capital_event,
    upsert_capital_event_sync,
    upsert_catalyst,
    upsert_catalyst_sync,
)
from .checkpoints import load_checkpoint, save_checkpoint  # noqa: F401 (re-exports)

# ── Company Profiles ──────────────────────────────────────────────────────
from .company_profiles import (
    get_company_profile,
    get_company_profile_sync,
    get_macro_sensitivities,
    get_profiles_batch,
    get_universe_with_aliases,
    resolve_tickers_by_factors_batch,
    resolve_tickers_by_macro_factor,
    resolve_tickers_by_macro_factor_sync,
    upsert_company_profile,
    upsert_company_profile_sync,
)

# ── Directives ──────────────────────────────────────────────────────────────
from .directives import (
    get_strategy_directive,
    save_strategy_directive,
)

# ── Enrichment (relative strength only — flow/insider/events now in shared.api.enrichment)
from .enrichment import get_relative_strength

# ── Ensemble Vote History ────────────────────────────────────────────────────
from .ensemble import get_ensemble_vote_history, get_ensemble_vote_history_batch

# ── Market ───────────────────────────────────────────────────────────────────
from .flow import get_foreign_flow

# ── Insert: Content ──────────────────────────────────────────────────────────
from .insert_content import (
    insert_articles,
    # sync
    insert_articles_sync,
    insert_midday_check,
    insert_midday_check_sync,
    write_article_sentiments,
)

# ── Insert: Learnings ────────────────────────────────────────────────────────
from .insert_learnings import (
    insert_learnings,
    # sync
    insert_learnings_sync,
)

# ── Insert: Market ───────────────────────────────────────────────────────────
from .insert_market import (
    insert_foreign_flow,
    insert_foreign_flow_sync,
    insert_macro_metrics,
    insert_macro_metrics_sync,
    insert_market_regime,
    # sync
    insert_market_regime_sync,
    insert_sector_rotation,
    insert_sector_rotation_sync,
)

# ── Insert: Records ──────────────────────────────────────────────────────────
from .insert_records import (
    get_morning_recommendations,
    get_morning_recommendations_sync,
    insert_daily_record,
    insert_daily_record_sync,
    insert_ensemble_votes,
    insert_morning_recommendations,
    # sync
    insert_morning_recommendations_sync,
    update_previous_day_change,
    update_previous_day_change_sync,
)

# ── Insert: Scan ─────────────────────────────────────────────────────────────
from .insert_scan import (
    insert_daily_scan,
    # sync
    insert_daily_scan_sync,
)

# ── Learnings ────────────────────────────────────────────────────────────────
from .learnings import (
    get_learnings_summary,
    # sync
    get_learnings_summary_sync,
    get_losing_patterns,
    get_losing_patterns_sync,
    get_macro_patterns,
    get_macro_patterns_sync,
    get_midday_patterns,
    get_midday_patterns_sync,
    get_mode_compliance,
    get_mode_compliance_sync,
    get_rolling_performance,
    get_rotation_patterns,
    get_rotation_patterns_sync,
    get_sector_insights,
    get_sector_insights_sync,
    get_strategy_regime_stats,
    get_ticker_insights,
    get_ticker_insights_sync,
    get_winning_patterns,
    get_winning_patterns_sync,
)

# ── Longterm automation ──────────────────────────────────────────────────────
from .longterm import (
    add_longterm_stock,
    deactivate_longterm_stock,
    get_company_research,
    get_company_research_sync,
    get_longterm_watchlist_full,
    get_longterm_watchlist_full_sync,
    mark_longterm_reviewed,
    update_longterm_conviction,
    update_longterm_entry_zone,
    update_longterm_ratios,
    update_longterm_review_flags,
    upsert_company_research,
    upsert_company_research_sync,
)
from .market import (
    get_macro_history,
    get_macro_metrics,
    get_market_regime,
    get_midday_check,
    get_regime_history,
    get_sector_rotation,
)

# ── Memory (Vector Search) ──────────────────────────────────────────────────
from .memory import (
    find_applicable_rules,
    find_applicable_rules_sync,
    find_similar_days,
    # sync
    find_similar_days_sync,
    find_similar_patterns,
    find_similar_patterns_sync,
    update_daily_record_embedding,
    update_daily_record_embedding_sync,
    update_pattern_embedding,
    update_pattern_embedding_sync,
    upsert_trading_rule,
    upsert_trading_rule_sync,
)

# ── Narratives ───────────────────────────────────────────────────────────────
from .narratives import (
    add_narrative_update,
    batch_count_distinct_sources,
    get_active_narratives,
    get_all_active_with_embeddings,
    mark_dead_narratives,
    mark_stale_narratives,
    refresh_all_conviction_scores,
    refresh_narrative_maturity,
    refresh_related_catalysts,
    update_article_narrative,
    update_narrative_on_article,
    upsert_narrative,
)

# ── Portfolio ────────────────────────────────────────────────────────────────
from .portfolio import (
    HoldingsSnapshot,
    collapse_holdings_by_ticker,
    get_active_goal,
    get_active_goal_sync,
    get_active_goals,
    get_cash_balance,
    get_cash_balance_sync,
    get_holdings_with_sectors,
    get_portfolio_holdings,
    get_portfolio_holdings_snapshot,
    # sync
    get_portfolio_holdings_snapshot_sync,
    get_portfolio_holdings_sync,
    get_sector_allocations,
    get_swing_trade_stats,
    index_holdings_by_ticker_plan,
    plans_for_ticker,
    primary_swing_slice,
    ticker_total_weight_pct,
    tickers_held,
    update_goal_realized,
    update_goal_realized_sync,
    update_portfolio_prices,
    update_portfolio_prices_sync,
)
from .portfolio_trades import (
    get_recent_trades,
    get_trades_by_status,
    get_trades_for_date,
)

# ── Position Alerts (Morning → Midday Handoff) ───────────────────────────────
from .position_alerts import (
    get_morning_position_alerts,
    insert_morning_position_alerts,
    upsert_with_passthrough,
)

# ── Review (pipeline review data collection) ──────────────────────────────
from .review import (
    get_alerts_by_source_date,
    get_beliefs_for_date,
    get_daily_evaluations,
    get_orphaned_belief_chains,
)
from .watchlist import (
    add_swing_stock,
    add_swing_stock_sync,
    ensure_stock_exists,
    get_longterm_watchlist,
    get_longterm_watchlist_sync,
    get_swing_watchlist,
    # sync
    get_swing_watchlist_sync,
    get_swing_watchlist_with_rsi,
    load_all_watchlist_tickers,
    pin_swing_stock,
    pin_swing_stock_sync,
    remove_swing_stock,
    remove_swing_stock_sync,
    unpin_swing_stock,
    unpin_swing_stock_sync,
    update_swing_rsi_batch,
    update_swing_rsi_batch_sync,
)

__all__ = [
    # Types
    "AfternoonAction",
    "AfternoonActionConfidence",
    "AfternoonActionKind",
    "ClosedTradeEntry",
    "GoalData",
    "HoldingData",
    "LongtermWatchlistEntry",
    "MacroHistoryEntry",
    "MacroMetricsData",
    "MarketRegimeData",
    "MiddayBigMover",
    "MiddayCheckData",
    "MiddayEntryHit",
    "MiddayPositionAlert",
    "OpenedTradeEntry",
    "RegimeHistoryEntry",
    "RemoveStockResult",
    "SectorRotationData",
    "SwingTradeStats",
    "SwingWatchlistRsiEntry",
    "TradeData",
    "TradesForDateData",
    # Watchlist
    "get_swing_watchlist",
    "get_longterm_watchlist",
    "get_swing_watchlist_with_rsi",
    "load_all_watchlist_tickers",
    "update_swing_rsi_batch",
    "add_swing_stock",
    "remove_swing_stock",
    "pin_swing_stock",
    "unpin_swing_stock",
    "ensure_stock_exists",
    "get_swing_watchlist_sync",
    "get_longterm_watchlist_sync",
    "update_swing_rsi_batch_sync",
    "add_swing_stock_sync",
    "remove_swing_stock_sync",
    "pin_swing_stock_sync",
    "unpin_swing_stock_sync",
    # Portfolio
    "HoldingsSnapshot",
    "get_portfolio_holdings",
    "get_portfolio_holdings_snapshot",
    "get_portfolio_holdings_snapshot_sync",
    "index_holdings_by_ticker_plan",
    "collapse_holdings_by_ticker",
    "tickers_held",
    "plans_for_ticker",
    "ticker_total_weight_pct",
    "primary_swing_slice",
    "get_cash_balance",
    "update_portfolio_prices",
    "get_recent_trades",
    "get_sector_allocations",
    "get_trades_by_status",
    "get_trades_for_date",
    "get_active_goal",
    "get_active_goals",
    "update_goal_realized",
    "get_holdings_with_sectors",
    "get_portfolio_holdings_sync",
    "get_cash_balance_sync",
    "update_portfolio_prices_sync",
    "get_active_goal_sync",
    "update_goal_realized_sync",
    "get_swing_trade_stats",
    # Market
    "get_market_regime",
    "get_sector_rotation",
    "get_macro_metrics",
    "get_foreign_flow",
    "get_midday_check",
    "get_regime_history",
    "get_macro_history",
    # Articles
    "list_articles",
    "list_articles_range",
    "get_issued_query_names",
    "load_articles_for_scan_date",
    "search_articles",
    "list_articles_by_ticker",
    "read_article",
    # Learnings
    "get_learnings_summary",
    "get_winning_patterns",
    "get_losing_patterns",
    "get_sector_insights",
    "get_ticker_insights",
    "get_midday_patterns",
    "get_mode_compliance",
    "get_rotation_patterns",
    "get_macro_patterns",
    "get_strategy_regime_stats",
    "get_rolling_performance",
    "get_learnings_summary_sync",
    "get_winning_patterns_sync",
    "get_losing_patterns_sync",
    "get_sector_insights_sync",
    "get_ticker_insights_sync",
    "get_midday_patterns_sync",
    "get_mode_compliance_sync",
    "get_rotation_patterns_sync",
    "get_macro_patterns_sync",
    # Insert: Scan
    "insert_daily_scan",
    "insert_daily_scan_sync",
    # Insert: Market
    "insert_market_regime",
    "insert_macro_metrics",
    "insert_foreign_flow",
    "insert_sector_rotation",
    "insert_market_regime_sync",
    "insert_macro_metrics_sync",
    "insert_foreign_flow_sync",
    "insert_sector_rotation_sync",
    # Insert: Content
    "insert_articles",
    "insert_midday_check",
    "write_article_sentiments",
    "insert_articles_sync",
    "insert_midday_check_sync",
    # Insert: Records
    "insert_morning_recommendations",
    "insert_daily_record",
    "insert_ensemble_votes",
    "update_previous_day_change",
    "get_morning_recommendations",
    "insert_morning_recommendations_sync",
    "insert_daily_record_sync",
    "update_previous_day_change_sync",
    "get_morning_recommendations_sync",
    # Insert: Learnings
    "insert_learnings",
    "insert_learnings_sync",
    # Memory
    "find_similar_days",
    "find_similar_patterns",
    "find_applicable_rules",
    "upsert_trading_rule",
    "update_daily_record_embedding",
    "update_pattern_embedding",
    "find_similar_days_sync",
    "find_similar_patterns_sync",
    "find_applicable_rules_sync",
    "upsert_trading_rule_sync",
    "update_daily_record_embedding_sync",
    "update_pattern_embedding_sync",
    # Alerts
    "register_alert",
    "register_alerts_batch",
    "get_active_alerts",
    "trigger_alert",
    "expire_stale_alerts",
    "cancel_alerts_for_date",
    "get_alerts_for_web",
    "get_recent_trigger_times",
    "register_alert_sync",
    "get_active_alerts_sync",
    "expire_stale_alerts_sync",
    "cancel_alerts_for_date_sync",
    "get_alerts_for_web_sync",
    # Catalysts & Capital Events
    "get_active_catalysts_db",
    "upsert_catalyst",
    "complete_catalyst",
    "update_catalyst_field",
    "get_upcoming_capital_events_db",
    "upsert_capital_event",
    "link_catalyst_articles",
    "refresh_catalyst_lifecycle",
    "get_active_catalysts_db_sync",
    "get_upcoming_capital_events_db_sync",
    "upsert_catalyst_sync",
    "upsert_capital_event_sync",
    "complete_catalyst_sync",
    # Directives
    "save_strategy_directive",
    "get_strategy_directive",
    # Position Alerts
    "insert_morning_position_alerts",
    "get_morning_position_alerts",
    "upsert_with_passthrough",
    # Longterm automation
    "get_company_research",
    "upsert_company_research",
    "get_longterm_watchlist_full",
    "update_longterm_entry_zone",
    "update_longterm_conviction",
    "update_longterm_review_flags",
    "update_longterm_ratios",
    "mark_longterm_reviewed",
    "add_longterm_stock",
    "deactivate_longterm_stock",
    "get_company_research_sync",
    "upsert_company_research_sync",
    "get_longterm_watchlist_full_sync",
    # Company Profiles
    "get_company_profile",
    "get_company_profile_sync",
    "get_macro_sensitivities",
    "get_profiles_batch",
    "get_universe_with_aliases",
    "resolve_tickers_by_factors_batch",
    "upsert_company_profile",
    "upsert_company_profile_sync",
    "resolve_tickers_by_macro_factor",
    "resolve_tickers_by_macro_factor_sync",
    # Enrichment (relative strength only)
    "get_relative_strength",
    # Ensemble Vote History
    "get_ensemble_vote_history",
    "get_ensemble_vote_history_batch",
    # Narratives
    "get_active_narratives",
    "get_all_active_with_embeddings",
    "upsert_narrative",
    "add_narrative_update",
    "update_narrative_on_article",
    "refresh_all_conviction_scores",
    "refresh_narrative_maturity",
    "refresh_related_catalysts",
    "batch_count_distinct_sources",
    "mark_dead_narratives",
    "mark_stale_narratives",
    "update_article_narrative",
    # Beliefs
    "get_prior_beliefs",
    "insert_agent_beliefs",
    "get_stale_beliefs",
    "get_unresolved_beliefs",
    "resolve_beliefs",
    "tombstone_beliefs",
    "get_agent_belief_accuracy",
    "get_all_belief_accuracy",
    "get_latest_aggregated_beliefs",
    # Review (pipeline review data collection)
    "get_daily_evaluations",
    "get_beliefs_for_date",
    "get_orphaned_belief_chains",
    "get_alerts_by_source_date",
    # Utilities
    "safe_float",
    "safe_round",
]
