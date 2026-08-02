"""Typed agent deps + legacy-context marshalling for native PydanticAI tools.

`AgentDeps` replaces the prior `context: dict` passed through the legacy
broker layer (SWI-180). Field set was audited from
`_ctx.get(...)` and `context.get(...)` reads across `scripts/agents/`,
`scripts/pipeline/`, and `scripts/agents/tools/broker/domains/`.

`_deps_to_ctx_dict` marshals `AgentDeps` back to the `_ctx: dict` shape
expected by existing `domains/*.py` implementations until those signatures
migrate to `RunContext[AgentDeps]` directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentDeps:
    """Typed deps passed via `Agent(deps_type=AgentDeps)`.

    Counters live for the lifetime of one `agent.run`; `create_agent` builds
    a fresh `AgentDeps` per invocation so counters reset naturally.
    """

    # core identity
    scan_date: object  # date | None — kept loose for domain code's date casts
    agent_key: str = "unknown"
    source: str = ""
    tickers_in_scope: list[str] = field(default_factory=list)

    # inject-once data (read by tool implementations + agent prompts)
    midday_prices: object = None
    current_prices: object = None
    holdings_tickers: list[str] = field(default_factory=list)
    active_alerts_snapshot: object = None
    previous_brief: object = None
    previous_date: object = None
    tool_cache: dict[str, object] = field(default_factory=dict)
    global_macro: object = None
    hot_sectors: list[str] = field(default_factory=list)
    cold_sectors: list[str] = field(default_factory=list)
    market_regime: str = ""
    vix: float | None = None
    trading_mode: str = ""
    bounce_confirmed: bool = False
    prior_down_volume: bool = False
    volume_trend: str = ""
    pattern: str = ""
    detected_drifts: object = None

    # per-run mutable counters (reset at create_agent boundary)
    iteration_count: int = 0
    error_signature_counts: dict[str, int] = field(default_factory=dict)
    unlocked: set[str] = field(default_factory=set)
    # SWI-86: count of identical (tool, args) calls within one run. The global
    # iteration cap already prevents runaway loops; this is a budget-efficiency
    # guard so an agent repeating the same query doesn't burn the whole
    # invocation budget on duplicate work.
    duplicate_call_counts: dict[str, int] = field(default_factory=dict)


def deps_to_ctx_dict(deps: AgentDeps) -> dict[str, object]:
    """Marshal `AgentDeps` back to the legacy `_ctx: dict` shape consumed by
    existing `domains/*.py` implementations.
    """
    return {
        "scan_date": deps.scan_date,
        "agent_key": deps.agent_key,
        "source": deps.source,
        "tickers_in_scope": deps.tickers_in_scope,
        "midday_prices": deps.midday_prices,
        "current_prices": deps.current_prices,
        "holdings_tickers": deps.holdings_tickers,
        "active_alerts_snapshot": deps.active_alerts_snapshot,
        "previous_brief": deps.previous_brief,
        "previous_date": deps.previous_date,
        "_tool_cache": deps.tool_cache,
        "global_macro": deps.global_macro,
        "hot_sectors": deps.hot_sectors,
        "cold_sectors": deps.cold_sectors,
        "market_regime": deps.market_regime,
        "vix": deps.vix,
        "trading_mode": deps.trading_mode,
        "bounce_confirmed": deps.bounce_confirmed,
        "prior_down_volume": deps.prior_down_volume,
        "volume_trend": deps.volume_trend,
        "pattern": deps.pattern,
        "detected_drifts": deps.detected_drifts,
    }
