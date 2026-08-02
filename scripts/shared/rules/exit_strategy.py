"""ExitStrategy polymorphism — single source of truth for exit family dispatch.

Exit family is derived from the existing `strategy` column
(`scripts/agents/tools/strategy_classifier.py`):

    TREND, MOMENTUM, BREAKOUT        → ATRTrailExit
    MEAN_REVERSION, BOUNCE, DIVERGENCE, PULLBACK, UNCLASSIFIED → FixedTargetExit

All downstream consumers (recommendation_validator, picks, retro, midday,
alert monitor, insert_records) must route exit logic through
``resolve_exit_strategy(strategy)`` — this eliminates the per-consumer
`if strategy in {...}` branching that the prior plan would have introduced.

Price convention: every VND price in ExitState is a Python ``int``
(matches BIGINT columns). ``trail_mult`` is a float mapped to DECIMAL(4,2).
``pnl_percent`` is a whole-number percent float (42.5 == 42.5%).
"""

from __future__ import annotations

import math
from typing import ClassVar, Literal, Protocol, TypedDict, runtime_checkable

ATR_TRAIL_STRATEGIES: frozenset[str] = frozenset({"TREND", "MOMENTUM", "BREAKOUT"})

# HOSE ±7% daily band — single source of truth for the market-structure
# constant referenced by trail_sim, exit_atr_trail, alert_registrar.
HOSE_DAILY_BAND_PCT: float = 0.07

ExitFamilyName = Literal["FIXED_TARGET", "ATR_TRAIL"]
ExitStatus = Literal["WIN", "LOSS", "PENDING", "MISSED", "TRAIL_FLOOR_LOCK"]
AlertKind = Literal["TARGET_HIT", "STOP_HIT", "TRAIL_BREAK", "LIKELY_FLOOR_LOCKED"]


class ExitState(TypedDict, total=False):
    """Runtime exit state carried alongside an open/pending rec.

    Built by ``ExitStrategy.build_exit_state`` and mutated only through the
    strategy's own methods (peak updates, DB round-trips). Keys are a
    superset: FixedTargetExit reads entry/stop/target; ATRTrailExit also
    reads atr_at_entry, trail_mult, peak_price.
    """

    entry_price: int  # VND
    stop_price: int  # VND
    target_price: int | None  # VND; None for ATR_TRAIL
    atr_at_entry: int | None  # VND; required for ATR_TRAIL
    trail_mult: float | None  # e.g. 2.5
    peak_price: int | None  # VND; updated in monitor, None at registration
    # Validation-time signals. Callers populate these before rr_gate() — the
    # validator has them in hand (rec.strategy, technicals.adx, catalyst
    # boost lookup). ATRTrailExit.rr_gate consumes them; FixedTargetExit
    # ignores them and uses target_price/risk_reward only.
    strategy: str | None
    adx: float | None
    has_positive_catalyst: bool
    daily_limit_pct: float  # HOSE ±7% band = 0.07


class TrailBar(TypedDict, total=False):
    """Minimal daily OHLC shape used by evaluate_bars."""

    date: str  # ISO
    open: int  # VND
    high: int  # VND
    low: int  # VND
    close: int  # VND


class ExitEvalResult(TypedDict, total=False):
    """Outcome produced by ``ExitStrategy.evaluate_bars``."""

    entry_hit: bool
    stop_hit: bool
    target_hit: bool
    exit_price: int | None  # VND; None when still PENDING/MISSED
    status: ExitStatus
    peak_price: int | None  # VND; highest bar close during window
    pnl_percent: float | None  # whole-number percent
    days_in_trade: int | None
    suspended_days: int  # trading days missing within the window
    exit_date: str | None  # ISO, date on which exit was marked


class AlertTrigger(TypedDict):
    """Result of ``ExitStrategy.alert_condition`` when the rec should fire."""

    kind: AlertKind
    level_price: int  # VND — the price at which the trigger armed
    rationale: str


@runtime_checkable
class ExitStrategy(Protocol):
    """Polymorphic exit interface — one implementation per exit family."""

    # Implementations expose this as ClassVar[ExitFamilyName]. Declared here
    # with the same union so the Protocol matches the implementations.
    name: ClassVar[ExitFamilyName]

    def build_exit_state(
        self,
        levels: dict,
        close: int,
        atr: int | None,
        regime: str | None,
    ) -> ExitState:
        """Construct ExitState from pre-computed levels + regime.

        For FixedTargetExit, produces entry/stop/target.
        For ATRTrailExit, produces entry/stop/atr_at_entry/trail_mult with
        target_price=None.
        """
        ...

    def evaluate_bars(
        self,
        state: ExitState,
        bars: list[TrailBar],
        entry_date: str,
    ) -> ExitEvalResult:
        """Drive the rec through the given bar stream and return outcome.

        FIXED_TARGET: same-day single-EOD binary check (wraps single bar).
        ATR_TRAIL: iterates bars updating peak, exits on trail break or
        hard stop, handles HOSE ±7% floor-lock and trading suspensions.
        """
        ...

    def alert_condition(
        self,
        state: ExitState,
        current_price: int,
        prev_close: int,
    ) -> AlertTrigger | None:
        """Per-poll evaluation for the Lightsail alert monitor.

        Returns None when no action; otherwise an AlertTrigger describing
        the kind of break detected. The monitor is responsible for
        persisting any peak update the strategy performed on state.
        """
        ...

    def rr_gate(self, state: ExitState, rr_floor: float) -> bool:
        """Validator gate — True = pass, False = drop.

        FIXED_TARGET compares net-of-cost R:R against ``rr_floor``.
        ATR_TRAIL ignores rr_floor and checks structural signals
        (ADX>25 OR positive catalyst OR strategy=BREAKOUT) plus loss cap.
        """
        ...

    def exit_description(self, state: ExitState) -> str | None:
        """Pre-rendered single-line description, or None when state is insufficient.

        Example FIXED_TARGET: 'Target 72.5k (R:R 3.1)'
        Example ATR_TRAIL:    'Trail 2.5x ATR from peak (hard stop 60.0k)'
        """
        ...

    def to_db_row(self, state: ExitState) -> dict[str, int | float | None]:
        """Return a dict of DB column names → values for INSERT merge.

        Keys: entry_price_vnd, stop_price_vnd, target_price_vnd,
              atr_at_entry_vnd, trail_mult. Missing-meaningful-None fields
              are emitted so callers can .update() into the row dict.
        """
        ...


# Singleton cache populated on first dispatch — breaks circular import with
# exit_atr_trail / exit_fixed_target (both import from this module).
_SINGLETONS: dict[str, ExitStrategy] = {}


def resolve_exit_strategy(strategy: str | None) -> ExitStrategy:
    """Dispatch — single source of truth for exit family selection.

    Accepts None/empty (e.g. legacy recs) → FixedTargetExit for safety.
    Returns cached singletons; callers may mutate ExitState but must not
    mutate the strategy instance itself.
    """
    family: ExitFamilyName = (
        "ATR_TRAIL" if strategy and strategy.upper() in ATR_TRAIL_STRATEGIES else "FIXED_TARGET"
    )
    cached = _SINGLETONS.get(family)
    if cached is not None:
        return cached
    if family == "ATR_TRAIL":
        from .exit_atr_trail import ATRTrailExit

        cached = ATRTrailExit()
    else:
        from .exit_fixed_target import FixedTargetExit

        cached = FixedTargetExit()
    _SINGLETONS[family] = cached
    return cached


def is_trailing_exit(pick_or_rec: dict) -> bool:
    """True when the pick/rec uses the ATR_TRAIL family (no fixed target / R:R).

    Single source of truth for downstream readers (alert builders, brief
    composers, entry strategist) so they branch identically. Trailing picks
    legitimately carry ``target=None`` and ``risk_reward=None`` end-to-end.
    """
    family = pick_or_rec.get("exit_family") or "FIXED_TARGET"
    return family == "ATR_TRAIL" or pick_or_rec.get("target") is None


def exit_state_from_rec(rec: dict) -> ExitState:
    """Materialize an ExitState from a persisted rec or pre-insert pick.

    Prefers a pre-computed ``rec["exit_state"]`` when present (picks.py
    attaches it) — falls back to reading top-level DB columns. None-safe
    per CLAUDE.md.
    """
    nested = rec.get("exit_state")
    if isinstance(nested, dict):
        rec = {**nested, **rec, **nested}  # nested wins for exit-specific keys
    state: ExitState = {
        "entry_price": int(rec.get("entry_price") or rec.get("entry_price_vnd") or 0),
        "stop_price": int(rec.get("stop_price") or rec.get("stop_price_vnd") or 0),
    }
    target = rec.get("target_price") or rec.get("target_price_vnd")
    state["target_price"] = int(target) if target else None
    atr = rec.get("atr_at_entry") or rec.get("atr_at_entry_vnd")
    state["atr_at_entry"] = int(atr) if atr else None
    trail_mult = rec.get("trail_mult")
    state["trail_mult"] = float(trail_mult) if trail_mult is not None else None
    peak = rec.get("peak_price") or rec.get("trail_peak_vnd")
    state["peak_price"] = int(peak) if peak else None
    state["strategy"] = rec.get("strategy")
    adx = rec.get("adx")
    state["adx"] = float(adx) if adx is not None else None
    state["has_positive_catalyst"] = bool(rec.get("has_positive_catalyst"))
    state["daily_limit_pct"] = float(rec.get("daily_limit_pct") or HOSE_DAILY_BAND_PCT)
    return state


SYNTHETIC_TARGET_ATR_MULT: float = 2.0
SYNTHETIC_RR_RISK_CAP: float = 4.0


def derive_atr_trail_synthetic_target(*, entry: int, atr: int | None) -> int:
    """ATR_TRAIL synthetic target = entry + max(1, SYNTHETIC_TARGET_ATR_MULT*ATR).

    Pure exit-math helper — no scoring concerns. Consumed by the simulator
    (picks.py) and the audit RR helper below. Never written back to
    ``setup`` — SWI-115 preserves ``setup["target"]=None`` end-to-end.
    """
    atr_safe = int(atr or 0)
    return entry + max(1, int(SYNTHETIC_TARGET_ATR_MULT * atr_safe))


def derive_atr_trail_synthetic_rr(*, entry: int | None, stop: int | None, atr: int | None) -> float:
    """Synthetic R:R for ATR_TRAIL audit scoring only. NOT written back to setup.

    Caps the reward at ``SYNTHETIC_RR_RISK_CAP * risk`` so the scorer
    contribution stays inside the sqrt(rr/10) normalizer sweet-spot
    (SWI-175). The cap lives here, not in the target helper, because
    "stay in normalizer sweet-spot" is a scoring concern; the simulator
    wants the uncapped target for unbiased p_target estimation.

    Fail-loud-by-zeroing: if entry/stop are missing/invalid (entry<=stop) or
    the derived rr is NaN/Inf, returns 0.0 — the scoring normalizer maps
    rr<=0 to a 0 contribution.
    """
    if entry is None or stop is None or entry <= 0 or stop <= 0 or entry <= stop:
        return 0.0
    target = derive_atr_trail_synthetic_target(entry=int(entry), atr=atr)
    risk = entry - stop
    capped_reward = min(target - entry, int(SYNTHETIC_RR_RISK_CAP * risk))
    rr = capped_reward / risk
    if math.isnan(rr) or math.isinf(rr):
        return 0.0
    return float(rr)


def read_rr(rec_or_pick: dict) -> float | None:
    """SSOT reader for ``risk_reward``. Returns None for trailing exits; never
    coerces to 0.0. Callers must branch on None. Enforced by pre-push grep
    guard scripts/hooks/check_risk_reward_readers.py — see hook for history.
    """
    if is_trailing_exit(rec_or_pick):
        return None
    raw = rec_or_pick.get("risk_reward")
    if raw is None:
        return None
    return float(raw)


def format_rr_display(rr: float | None, *, precision: int = 1, suffix: str = "") -> str:
    """SSOT formatter for R:R values that may be None (trailing exits).

    Returns ``"trailing"`` for None; otherwise ``f"{rr:.{precision}f}{suffix}"``.
    Use ``suffix=":1"`` to render verdict-style ``"3.5:1"``.
    """
    if rr is None:
        return "trailing"
    return f"{rr:.{precision}f}{suffix}"


def rr_sort_weight(rec_or_pick: dict, *, descending: bool = True) -> float:
    """SSOT sort key for picks that may be trailing (read_rr → None).

    Trailing picks rank as max-bound (unbounded upside; should never sort
    last after the historic ``or 0.0`` coercion that put them at the bottom).
    With ``descending=True`` (sorted ascending = highest first), trailing
    sorts FIRST via -inf; with ``descending=False`` (max(...) selection),
    trailing sorts FIRST via +inf.
    """
    rr = read_rr(rec_or_pick)
    if rr is None:
        return -float("inf") if descending else float("inf")
    return -float(rr) if descending else float(rr)


StopType = Literal[
    "thesis_based",
    "catastrophic",
    "breakeven",
    "breakeven_floor",
    "trailing_50pct",
    "trailing_tight",
    "technical",
]
"""Closed set of trailing_stops.stop_type values. Mirrors compute_trailing_stop
returns + the alert registrar's critical-stops set. Add new values here and
update consumers atomically."""

CRITICAL_STOP_TYPES: frozenset[StopType] = frozenset({"catastrophic", "breakeven_floor"})
"""Stop types that bypass the 7%-band guard in alert registration — both are
cost-basis-anchored catastrophic floors. SWI-157."""


__all__ = [
    "ATR_TRAIL_STRATEGIES",
    "AlertKind",
    "AlertTrigger",
    "CRITICAL_STOP_TYPES",
    "ExitEvalResult",
    "ExitFamilyName",
    "ExitState",
    "ExitStatus",
    "ExitStrategy",
    "HOSE_DAILY_BAND_PCT",
    "StopType",
    "TrailBar",
    "derive_atr_trail_synthetic_rr",
    "derive_atr_trail_synthetic_target",
    "exit_state_from_rec",
    "format_rr_display",
    "is_trailing_exit",
    "read_rr",
    "resolve_exit_strategy",
    "rr_sort_weight",
]
