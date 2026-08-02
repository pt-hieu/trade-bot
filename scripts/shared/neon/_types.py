"""TypedDict definitions for neon module return types.

Provides compile-time type safety for DB query return shapes.
Consumers get pyright checking on dict key access.
"""

from typing import TYPE_CHECKING, Any, Literal, TypedDict

if TYPE_CHECKING:
    from pipeline.types import GeopoliticalShockDict


AfternoonActionKind = Literal["BUY", "HOLD", "TRIM", "EXIT", "NOTE", "CANCEL", "WATCH"]
AfternoonActionConfidence = Literal["HIGH", "MEDIUM", "LOW"]

# ============================================================================
# Watchlist types
# ============================================================================


class LongtermWatchlistEntry(TypedDict):
    """Single entry in the longterm watchlist dict (keyed by ticker)."""

    entry_zone: int
    conviction: str
    sector: str
    updated_at: str | None


class SwingWatchlistRsiEntry(TypedDict):
    """Swing watchlist entry with RSI and pin status."""

    ticker: str
    sector: str
    stock_type: str
    rsi: float | None
    is_pinned: bool


class RemoveStockResult(TypedDict):
    """Result of remove_swing_stock operation."""

    removed: bool
    pinned: bool
    reason: str


# ============================================================================
# Market types
# ============================================================================


class MarketRegimeData(TypedDict):
    """Market regime classification for a scan date."""

    regime: str
    regime_confidence: float
    key_signal: str
    recommendation: str


class SectorRotationData(TypedDict):
    """Sector rotation analysis result."""

    hot_sectors: list[str]
    cold_sectors: list[str]
    rotation_signal: str
    market_regime: str


class MacroMetricsData(TypedDict):
    """Global macro metrics from macro_metrics table."""

    dxy_value: float | None
    dxy_change_pct: float | None
    dxy_signal: str
    vix_value: float | None
    vix_change_pct: float | None
    vix_signal: str
    usd_vnd_rate: float | None
    usd_vnd_signal: str
    usd_vnd_source: str | None
    usd_vnd_spread: float | None
    global_risk_regime: str
    interpretation: str | None
    upcoming_events: list[str]
    oil_price: float | None
    oil_change_pct: float | None
    copper_price: float | None
    copper_change_pct: float | None
    us_10y_yield: float | None
    us_10y_change_pct: float | None
    shanghai_close: float | None
    shanghai_change_pct: float | None
    sp500_close: float | None
    sp500_change_pct: float | None
    nasdaq_close: float | None
    nasdaq_change_pct: float | None
    dow_close: float | None
    dow_change_pct: float | None
    breadth_advance: int | None
    breadth_decline: int | None
    breadth_ratio: float | None
    geopolitical_shock: "GeopoliticalShockDict | None"


class RegimeHistoryEntry(TypedDict):
    """Single entry in regime history list."""

    date: str
    regime: str
    confidence: float


class MiddayEntryHit(TypedDict):
    """Entry that hit its recommended price during midday check."""

    ticker: str
    recommended_entry: float | None
    actual_low: float | None
    current_price: float | None
    status: str


class MiddayBigMover(TypedDict):
    """Big mover detected during midday check."""

    ticker: str
    open_price: float | None
    current_price: float | None
    change_pct: float | None
    direction: str


class MiddayPositionAlert(TypedDict):
    """Position alert from midday check."""

    ticker: str
    current_price: float | None
    level: float | None
    level_type: str
    distance_pct: float | None
    urgency: str


class AfternoonAction(TypedDict):
    """Structured afternoon-plan action (migration 316).

    ``ticker=None`` is reserved for legacy-seeded rows and session-wide notes
    that do not target a specific ticker.
    """

    ticker: str | None
    action: AfternoonActionKind
    confidence: AfternoonActionConfidence
    reason: str


class MiddayCheckData(TypedDict):
    """Full midday check result with nested lists."""

    trading_mode: str
    morning_reflection: str
    afternoon_plan: list[AfternoonAction]
    capital_note: str
    entries_hit: list[MiddayEntryHit]
    big_movers: list[MiddayBigMover]
    position_alerts: list[MiddayPositionAlert]
    recommendation_overrides: list[Any]


class MacroHistoryEntry(TypedDict):
    """Single entry in macro history time series."""

    date: str
    global_risk_regime: str
    dxy_signal: str
    vix_signal: str
    dxy_value: float | None
    vix_value: float | None
    oil_price: float | None
    copper_price: float | None
    us_10y_yield: float | None
    shanghai_close: float | None
    usd_vnd_rate: float | None
    usd_vnd_source: str | None
    geopolitical_shock: "GeopoliticalShockDict | None"


# ============================================================================
# Portfolio types
# ============================================================================


class HoldingData(TypedDict):
    """Single portfolio slice (one row per (ticker, plan_type) pair).

    ``get_portfolio_holdings`` returns a ``list[HoldingData]`` so callers can
    see every (ticker, plan_type) slice. Dict access is available via
    ``index_holdings_by_ticker_plan`` or, for the MY HOLDINGS card pattern
    that must expose the SWING row, ``primary_swing_slice(ticker)``.
    """

    ticker: str
    plan_type: str
    shares: int
    avg_cost: int
    avg_cost_vnd: float
    type: str
    # `_vnd` suffix aligns with pipeline rendering contract
    # (pipeline/rendering/models.py reads `current_price_vnd`).
    current_price_vnd: int | None
    market_value: float
    # Per-slice weight within the total portfolio (market_value / total * 100).
    slice_weight_pct: float
    # Total weight of the ticker across all its slices (SWING + LONGTERM).
    ticker_weight_pct: float
    pct_from_entry: float | None
    breakeven_stop: int


class TradeData(TypedDict):
    """Normalized trade from trades_calculated."""

    ticker: str
    entry_date: str
    entry_price: int
    shares: int
    strategy: str
    status: str
    exit_date: str
    exit_price: int
    pl_pct: float
    plan_type: str


class OpenedTradeEntry(TypedDict):
    """Trade opened on a specific date."""

    ticker: str
    entry_price: int
    shares: int
    strategy: str
    status: str


class ClosedTradeEntry(TypedDict):
    """Trade closed on a specific date."""

    ticker: str
    exit_price: int
    shares: int
    pl_pct: float
    pl_net: int


class TradesForDateData(TypedDict):
    """Trades opened and closed on a specific date."""

    opened: list[OpenedTradeEntry]
    closed: list[ClosedTradeEntry]


class GoalData(TypedDict):
    """Active goal record."""

    id: str
    name: str
    target: int
    realized: int
    start_date: str
    deadline: str
    goal_type: str


class SwingTradeStats(TypedDict):
    """Swing trade performance statistics from v_swing_metrics."""

    total_trades: int
    win_rate: float
    expectancy_vnd: float
    avg_holding_days: float
    trades_per_month: float
