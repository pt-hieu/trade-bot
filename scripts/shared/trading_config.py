"""
Trading configuration loader — fetches all trading constraints from Neon DB.

Mirrors the pattern of shared/agent_config.py:
- Single-row `trading_config` table is the source of truth
- Loaded once at pipeline startup via init_trading_config()
- Accessed sync via get_trading_config() (requires prior init)

Usage:
    # At pipeline startup (inside async with Database():)
    await init_trading_config()

    # Anywhere in sync or async code afterward:
    cfg = get_trading_config()
    reserve = cfg.min_cash_reserve
"""

from dataclasses import dataclass

from shared.database import fetch_one


@dataclass(frozen=True)
class TradingConfig:
    """All trading constraints from the trading_config DB table."""

    # ── Core Risk ────────────────────────────────────────────────────────────
    # Placeholder defaults. Live values come from the trading_config table — set
    # them there for your own account size and risk tolerance.
    min_cash_reserve: int = 10_000_000  # VND held back, never deployed
    max_risk_per_trade: int = 200_000  # VND at risk per position
    low_cash_threshold: int = 5_000_000  # below this → LOW_CASH mode
    max_concurrent_positions: int = 3
    transaction_cost_pct: float = 0.003  # 0.3% round-trip
    monthly_contribution: int = 10_000_000  # VND added per month

    # ── Concentration Limits ─────────────────────────────────────────────────
    concentration_exit_pct: float = 60.0  # any plan >60% weight → EXIT
    swing_trim_weight_pct: float = 40.0  # swing weight >40% → TRIM
    swing_trim_gain_pct: float = 15.0  # swing gain >15% → TRIM
    longterm_trim_weight_high_pct: float = 55.0  # longterm >55% → TRIM (high urgency)
    longterm_trim_weight_med_pct: float = 45.0  # longterm >45% → TRIM (med urgency)
    longterm_review_weight_pct: float = 30.0  # informational review threshold
    sector_concentration_high_pct: float = 60.0  # >60% same cluster → HIGH
    sector_concentration_med_pct: float = 40.0  # >40% same cluster → MEDIUM

    # ── Max Loss Ceiling ────────────────────────────────────────────────────
    swing_max_loss_pct: float = 7.0  # >7% loss from entry → forced EXIT for SWING

    # ── Trailing Stops (SWING) ───────────────────────────────────────────────
    breakeven_gain_pct: float = 10.0  # up to 10% gain → breakeven stop
    half_trail_gain_pct: float = 15.0  # 10–15% gain → 50% trail
    tight_trail_gain_pct: float = 15.0  # >15% gain → tight trail
    tight_current_floor_pct: float = 95.0  # floor = current * (tight_current_floor_pct / 100)
    tight_gain_lock_pct: float = 75.0  # stop = entry + gain * (tight_gain_lock_pct / 100)
    longterm_catastrophic_pct: float = 20.0  # longterm floor = entry * (1 - pct/100)

    # ── Win Rate Position Scale ──────────────────────────────────────────────
    full_winrate_threshold: float = 50.0  # win_rate >= 50% → 1.0x sizing
    reduced_winrate_threshold: float = 35.0  # win_rate >= 35% → 0.75x sizing
    half_winrate_threshold: float = 20.0  # win_rate >= 20% → 0.5x sizing
    minimal_scale_factor: float = 0.25  # win_rate < 20% → 0.25x sizing

    # ── Retro Constraints ────────────────────────────────────────────────────
    retro_severe_winrate: float = 35.0  # below this → severe entry cap
    retro_moderate_winrate: float = 45.0  # below this → moderate entry cap
    retro_severe_max_entries: int = 1  # max entries at severe level
    retro_severe_min_rr: float = 4.0  # min R:R required at severe level
    retro_severe_scale: float = 0.5  # position scale override at severe level
    retro_moderate_max_entries: int = 2  # max entries at moderate level
    retro_moderate_min_rr: float = 3.5  # min R:R required at moderate level

    # ── Retro Evaluation ─────────────────────────────────────────────────────
    hold_loss_threshold_pct: float = 2.0  # HOLD wins if day_change >= -threshold (VN vol ~2-3%)
    max_entry_gap_pct: float = 3.0  # max gap (%) before pullback entry tier activates

    # ── Rally Readmit (SWI-304) ──────────────────────────────────────────────
    rally_readmit_ret_5d_min: float = 0.05  # min 5-day return for rally-volume readmit
    rally_readmit_vol_ratio_min: float = 1.5  # min 20-day volume ratio
    rally_readmit_daily_cap: int = 5  # max tickers re-admitted per day
    # ── Rally Readmit — new-ticker path (SWI-322) ───────────────────────────
    rally_readmit_new_ticker_ret_5d_min: float = 0.08  # stricter ret_5d for brand-new tickers
    rally_readmit_new_ticker_vol_ratio_min: float = 2.0  # stricter vol_ratio for brand-new tickers

    # ── Quantitative Screening ───────────────────────────────────────────────
    screen_max_pe: float = 20.0  # max P/E ratio for BUY candidates
    screen_max_pb: float = 2.5  # max P/B ratio
    screen_min_roe_pct: float = 10.0  # min ROE (percentage points, e.g. 10.0 = 10%)
    screen_min_margin_pct: float = 5.0  # min net margin (percentage points)
    screen_max_de: float = (
        1.5  # max debt/equity — sector overrides replace the old bank-only frozenset
    )
    screen_missing_data_policy: str = "pass"  # 'pass' = allow if no data, 'fail' = reject
    screen_min_core_ratio: float = 0.4  # min core earnings ratio (core profit / net income)
    screen_tolerance_pct: float = 0.10  # per-metric soft-fail band (±10% around threshold)
    screen_composite_limit: float = 1.00  # sum-of-per-metric scores cap (0=pass, 1=soft, 2=hard)


_config: TradingConfig | None = None

_SQL = """
    SELECT
        min_cash_reserve, max_risk_per_trade, low_cash_threshold,
        max_concurrent_positions, transaction_cost_pct, monthly_contribution,
        swing_max_loss_pct,
        concentration_exit_pct, swing_trim_weight_pct, swing_trim_gain_pct,
        longterm_trim_weight_high_pct, longterm_trim_weight_med_pct,
        longterm_review_weight_pct, sector_concentration_high_pct,
        sector_concentration_med_pct, breakeven_gain_pct, half_trail_gain_pct,
        tight_trail_gain_pct, tight_current_floor_pct, tight_gain_lock_pct,
        longterm_catastrophic_pct, full_winrate_threshold, reduced_winrate_threshold,
        half_winrate_threshold, minimal_scale_factor,
        retro_severe_winrate, retro_moderate_winrate,
        retro_severe_max_entries, retro_severe_min_rr, retro_severe_scale,
        retro_moderate_max_entries, retro_moderate_min_rr,
        screen_max_pe, screen_max_pb, screen_min_roe_pct, screen_min_margin_pct,
        screen_max_de, screen_missing_data_policy, screen_min_core_ratio,
        screen_tolerance_pct, screen_composite_limit,
        hold_loss_threshold_pct, max_entry_gap_pct,
        rally_readmit_ret_5d_min, rally_readmit_vol_ratio_min, rally_readmit_daily_cap,
        rally_readmit_new_ticker_ret_5d_min, rally_readmit_new_ticker_vol_ratio_min
    FROM trading_config
    LIMIT 1
"""


async def init_trading_config() -> TradingConfig:
    """Load trading config from DB and cache for this process.

    Call once at pipeline startup inside `async with Database():`.
    Subsequent calls return the cached value without querying the DB.
    """
    global _config
    if _config is not None:
        return _config

    row = await fetch_one(_SQL)
    if row:
        _config = TradingConfig(
            min_cash_reserve=int(row["min_cash_reserve"]),
            max_risk_per_trade=int(row["max_risk_per_trade"]),
            low_cash_threshold=int(row["low_cash_threshold"]),
            max_concurrent_positions=int(row["max_concurrent_positions"]),
            transaction_cost_pct=float(row["transaction_cost_pct"]),
            monthly_contribution=int(row["monthly_contribution"]),
            swing_max_loss_pct=float(row["swing_max_loss_pct"])
            if row.get("swing_max_loss_pct") is not None
            else 7.0,
            concentration_exit_pct=float(row["concentration_exit_pct"]),
            swing_trim_weight_pct=float(row["swing_trim_weight_pct"]),
            swing_trim_gain_pct=float(row["swing_trim_gain_pct"]),
            longterm_trim_weight_high_pct=float(row["longterm_trim_weight_high_pct"]),
            longterm_trim_weight_med_pct=float(row["longterm_trim_weight_med_pct"]),
            longterm_review_weight_pct=float(row["longterm_review_weight_pct"]),
            sector_concentration_high_pct=float(row["sector_concentration_high_pct"]),
            sector_concentration_med_pct=float(row["sector_concentration_med_pct"]),
            breakeven_gain_pct=float(row["breakeven_gain_pct"]),
            half_trail_gain_pct=float(row["half_trail_gain_pct"]),
            tight_trail_gain_pct=float(row["tight_trail_gain_pct"]),
            tight_current_floor_pct=float(row["tight_current_floor_pct"]),
            tight_gain_lock_pct=float(row["tight_gain_lock_pct"]),
            longterm_catastrophic_pct=float(row["longterm_catastrophic_pct"]),
            full_winrate_threshold=float(row["full_winrate_threshold"]),
            reduced_winrate_threshold=float(row["reduced_winrate_threshold"]),
            half_winrate_threshold=float(row["half_winrate_threshold"]),
            minimal_scale_factor=float(row["minimal_scale_factor"]),
            retro_severe_winrate=float(row["retro_severe_winrate"]),
            retro_moderate_winrate=float(row["retro_moderate_winrate"]),
            retro_severe_max_entries=int(row["retro_severe_max_entries"]),
            retro_severe_min_rr=float(row["retro_severe_min_rr"]),
            retro_severe_scale=float(row["retro_severe_scale"]),
            retro_moderate_max_entries=int(row["retro_moderate_max_entries"]),
            retro_moderate_min_rr=float(row["retro_moderate_min_rr"]),
            screen_max_pe=float(row["screen_max_pe"]) if row["screen_max_pe"] is not None else 20.0,
            screen_max_pb=float(row["screen_max_pb"]) if row["screen_max_pb"] is not None else 2.5,
            screen_min_roe_pct=float(row["screen_min_roe_pct"])
            if row["screen_min_roe_pct"] is not None
            else 10.0,
            screen_min_margin_pct=float(row["screen_min_margin_pct"])
            if row["screen_min_margin_pct"] is not None
            else 5.0,
            screen_max_de=float(row["screen_max_de"]) if row["screen_max_de"] is not None else 1.5,
            screen_missing_data_policy=str(row["screen_missing_data_policy"])
            if row["screen_missing_data_policy"]
            else "pass",
            screen_min_core_ratio=float(row["screen_min_core_ratio"])
            if row.get("screen_min_core_ratio") is not None
            else 0.4,
            screen_tolerance_pct=float(row["screen_tolerance_pct"])
            if row.get("screen_tolerance_pct") is not None
            else 0.10,
            screen_composite_limit=float(row["screen_composite_limit"])
            if row.get("screen_composite_limit") is not None
            else 1.00,
            hold_loss_threshold_pct=float(row["hold_loss_threshold_pct"])
            if row.get("hold_loss_threshold_pct") is not None
            else 2.0,
            max_entry_gap_pct=float(row["max_entry_gap_pct"])
            if row.get("max_entry_gap_pct") is not None
            else 3.0,
            rally_readmit_ret_5d_min=float(row["rally_readmit_ret_5d_min"])
            if row.get("rally_readmit_ret_5d_min") is not None
            else 0.05,
            rally_readmit_vol_ratio_min=float(row["rally_readmit_vol_ratio_min"])
            if row.get("rally_readmit_vol_ratio_min") is not None
            else 1.5,
            rally_readmit_daily_cap=int(row["rally_readmit_daily_cap"])
            if row.get("rally_readmit_daily_cap") is not None
            else 5,
            rally_readmit_new_ticker_ret_5d_min=float(row["rally_readmit_new_ticker_ret_5d_min"])
            if row.get("rally_readmit_new_ticker_ret_5d_min") is not None
            else TradingConfig.rally_readmit_new_ticker_ret_5d_min,
            rally_readmit_new_ticker_vol_ratio_min=float(
                row["rally_readmit_new_ticker_vol_ratio_min"]
            )
            if row.get("rally_readmit_new_ticker_vol_ratio_min") is not None
            else TradingConfig.rally_readmit_new_ticker_vol_ratio_min,
        )
    else:
        # Table exists but no row — use defaults (safe for dev)
        _config = TradingConfig()

    return _config


def get_trading_config() -> TradingConfig:
    """Return cached TradingConfig. Raises if init_trading_config() not called first."""
    if _config is None:
        raise RuntimeError(
            "Trading config not initialized. "
            "Call `await init_trading_config()` at pipeline startup."
        )
    return _config


def clear_trading_config_cache() -> None:
    """Clear cached config — for testing or hot-reload."""
    global _config
    _config = None
