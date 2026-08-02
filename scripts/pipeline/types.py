"""Typed dataclasses for pipeline phase results.

Replaces ad-hoc dict returns with structured types for attribute
access safety and IDE autocompletion.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

if TYPE_CHECKING:
    from eval.score_recorder import ScoreRecorder
    from pipeline.enrichment_loader import EnrichmentData
    from shared.rules.catalyst_override import CatalystBoost, CatalystInput
    from shared.rules.constraints import PipelineConstraints
    from shared.rules.recommendation_gate import RecommendationGateDecision
    from shared.rules.trend_momentum import MomentumSignals


class RehydratedArticle(TypedDict):
    """Article shape returned by ``shared.neon.articles.load_articles_for_scan_date``.

    Consumers: ``news_pipeline_v2._run_pipeline`` and
    ``pipeline.news_v2_persist.run_news_v2_pass``. ``id`` is non-Optional —
    Stage 1 verdict UPDATEs key on it; an absent id silently no-ops.
    """

    id: str
    url: str
    title: str | None
    summary: str | None
    domain: str | None
    summary_length: int | None
    description: str | None
    published_at: datetime | None
    query_name: str


# ── Geopolitical shock + catalyst phase contracts ────────────────────────
#
# Foundation for preventing silent field drops between agents and persistence.
# macro.py and catalysts.py return-site branches must all be assignable to
# these types — pyright enforces field parity at compile time.


class FlatTechnicalsRow(TypedDict, total=False):
    """Canonical flat shape returned by `shared.api.technicals.get_technicals()`.

    Flattening happens in `_flatten_row` before the dict is handed to consumers.
    `supertrend` → `supertrend_direction` (str), `adx` dict → `adx`/`adx_dmp`/
    `adx_dmn` scalars. `bbands`/`stoch` are dropped. Every consumer of
    `get_technicals()` reads this shape — callers of the raw vnstock client
    (`fetch_technicals_batch`) still see the nested shape and must not be
    mixed with this type.

    `total=False` because the partial-success contract allows missing fields
    per ticker (vnstock may not return every indicator for every symbol).
    """

    ticker: str
    rsi: float | None
    rsi_series: list[float] | None
    ma20: int | None
    ma50: int | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    macd_histogram_series: list[float] | None
    atr: float | None
    adx: float | None
    adx_dmp: float | None
    adx_dmn: float | None
    adx_series: list[float] | None
    supertrend_direction: str | None
    momentum_signals: MomentumSignals | None
    close: int | None
    open: int | None
    high: int | None
    low: int | None
    volume: int | None
    volume_context: dict | None
    levels: dict | None
    pattern: str | dict | None
    trend: str | dict | None
    analysis: str | None
    closed_at_low: bool | None
    volume_vs_avg: float | None
    rs_20d: float | None
    price_vs_ma20: str | None
    price_vs_ma50: str | None
    data_date: str | None
    trade_setup: dict | None
    prose: str
    price_action: dict | None
    change_pct: float | None
    error: str


PhaseImpact = Literal["POSITIVE", "NEGATIVE", "NEUTRAL"]

# CatalystFactor — structured macro-factor keys for the geo-exposure
# aggregator. Mirrors the DB CHECK constraint `catalysts_factors_allowed`
# on `catalysts.catalyst_factors` (migration 322). Hosted here so
# `pipeline.types.GeopoliticalShockDict` can reference it without
# importing from the agent layer (avoid pipeline → agents cycle).
CatalystFactor = Literal[
    "oil_price",
    "usd_vnd",
    "dxy",
    "vix",
    "rates",
    "global_risk",
]


class PhaseEntry(TypedDict):
    """One entry inside a catalyst `phases` dict."""

    period: str
    impact: PhaseImpact
    behavior: str


class CatalystPhases(TypedDict, total=False):
    """Structured phases for a geopolitical catalyst.

    All keys optional — a catalyst may only define the phases it currently has.
    """

    immediate_shock: PhaseEntry
    sustained_pressure: PhaseEntry
    resolution_or_escalation: PhaseEntry


class GeopoliticalShockDict(TypedDict):
    """The dict returned by `get_active_geopolitical_shock()`.

    Produced by `scripts/shared/neon/catalyst_summaries.py:get_active_geopolitical_shock`.
    Injected via Phase 0 pre-fetch into `fetch_macro_metrics`, embedded verbatim in
    `MacroMetricsOutput.geopolitical_shock`.
    """

    phase_name: str
    catalyst_event: str
    behavior: str
    impact: str
    affected_tickers: list[str]
    notes: str
    catalyst_key: str | None
    days_active: int
    phase_stale: bool
    # Fix 2 (2026-04-21): the catalyst's structured factor list. Empty list
    # signals no macro-factor stress attached; the geo-exposure aggregator
    # then falls back to `affected_tickers`-only labelling.
    catalyst_factors: list[CatalystFactor]


MacroDataQuality = Literal["OK", "STALE", "DEGRADED", "ERROR", "HEALTHY"]


class MacroMetricsOutput(TypedDict, total=False):
    """Contract between `fetch_macro_metrics()` and Phase 1 consumers.

    All 3 return branches (happy, STALE, DEGRADED, exception) must construct a
    value assignable to this type. pyright fails the build if any branch drops
    `geopolitical_shock` or `global_risk_regime`.

    `total=False` because the happy path includes additional informational fields
    (sp500_*, breadth_*, etc.) and we want pyright to flag missing required fields
    on the branches that build partial dicts.
    """

    # Required — every branch must populate these
    date: str
    dxy_value: float
    dxy_change_pct: float
    dxy_signal: str
    vix_value: float
    vix_change_pct: float
    vix_signal: str
    usd_vnd_rate: float
    usd_vnd_signal: str
    global_risk_regime: str
    interpretation: str
    geopolitical_shock: GeopoliticalShockDict | None
    data_quality: MacroDataQuality

    # Optional extras — present on happy path, may be absent on fail-closed branches
    usd_vnd_source: NotRequired[str]
    usd_vnd_spread: NotRequired[float | None]
    scan_date: NotRequired[str]
    error: NotRequired[str]
    oil_price: NotRequired[float | None]
    oil_change_pct: NotRequired[float | None]
    oil_signal: NotRequired[str]
    copper_price: NotRequired[float | None]
    copper_change_pct: NotRequired[float | None]
    us_10y_yield: NotRequired[float | None]
    us_10y_change_pct: NotRequired[float | None]
    shanghai_close: NotRequired[float | None]
    shanghai_change_pct: NotRequired[float | None]
    sp500_close: NotRequired[float | None]
    sp500_change_pct: NotRequired[float | None]
    nasdaq_close: NotRequired[float | None]
    nasdaq_change_pct: NotRequired[float | None]
    dow_close: NotRequired[float | None]
    dow_change_pct: NotRequired[float | None]
    breadth_advance: NotRequired[int | None]
    breadth_decline: NotRequired[int | None]
    breadth_ratio: NotRequired[float | None]
    upcoming_events: NotRequired[list[str]]
    regime_adjustments: NotRequired[list[str]]  # L1 post-merge audit: local VN override rules fired


class DeterministicBeliefs(TypedDict, total=False):
    """Inter-phase contract for Phase 2.5 deterministic belief output.

    Produced by `pipeline.phase_beliefs.post_process_beliefs`, consumed by
    Phase 3b (top picks), Phase 3.5 (advocates), Phase 6 (recommendations +
    coverage-gap reconciliation, T05). Missing keys are treated as empty.
    """

    sector: list[dict]
    positions: list[dict]
    calibration_stats: dict[str, dict]


@dataclass
class PipelineContext:
    """Database context loaded before pipeline starts."""

    sectors: dict[str, list[str]] = field(default_factory=dict)
    longterm_watchlist: dict = field(default_factory=dict)
    # One entry per (ticker, plan_type) slice (HoldingData-shaped at runtime).
    # Consumers that need dict-by-ticker access route through
    # ``collapse_holdings_by_ticker`` (SWING-preferred) or
    # ``index_holdings_by_ticker_plan``. Typed ``list[dict]`` because
    # list-invariance + TypedDict makes ``list[HoldingData]`` non-assignable
    # to ``list[dict]`` at call sites downstream.
    holdings: list[dict] = field(default_factory=list)
    # SWI-121: freshest ``updated_at`` from portfolio_holdings at load time.
    # Threaded through to MY HOLDINGS / portfolio block as the "Prices last
    # written" header. ``None`` when the load path skipped the snapshot
    # fetch — renderers must default-tolerate.
    holdings_snapshot_at: datetime | None = None
    cash_balance: float = 0.0
    deployable_cash: float = 0.0
    enrichment: EnrichmentData | None = None
    # Catalyst-boosted tickers, computed once in Phase 0 via
    # get_catalyst_boosted_tickers(). None signals fetch failure (fail-closed);
    # {} signals fetch succeeded but no eligible boosts. Consumers must handle
    # None with the none-safe pattern: `ctx.catalyst_boosted or {}`.
    catalyst_boosted: dict[str, CatalystBoost] | None = None
    # Active catalyst list (typed) fetched once in Phase 0 so the geo_label
    # aggregator and downstream briefings can count stacked-positive catalysts
    # per ticker without re-querying. Fail-closed: None on fetch failure.
    # Per-ticker geo labels are computed lazily inside `format_ticker_briefings`
    # (one pass per sector call) — caching on the context object was rejected
    # as duplicate state that's trivially derivable from this list + shock.
    active_catalysts: list[CatalystInput] | None = None
    # SWI-171 Phase A: per-pipeline-run score audit recorder. Populated at
    # pipeline startup (daily_scan.py / phase_orchestration.py) so phase_picks
    # and phase_recommendations can write `pre_gate_candidates` rows. None
    # outside the morning/midday/retro pipelines (e.g. ad-hoc CLI scripts).
    score_recorder: ScoreRecorder | None = None

    @property
    def holdings_tickers(self) -> list[str]:
        if not self.holdings:
            return []
        seen: list[str] = []
        for slice_row in self.holdings:
            ticker = slice_row.get("ticker")
            if ticker and ticker not in seen:
                seen.append(ticker)
        return seen


@dataclass
class InjectedContext:
    """Pre-formatted context strings injected into Phase 3d+ agent prompts."""

    portfolio_context: str = ""
    catalyst_context: str = ""
    catalyst_boost_context: str = ""
    articles_context: str = ""
    geopolitical_context: str = ""
    trailing_stops_context: str = ""
    regime_context: str = ""
    macro_interpretation: str = ""
    commodity_context: str = ""
    vn_economy_context: str = ""
    # Inject-instead-of-tool fields (audit cleanup)
    recent_trades: str = ""
    learnings_formatted: dict[str, str] = field(default_factory=dict)
    memory_context: str = ""


@dataclass
class PhaseHealth:
    """Health assessment for a pipeline phase."""

    total_agents: int
    failed_agents: int
    failed_names: list[str] = field(default_factory=list)
    # When set to ``"aggregator_only"`` (Phase 2 only, set in
    # phase_parallel.py when ``should_force_aggregator_only`` returns
    # True), downstream picks must drop sector_signals and rely on the
    # belief-fallback / aggregator path. None on a healthy pipeline.
    degraded_mode: str | None = None

    @property
    def failure_rate(self) -> float:
        return self.failed_agents / max(self.total_agents, 1)

    @property
    def is_degraded(self) -> bool:
        """True if >50% of agents failed."""
        return self.failure_rate > 0.5

    @property
    def is_total_failure(self) -> bool:
        """True if ALL agents failed."""
        return self.failed_agents >= self.total_agents and self.total_agents > 0


@dataclass
class PhaseIntermediates:
    """Typed intermediates derived from Phase 1 output, consumed by Phase 3+.

    Single source of truth for both live and resume paths.
    Both paths call derive_intermediates() to produce this.
    """

    market_regime: str = "CAUTIOUS"
    global_risk_regime: str = "CAUTIOUS"
    entries_allowed: bool = False
    entries_blocked_reason: str | None = None
    early_mode: str = "NORMAL"
    sector_rotation: dict | None = None
    trailing_stops_context: str = ""
    geopolitical_context: str = ""
    technicals: dict = field(default_factory=dict)
    # Fail-closed: `None` signals "composer hasn't run yet" — consumers
    # must treat that as MOST CONSERVATIVE. Populated in derive_intermediates
    # (live path) and the resume path so both routes produce identical state.
    gate_decision: RecommendationGateDecision | None = None
    # Cached to avoid a second `get_streak_alert` round-trip in the banner
    # renderer. Set alongside gate_decision.
    streak_alert: dict | None = None


@dataclass
class Phase3Result:
    """Output from Phase 3: Trading Mode determination."""

    trading_mode: dict = field(default_factory=dict)

    @property
    def mode_str(self) -> str:
        """Extract trading mode string, defaulting to NORMAL."""
        if isinstance(self.trading_mode, dict):
            return self.trading_mode.get("mode") or "NORMAL"
        return "NORMAL"


@dataclass
class Phase3aResult:
    """Output from Phase 3a: Pipeline Constraints."""

    pipeline_constraints: PipelineConstraints = field(default_factory=dict)  # type: ignore[assignment]
    goals: list[dict] = field(default_factory=list)
    cash_dict: dict = field(default_factory=dict)
    composed_min_rr: float = 2.5
    composed_max_picks: int = 3
    expectancy_floor: float | None = None
    rolling_win_rate: float | None = None


@dataclass
class Phase3bResult:
    """Output from Phase 3b: Pre-computed top picks."""

    pre_computed_picks: list[dict] = field(default_factory=list)


@dataclass
class AdvocateResult:
    """Output from Phase 3.5+3.6: Advocate reviews + gate filtering."""

    advocate_reviews: dict = field(default_factory=lambda: {"bull": [], "bear": []})
    filtered_picks: list[dict] = field(default_factory=list)
    gated_tickers: list[dict] = field(default_factory=list)


@dataclass
class SynthesisResult:
    """Output from Phase 3d+4: Strategy + Synthesis."""

    final_brief: str = ""
    reflection_status: str = "reviewed"


@dataclass
class Phase1Result:
    """Output from Phase 1: independent macro agents."""

    market_level: dict | None = None
    macro_metrics: dict | None = None
    foreign_flow: dict | None = None
    commodity_prices: dict = field(default_factory=dict)
    market_valuation: dict = field(default_factory=dict)
    vn_economy: dict = field(default_factory=dict)
    health: PhaseHealth | None = None


@dataclass
class Phase2SectorsCompleteCheckpoint:
    """Checkpoint written after Phase 2 sector + longterm fan-out completes,
    BEFORE positions ensemble starts.

    Serves as a recovery point: if positions ensemble hangs (e.g. silent
    provider stall past the 75s wall, SWI-318), operator can resume with
    `--resume-from=phase2_sectors_complete` and re-run only positions +
    Phase 3+ instead of the full ~20-minute pipeline.
    """

    sector_results: list[str] = field(default_factory=list)
    sector_signals: list[dict] = field(default_factory=list)
    sector_beliefs: list[dict] = field(default_factory=list)
    failed_sector_count: int = 0
    longterm: str | None = None
    # PhaseHealth covering only sector + longterm (positions not yet attempted)
    health: PhaseHealth | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Phase2SectorsCompleteCheckpoint:
        if not isinstance(data, dict):
            raise ValueError(
                f"Phase2SectorsCompleteCheckpoint.from_dict expects dict, got {type(data)}"
            )
        return cls(
            sector_results=data.get("sector_results") or [],
            sector_signals=data.get("sector_signals") or [],
            sector_beliefs=data.get("sector_beliefs") or [],
            failed_sector_count=data.get("failed_sector_count") or 0,
            longterm=data.get("longterm"),
            health=PhaseHealth(**data["health"]) if data.get("health") else None,
        )


@dataclass
class Phase2Result:
    """Output from Phase 2: sector analysis + position monitor."""

    sector_results: list[str] = field(default_factory=list)
    sector_signals: list[dict] = field(default_factory=list)
    position_alerts: dict = field(default_factory=lambda: {"alerts": []})
    sector_beliefs: list[dict] = field(default_factory=list)
    position_beliefs: list[dict] = field(default_factory=list)
    failed_sector_count: int = 0
    health: PhaseHealth | None = None

    @property
    def all_sectors_failed(self) -> bool:
        """True if every sector analysis failed (no usable signals)."""
        return self.failed_sector_count > 0 and self.failed_sector_count >= len(self.sector_results)

    def to_dict(self) -> dict:
        """Serialize for JSON checkpoint storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Phase2Result:
        """Deserialize from JSON checkpoint. Validates required fields exist."""
        if not isinstance(data, dict):
            raise ValueError(f"Phase2Result.from_dict expects dict, got {type(data)}")
        return cls(
            sector_results=data.get("sector_results") or [],
            sector_signals=data.get("sector_signals") or [],
            position_alerts=data.get("position_alerts") or {"alerts": []},
            sector_beliefs=data.get("sector_beliefs") or [],
            position_beliefs=data.get("position_beliefs") or [],
            failed_sector_count=data.get("failed_sector_count") or 0,
            health=PhaseHealth(**data["health"]) if data.get("health") else None,
        )
