#!/usr/bin/env python3
"""Top pick extraction from sector signals — classify, dispatch exit strategy, simulate."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from shared.calibration_overlay import get_calibrated_entry_gap
from shared.rules.catalyst_override import CatalystInput
from shared.rules.entry_gates import is_stacked_shock_relief
from shared.rules.exit_strategy import (
    derive_atr_trail_synthetic_target,
    read_rr,
    rr_sort_weight,
)
from shared.rules.rr_math import compute_net_rr_only
from shared.rules.scoring import ScoringPhase
from shared.rules.trend_momentum import (
    TREND_FOLLOW_STRATEGIES,
    buy_trend_follow_eligible,
    derive_momentum_signals,
)
from shared.trading_config import get_trading_config

from .belief_mapping import map_signal_confidence_to_conviction as _map_conviction
from .picks_audit import AuditRunContext, audit_layer_drop, build_score_inputs
from .picks_exit_dispatch import apply_exit_strategy

if TYPE_CHECKING:
    from eval.score_recorder import ScoreRecorder
    from pipeline.types import GeopoliticalShockDict
from .tools.exit_plan import compute_exit_plan
from .tools.strategy_classifier import (
    StrategyClassification,
    classify_strategy,
    get_rsi_at_swing_low_date,
)
from .tools.technicals import get_batch_ticker_data_async
from .trade_simulator import simulate_trade


async def extract_top_picks(
    sector_signals: list[dict],
    scan_date: date,
    min_rr: float = 2.5,
    max_picks: int = 5,
    scale_factor: float = 1.0,
    exclude_tickers: list[str] | None = None,
    beliefs_by_ticker: dict[str, dict] | None = None,
    risk_regime: str | None = None,
    catalyst_boosted_tickers: set[str] | None = None,
    belief_boosted_tickers: set[str] | None = None,
    *,
    active_catalysts: Sequence[CatalystInput] | None = None,
    geopolitical_shock: GeopoliticalShockDict | None = None,
    # Phase A audit — SWI-171. Optional so existing callers (tests,
    # legacy resume paths) keep working without wiring the recorder.
    score_recorder: ScoreRecorder | None = None,
    score_phase: ScoringPhase = "morning",
    audit_context: dict | None = None,
) -> list[dict]:
    """Extract validated top picks from structured sector signals.

    Args:
        sector_signals: List of dicts with ticker, signal, note, sector
                        (from SectorAnalysisResult).
        scan_date: Date for trade setup computation.
        min_rr: Minimum R:R ratio (from goal urgency tier). Compared against
            the raw float net-of-cost R:R; never rounded before comparison.
        max_picks: Maximum picks to return (from goal urgency tier).
        scale_factor: Position sizing multiplier (from win rate).
        exclude_tickers: Tickers to skip (e.g., current holdings).
        beliefs_by_ticker: Aggregated beliefs keyed by ticker for conviction scaling.
        risk_regime: Global risk regime — threaded to trade-setup so targets
            scale with the regime (CALM expands, RISK_OFF contracts).
        belief_boosted_tickers: Tickers promoted via belief fallback (BULLISH
            aggregator belief, no sector BUY). Final picks carry
            `source="belief_fallback"` so synthesis + monitoring can tag.

    Returns:
        List of validated pick dicts sorted by R:R descending.
    """
    if max_picks <= 0:
        return []

    # Guard against None min_rr (e.g., ACCEPTANCE urgency)
    if min_rr is None:
        min_rr = 2.5

    exclude = {t.upper() for t in (exclude_tickers or [])}
    boosted = {t.upper() for t in (catalyst_boosted_tickers or set())}
    # belief_boosted_tickers is already upper-case at the producer
    # (derive_belief_boosted_tickers) — no second pass needed.
    belief_boosted = belief_boosted_tickers or set()

    # L2 (2026-04-27): per-ticker stacked-shock relief inputs. Empty set
    # outside an active shock window — the helper short-circuits.
    from shared.rules.catalyst_override import count_high_positive_per_ticker
    from shared.rules.geopolitical import derive_shock_affected_tickers

    shock_affected = derive_shock_affected_tickers(geopolitical_shock)

    # Step 1: Filter BUY signals, exclude holdings
    buy_signals = [
        s
        for s in sector_signals
        if s.get("signal", "").upper() == "BUY" and s.get("ticker", "").upper() not in exclude
    ]

    if not buy_signals:
        return []

    # Step 2: Single batch fetch — get_batch_ticker_data_async embeds
    # `trade_setup` per ticker (see technicals.py::_enrich_with_setup_and_prose),
    # so one call replaces the previous per-ticker compute_trade_setup_async +
    # get_ticker_data_async loop.
    buy_tickers = [s["ticker"].upper() for s in buy_signals]
    # SWI-305: parallel fetch — tech_data + foreign-flow are independent.
    # Flow threads into picks_audit.build_score_inputs via tech_data["flow"].
    from shared.api.enrichment import get_daily_flow_batch

    batch_result, flow_result = await asyncio.gather(
        get_batch_ticker_data_async(buy_tickers, scan_date, risk_regime=risk_regime),
        get_daily_flow_batch(buy_tickers, scan_date),
        return_exceptions=True,
    )
    if isinstance(batch_result, BaseException):
        logger.warning(
            "get_batch_ticker_data_async(%d tickers, %s) failed: %s",
            len(buy_tickers),
            scan_date,
            batch_result,
        )
        return []
    batch = batch_result
    if isinstance(flow_result, BaseException):
        logger.warning(
            "get_daily_flow_batch(%d tickers, %s) failed: %s",
            len(buy_tickers),
            scan_date,
            flow_result,
        )
        flow_by_ticker: dict[str, dict[str, float | str | None] | None] = {}
    else:
        flow_by_ticker = flow_result or {}
    for ticker, flow in flow_by_ticker.items():
        entry = batch.get(ticker) if isinstance(batch, dict) else None
        if entry is None or "error" in entry:
            continue
        entry["flow"] = flow or {}

    # Per-ticker HIGH/MEDIUM POSITIVE catalyst counts for stacked-shock
    # relief. Empty dict outside an active shock window so the no-shock
    # path is identical to legacy.
    high_positive_count = (
        count_high_positive_per_ticker(active_catalysts, set(buy_tickers))
        if active_catalysts and shock_affected
        else {}
    )

    # SWI-171 Phase A: build the audit run-context once so every audit
    # row records a consistent suppressor decision. Per-candidate state
    # (ticker, sector, R:R) is threaded into audit_layer_drop separately.
    audit_ctx_dict = audit_context or {}
    run_ctx = AuditRunContext(
        recorder=score_recorder,
        phase=score_phase,
        regime=(risk_regime or "CAUTIOUS").upper(),
        urgency_tier=audit_ctx_dict.get("urgency_tier"),
        underlying_stress=bool(audit_ctx_dict.get("underlying_stress")),
        shock_active=bool(audit_ctx_dict.get("shock_active")),
        has_high_positive_macro_catalyst=bool(
            audit_ctx_dict.get("has_high_positive_macro_catalyst")
        ),
        bullish_sector_belief_count=int(audit_ctx_dict.get("bullish_sector_belief_count") or 0),
        total_sector_count=int(audit_ctx_dict.get("total_sector_count") or 0),
    )

    picks = []
    for signal in buy_signals:
        ticker = signal["ticker"].upper()
        tech_data = batch.get(ticker) or {}
        sector_label = signal.get("sector") or signal.get("sector_name")
        candidate_source = (
            "belief_fallback" if ticker in belief_boosted else (signal.get("source") or "sector")
        )
        per_ticker_positive = (
            bool(high_positive_count.get(ticker, 0)) if high_positive_count else False
        )

        # ── Layer 1a: tech_data error (no setup at all) ──────────────
        if "error" in tech_data:
            logger.info(
                "picks_filter: %s dropped — setup_error: %s", ticker, tech_data.get("error")
            )
            await audit_layer_drop(
                ctx=run_ctx,
                ticker=ticker,
                sector_label=sector_label,
                candidate_source=candidate_source,
                per_ticker_positive=per_ticker_positive,
                features=build_score_inputs(
                    signal=signal,
                    tech_data=None,
                    setup=None,
                    boosted=boosted,
                    high_positive_count=high_positive_count,
                    bullish_sector_belief_count=run_ctx.bullish_sector_belief_count,
                    total_sector_count=run_ctx.total_sector_count,
                ),
                gated_by="setup_invalid",
                gate_reason=f"tech_data_error: {tech_data.get('error')}",
                chosen_rr_for_relief=0.0,
                sim_populated=False,
            )
            continue

        setup = tech_data.get("trade_setup") or {}
        if setup.get("error") or not setup.get("valid"):
            logger.info(
                "picks_filter: %s dropped — setup_invalid: %s",
                ticker,
                setup.get("error", "valid=False"),
            )
            await audit_layer_drop(
                ctx=run_ctx,
                ticker=ticker,
                sector_label=sector_label,
                candidate_source=candidate_source,
                per_ticker_positive=per_ticker_positive,
                features=build_score_inputs(
                    signal=signal,
                    tech_data=tech_data,
                    setup=None,
                    belief=(beliefs_by_ticker or {}).get(ticker),
                    boosted=boosted,
                    high_positive_count=high_positive_count,
                    bullish_sector_belief_count=run_ctx.bullish_sector_belief_count,
                    total_sector_count=run_ctx.total_sector_count,
                ),
                gated_by="setup_invalid",
                gate_reason=str(setup.get("error", "valid=False")),
                chosen_rr_for_relief=0.0,
                sim_populated=False,
            )
            continue

        # Raw float net-of-cost R:R — never round before gate comparison.
        # Setup is fixed-target at this line (ATR_TRAIL setups exit the loop
        # earlier via the gated_by="setup_invalid" continue above); read_rr
        # therefore returns a float, but we keep the `or 0.0` fallback for
        # producer-leak resilience (logged via grep guard if regressed).
        chosen_rr = read_rr(setup) or 0.0

        levels = tech_data.get("levels") or {}
        swing_low_date = levels.get("swing_low_date")
        rsi_at_low = None
        if swing_low_date:
            try:
                rsi_at_low = await get_rsi_at_swing_low_date(ticker, swing_low_date)
            except Exception as exception:
                logger.warning(
                    "get_rsi_at_swing_low_date(%s, %s) failed — divergence path skipped: %s: %s",
                    ticker,
                    swing_low_date,
                    type(exception).__name__,
                    exception,
                )
        if setup.get("volume_vs_avg") is not None:
            tech_data["volume_vs_avg"] = setup["volume_vs_avg"]
        strategy_cls: StrategyClassification = classify_strategy(
            tech_data,
            rsi_at_low,
            has_positive_active_catalyst=ticker in boosted,
        )

        # ── Layer 2: deterministic trend-momentum gate ───────────────
        # Rejection drops the pick so the LLM's BUY effectively downgrades
        # to WATCH — composer-owned, not prompt-owned. Batch fetcher
        # populates `momentum_signals` for every non-error row; derive
        # inline only if the invariant is violated (fail-closed).
        if strategy_cls.strategy in TREND_FOLLOW_STRATEGIES:
            signals = tech_data.get("momentum_signals") or derive_momentum_signals(tech_data)
            eligible, reason = buy_trend_follow_eligible(tech_data, signals)
            if not eligible:
                logger.info(
                    "picks_filter: %s dropped — trend-momentum gate: %s (strategy=%s)",
                    ticker,
                    reason,
                    strategy_cls.strategy,
                )
                await audit_layer_drop(
                    ctx=run_ctx,
                    ticker=ticker,
                    sector_label=sector_label,
                    candidate_source=candidate_source,
                    per_ticker_positive=per_ticker_positive,
                    features=build_score_inputs(
                        signal=signal,
                        tech_data=tech_data,
                        setup=setup,
                        strategy_cls=strategy_cls,
                        belief=(beliefs_by_ticker or {}).get(ticker),
                        boosted=boosted,
                        high_positive_count=high_positive_count,
                        bullish_sector_belief_count=run_ctx.bullish_sector_belief_count,
                        total_sector_count=run_ctx.total_sector_count,
                        trend_gate_failed=True,
                    ),
                    gated_by="trend_momentum",
                    gate_reason=f"{reason} (strategy={strategy_cls.strategy})",
                    chosen_rr_for_relief=chosen_rr,
                    sim_populated=False,
                )
                continue

        is_stacked = is_stacked_shock_relief(ticker, shock_affected, high_positive_count)
        passed, exit_family, chosen_rr = apply_exit_strategy(
            ticker=ticker,
            strategy=strategy_cls.strategy,
            setup=setup,
            tech_data=tech_data,
            levels=levels,
            risk_regime=risk_regime,
            boosted=boosted,
            min_rr=min_rr,
            chosen_rr=chosen_rr,
            rr_tolerance_pct=float(get_trading_config().screen_tolerance_pct),
            stacked_shock_relief=is_stacked,
        )

        # Sim runs here (after apply_exit_strategy mutates entry/stop for
        # ATR_TRAIL passers) so L3/L4 drop audit rows carry real sim
        # probabilities instead of structural defaults. ATR_TRAIL has no
        # fixed target; the synthetic target is for sim probability bounds
        # only — setup["target"] stays None per SWI-115.
        sim_target = setup.get("target")
        if sim_target is None and setup.get("exit_family") == "ATR_TRAIL":
            sim_target = derive_atr_trail_synthetic_target(
                entry=setup["entry"],
                atr=tech_data.get("atr"),
            )
        sim_target = float(sim_target or setup["entry"] * 1.1)
        sim = simulate_trade(
            ticker=ticker,
            entry=setup["entry"],
            stop=setup["stop"],
            target=sim_target,
            technicals=tech_data,
        )

        if not passed:
            # Layers 3-4 dropped this candidate. The dispatcher already
            # logged the precise reason; persist the audit row using the
            # post-layer-2 features (sim is not yet computed → defaults).
            drop_kind = setup.get("audit_drop_kind") or "rr_floor"
            drop_reason = setup.get("audit_drop_reason") or "rr_gate_failed"
            await audit_layer_drop(
                ctx=run_ctx,
                ticker=ticker,
                sector_label=sector_label,
                candidate_source=candidate_source,
                per_ticker_positive=per_ticker_positive,
                features=build_score_inputs(
                    signal=signal,
                    tech_data=tech_data,
                    setup=setup if setup.get("valid") else None,
                    strategy_cls=strategy_cls,
                    simulation=sim,
                    belief=(beliefs_by_ticker or {}).get(ticker),
                    boosted=boosted,
                    high_positive_count=high_positive_count,
                    bullish_sector_belief_count=run_ctx.bullish_sector_belief_count,
                    total_sector_count=run_ctx.total_sector_count,
                ),
                gated_by=drop_kind,
                gate_reason=drop_reason,
                chosen_rr_for_relief=chosen_rr,
                sim_populated=True,
            )
            continue

        # ATR_TRAIL has no fixed R:R — surface None so downstream readers
        # branch on exit_family instead of misreading 0.0 as "fails floor".
        rr_for_pick: float | None = None if exit_family == "ATR_TRAIL" else chosen_rr

        target_basis = setup.get("target_basis") or "conservative"
        verdict = "partial_size" if target_basis == "aggressive" else "full_size"

        # Belief data for recommendation records (conviction + direction + narrative)
        belief = (beliefs_by_ticker or {}).get(ticker)
        conviction = _map_conviction(signal.get("confidence"), belief)
        # Sizing neutralized: belief accuracy <33%, conviction inversely correlated with accuracy
        conviction_scale = 1.0
        raw_shares = setup.get("shares", 0)
        scaled_shares = max(1, int(raw_shares * scale_factor * conviction_scale))

        # Exit ladder uses raw level pair, not the chosen target.
        levels_used = setup.get("levels_used", {})
        exit_plan = compute_exit_plan(
            entry=setup["entry"],
            stop=setup["stop"],
            # SWI-3a: prefer MA-free swing target; fall back to MA-inclusive
            # nearest_resistance only when no swing target was emitted.
            conservative_target=(
                levels_used.get("nearest_swing_target") or levels_used.get("nearest_resistance")
            ),
            aggressive_target=levels_used.get("swing_high"),
            range_20d_low=levels_used.get("range_20d_low"),
        )

        # Phase A audit: candidate cleared layers 1-4. Layer 5 (validator
        # max_picks) is recorded by the validator wrapper later — at this
        # point we only know the candidate has not yet been culled, not
        # whether it makes the final cut.
        await audit_layer_drop(
            ctx=run_ctx,
            ticker=ticker,
            sector_label=sector_label,
            candidate_source=candidate_source,
            per_ticker_positive=per_ticker_positive,
            features=build_score_inputs(
                signal=signal,
                tech_data=tech_data,
                setup=setup,
                strategy_cls=strategy_cls,
                simulation=sim,
                belief=(beliefs_by_ticker or {}).get(ticker),
                boosted=boosted,
                high_positive_count=high_positive_count,
                bullish_sector_belief_count=run_ctx.bullish_sector_belief_count,
                total_sector_count=run_ctx.total_sector_count,
            ),
            gated_by="passed",
            gate_reason=None,
            chosen_rr_for_relief=chosen_rr,
            sim_populated=True,
        )

        # `source` field: belief_fallback overrides signal-embedded source so
        # the BULLISH-aggregator-no-sector-BUY path is authoritatively tagged
        # even if the synthetic signal gets modified downstream.
        source = (
            "belief_fallback" if ticker in belief_boosted else (signal.get("source") or "sector")
        )
        # Propagate borderline context from screen (signal) + R:R (setup).
        # Synthesis / critic / entry_strategist prompts key off these fields
        # to decide whether a borderline BUY still merits promotion.
        merged_borderline: list[str] = []
        merged_borderline.extend(signal.get("borderline_reasons") or [])
        merged_borderline.extend(setup.get("borderline_reasons") or [])
        pick = {
            "ticker": ticker,
            "source": source,
            "sector": signal.get("sector", ""),
            "note": signal.get("note", ""),
            "entry": setup["entry"],
            "stop": setup["stop"],
            "target": setup["target"],
            "close": setup.get("close") or tech_data.get("close") or 0,
            "risk_reward": rr_for_pick,
            "risk_reward_gross": setup.get("risk_reward_gross"),
            "shares": scaled_shares,
            "position_vnd": scaled_shares * setup["entry"],
            "target_basis": target_basis,
            "rr_stretch": setup.get("rr_stretch"),
            "verdict": verdict,
            # Exit plan
            "exit_plan": exit_plan,
            # Volume context
            "volume_vs_avg": setup.get("volume_vs_avg"),
            "volume_confirmed": setup.get("volume_confirmed"),
            "pattern_name": setup.get("pattern_name"),
            "pattern_signal": setup.get("pattern_signal"),
            # Strategy classification
            "strategy": strategy_cls.strategy,
            "strategy_confidence": round(strategy_cls.confidence, 2),
            "strategy_signals": strategy_cls.matched_signals,
            # Monte Carlo simulation
            "sim_ev": round(sim.expected_return_pct, 1),
            "sim_p_target": round(sim.p_target, 2),
            "sim_p_stop": round(sim.p_stop, 2),
            "sim_action": sim.recommended_action,
            # Belief context for synthesis
            "belief_conviction": round(conviction, 2),
            "belief_direction": belief.get("direction") if belief else None,
            "belief_narrative": belief.get("belief_narrative") if belief else None,
            "key_risk": signal.get("key_risk"),
            # Borderline context (L5) — surfaced to synthesis / critic /
            # entry_strategist prompts; absent when clean pass.
            "fundamental_flag": signal.get("fundamental_flag"),
            "rr_flag": setup.get("rr_flag"),
            "borderline_reasons": merged_borderline or None,
            "fundamental_distance": signal.get("fundamental_distance"),
            "sector_name": signal.get("sector_name"),
        }

        # Flag negative EV for synthesis agent
        if sim.expected_return_pct < 0:
            pick["negative_ev_warning"] = (
                f"Monte Carlo: negative EV ({sim.expected_return_pct:+.1f}%)"
            )

        # exit_state is the single source for polymorphic dispatch downstream;
        # exit_state_from_rec unpacks it into top-level ExitState fields.
        pick["exit_state"] = setup.get("exit_state")
        pick["exit_family"] = setup.get("exit_family", "FIXED_TARGET")

        # Determine action: BUY (market-ready) vs LIMIT_BUY (needs pullback).
        # ATR_TRAIL picks don't use market_setup fork (no fixed target R:R).
        if "market_setup" in setup and setup.get("exit_family") != "ATR_TRAIL":
            market_entry_setup = setup["market_setup"]
            # market_setup branch is gated by `setup.get("exit_family") != "ATR_TRAIL"`
            # above — market_rr is fixed-target only; read_rr returns a float.
            market_rr = read_rr(market_entry_setup) or 0.0
            gap_from_support = market_entry_setup.get("gap_from_support_pct") or 0
            market_shares = max(
                1, int((market_entry_setup.get("shares") or 0) * scale_factor * conviction_scale)
            )

            # Shared context dict for LIMIT_BUY branches (synthesis needs market-level data)
            market_setup_context = {
                "entry": market_entry_setup["entry"],
                "stop": market_entry_setup["stop"],
                "target": market_entry_setup["target"],
                "risk_reward": market_rr,
                "shares": market_shares,
                "position_vnd": market_shares * market_entry_setup["entry"],
                "valid": market_entry_setup["valid"],
                "gap_from_support_pct": gap_from_support,
            }

            if market_rr >= min_rr:
                pick["action"] = "BUY"
                pick["entry"] = market_entry_setup["entry"]
                pick["stop"] = market_entry_setup["stop"]
                pick["target"] = market_entry_setup["target"]
                pick["risk_reward"] = market_rr
                pick["shares"] = market_shares
                pick["position_vnd"] = market_shares * market_entry_setup["entry"]
            else:
                # LIMIT_BUY: market R:R insufficient. Use promoted pullback
                # (already in setup primary) or generate inline pullback for
                # the 1.5-3.0% gap blind spot.
                pick["action"] = "LIMIT_BUY"
                pick["gap_from_support_pct"] = gap_from_support
                pick["market_rr"] = market_rr
                pick["market_setup"] = market_setup_context

                if setup.get("pullback_promoted"):
                    pick["pullback_entry"] = True
                else:
                    # Gap 1.5-3.0% blind spot — generate inline pullback at
                    # the calibrated max gap below close.
                    tc = get_trading_config()
                    max_gap = get_calibrated_entry_gap() or tc.max_entry_gap_pct
                    cost_pct = tc.transaction_cost_pct or 0.0
                    current_close = pick["close"]
                    inline_entry = round(current_close * (1 - max_gap / 100))
                    if inline_entry > pick["stop"]:
                        inline_rr = (
                            compute_net_rr_only(
                                inline_entry, pick["stop"], pick["target"], cost_pct
                            )
                            or 0.0
                        )
                        inline_shares = max(
                            1,
                            int((setup.get("shares") or 0) * scale_factor * conviction_scale),
                        )
                        pick["entry"] = inline_entry
                        pick["risk_reward"] = inline_rr
                        pick["shares"] = inline_shares
                        pick["position_vnd"] = inline_shares * inline_entry
                        pick["pullback_entry"] = True
        else:
            # Price near support — standard BUY (limit ~= market)
            pick["action"] = "BUY"

        picks.append(pick)

    # SWI-125: filter before sort/cap so every downstream consumer
    # (writer, builder, renderer, alert_registrar) sees one gate-passed list.
    picks = [pick for pick in picks if _passes_rr_floor(pick, min_rr)]

    # Step 4: Sort BUY before LIMIT_BUY, then by R:R descending. Trailing
    # exits rank as max-bound (unbounded upside) via rr_sort_weight — fixes
    # the historic `or 0.0` coercion that buried them at the bottom.
    picks.sort(key=lambda p: (0 if p.get("action") == "BUY" else 1, rr_sort_weight(p)))
    return picks[:max_picks]


def _passes_rr_floor(pick: dict, min_rr: float) -> bool:
    """Gate predicate: keep picks whose risk_reward >= min_rr OR is None.

    None means ATR_TRAIL exit_family — risk_reward is unknowable until
    the trail anchor moves, so the floor does not apply.
    """
    rr = pick.get("risk_reward")
    return rr is None or rr >= min_rr
