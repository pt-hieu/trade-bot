"""Build structured recommendations directly from pipeline data."""

import logging
from collections import defaultdict

from agents.retro.parser import (
    SECTION_LONG_TERM,
    SECTION_MY_HOLDINGS,
    SECTION_SKIP_THESE,
    SECTION_TOP_PICKS,
    SECTION_WHAT_TO_DO,
)
from agents.tools.strategy_classifier import classify_strategy
from pipeline.recommendation_helpers import (
    CONVICTION_CONFIDENCE,
    SIGNAL_CONFIDENCE,
    accuracy_discounted_confidence,
    build_verdict,
    format_dissent,
)
from pipeline.skip_rec_builder import build_skip_recs
from shared.rules.plan_shape import coerce_plan_shape_for_check
from shared.rules.rr_math import compute_net_rr_only
from shared.rules.skip_selector import select_skip_tickers
from shared.rules.stop_resolution import StopResolutionInput, resolve_stop_for_rec
from shared.rules.vnd_price_clamp import normalize_vnd_price
from shared.trading_config import get_trading_config

# strategy_classifier strategy → plan_shape. DIVERGENCE/MOMENTUM/UNCLASSIFIED
# map to NONE on purpose — those level rules don't project onto the 5 shapes
# without silently relabelling wrong-geometry strategies.
_STRATEGY_TO_SHAPE: dict[str, str] = {
    "BREAKOUT": "BREAKOUT",
    "PULLBACK": "PULLBACK",
    "TREND": "TREND_PULLBACK",
    "BOUNCE": "BOUNCE",
    "MEAN_REVERSION": "MEAN_REVERT",
    "DIVERGENCE": "NONE",
    "MOMENTUM": "NONE",
    "UNCLASSIFIED": "NONE",
}

logger = logging.getLogger(__name__)

# Valid rec_action enum values in the database
_VALID_ACTIONS = frozenset(
    {
        "BUY",
        "SELL",
        "HOLD",
        "WATCH",
        "WAIT",
        "SKIP",
        "AVOID",
        "LIMIT_BUY",
        "EXIT",
        "TRIM",
        "ADD",
        "EVALUATE",
    }
)
BUY_ACTIONS = frozenset({"BUY", "LIMIT_BUY", "ADD"})

# HOLD/EVALUATE/TRIM/EXIT/ADD recs for held positions must carry a stop so
# the retro evaluator can score `stop_hit` against actual price action. See
# MON-2026-04-24-002 for the NULL-stop class of bug this guards.
_ACTIONS_REQUIRING_STOP: frozenset[str] = frozenset({"HOLD", "TRIM", "EXIT", "EVALUATE", "ADD"})


def _holding_data_from_slice(holding_slice: dict) -> StopResolutionInput:
    """Project a `portfolio_holdings` slice into the resolver's input shape.

    `plan_type` is only emitted when it matches the runtime enum; unknown
    values drop to an unset key (total=False) so the resolver's precedence
    falls through to the `brief_stop_vnd` tier.
    """
    data: StopResolutionInput = {
        "ticker": (holding_slice.get("ticker") or "").upper(),
        "breakeven_stop": holding_slice.get("breakeven_stop"),
        "catastrophic_stop": holding_slice.get("catastrophic_stop"),
    }
    raw_plan = (holding_slice.get("plan_type") or "").upper()
    if raw_plan == "SWING":
        data["plan_type"] = "SWING"
    elif raw_plan == "LONGTERM":
        data["plan_type"] = "LONGTERM"
    return data


def _backfill_stop_from_holding(rec: dict, holding_slice: dict | None) -> None:
    """Overwrite a rec's `stop_price` via `resolve_stop_for_rec` when missing.

    Only acts when the rec already lacks a stop and the action is one that
    surfaces a stop. Fail-loud for held SWING positions where neither the
    LLM nor the resolver produced a stop — persisting NULL re-opens
    MON-2026-04-24-002.
    """
    action = (rec.get("action") or "").upper()
    if action not in _ACTIONS_REQUIRING_STOP:
        return
    if rec.get("stop_price"):
        return
    if not holding_slice:
        return

    holding_data = _holding_data_from_slice(holding_slice)
    resolved = resolve_stop_for_rec(
        plan_type=holding_data.get("plan_type"),
        holding=holding_data,
        brief_stop_vnd=None,
        atr_trail_state=None,
    )
    if resolved is None:
        if (holding_slice.get("plan_type") or "").upper() == "SWING":
            logger.error(
                "STOP_RESOLUTION_EMPTY: SWING rec for %s (source=%s action=%s) "
                "has no stop and holding slice carries neither breakeven_stop "
                "nor trail state — persisting NULL risks retro stop_hit=false. "
                "Check portfolio_holdings.breakeven_stop for this ticker.",
                rec.get("ticker"),
                rec.get("source"),
                action,
            )
        return

    rec["stop_price"] = resolved.price_vnd
    rec["stop_source"] = resolved.source


def build_structured_recommendations(
    pre_computed_picks: list[dict],
    position_alerts: dict,
    sector_signals: list[dict],
    holdings: list[dict],
    trading_mode: dict | None,
    longterm_watchlist: dict[str, dict] | None = None,
    beliefs_by_ticker: dict[str, dict] | None = None,
    calibration_stats: dict[str, dict] | None = None,
    trade_setups_by_ticker: dict[str, dict] | None = None,
    valid_tickers: frozenset[str] | None = None,
    gated_tickers: list[dict] | None = None,
    technicals_by_ticker: dict[str, dict] | None = None,
    gate_floor_at_build: float | None = None,
    gate_passes_at_build: bool | None = None,
) -> list[dict]:
    """Build recommendation dicts from structured pipeline data.

    Dedup is per-section (`seen_by_section`) so a ticker on both the swing
    and long-term watchlists lands in both WHAT_TO_DO and LONG_TERM. A flat
    seen-set would silently drop one of the two sections.

    ``holdings`` is the list[HoldingData] form; MY HOLDINGS lookups route
    through :func:`collapse_holdings_by_ticker` so the SWING-preferred
    collapse rule stays in one place.
    """
    from shared.neon import collapse_holdings_by_ticker

    _beliefs = beliefs_by_ticker or {}
    _setups = trade_setups_by_ticker or {}
    recs: list[dict] = []
    seen_by_section: dict[str, set[str]] = defaultdict(set)

    holdings_by_ticker = collapse_holdings_by_ticker(holdings or [])
    holdings_tickers = set(holdings_by_ticker.keys())

    # 1. BUY recs from pre-computed picks
    for pick in pre_computed_picks or []:
        ticker = pick.get("ticker") or ""
        if not ticker:
            continue
        ticker = ticker.upper()

        # Build rationale with LIMIT_BUY context when applicable
        rationale = pick.get("note") or ""
        if pick.get("action") == "LIMIT_BUY":
            gap = pick.get("gap_from_support_pct") or 0
            market_rr = pick.get("market_rr") or 0
            rationale = (
                f"[LIMIT ORDER: {gap:.1f}% above support, market R:R {market_rr}] {rationale}"
            )

        # SWI-326: defense-in-depth normalize at the persistence boundary —
        # recovers the dropped-zeros unit-shift (44 → 44,910) when the rationale
        # cites the 5-digit price, else raises so a thousand-VND entry cannot be
        # persisted (the SAB-class incident, migration 346). Scope the raise
        # PER-PICK: one malformed/out-of-range price (e.g. a >1M VND name or a
        # producer leak) must drop only its own pick, never zero the whole rec
        # list (which would also drop unrelated HOLD/EXIT rows).
        try:
            entry_price = normalize_vnd_price(
                pick.get("entry"), rationale, agent="recommendation", boundary="persistence"
            )
            stop_price = normalize_vnd_price(
                pick.get("stop"), rationale, agent="recommendation", boundary="persistence"
            )
            target_price = normalize_vnd_price(
                pick.get("target"), rationale, agent="recommendation", boundary="persistence"
            )
        except (ValueError, TypeError) as price_exc:
            logger.error(
                "SWI-326: dropping pick %s — malformed/out-of-range price: %s",
                ticker,
                price_exc,
            )
            continue

        seen_by_section[SECTION_TOP_PICKS].add(ticker)
        recs.append(
            {
                "ticker": ticker,
                "action": pick.get("action", "BUY"),
                "section": SECTION_TOP_PICKS,
                "source": "picks",
                # Core price levels (already VND integers from compute_trade_setup_async),
                # normalized + per-pick-scoped above (SWI-326).
                "entry_price": entry_price,
                "stop_price": stop_price,
                "target_price": target_price,
                "size_shares": pick.get("shares"),
                "rationale": rationale,
                # R:R — raw float net-of-cost from picks.py.
                "risk_reward": pick.get("risk_reward"),
                "risk_reward_gross": pick.get("risk_reward_gross"),
                "target_basis": pick.get("target_basis"),
                "rr_stretch": pick.get("rr_stretch"),
                # Strategy + simulation
                "strategy": pick.get("strategy"),
                # SWI-340: SSOT routing key for is_trailing_exit().
                "exit_family": pick.get("exit_family", "FIXED_TARGET"),
                "strategy_confidence": pick.get("strategy_confidence"),
                "verdict": build_verdict(SECTION_TOP_PICKS, pick.get("action", "BUY"), pick),
                "sim_ev": pick.get("sim_ev"),
                "sim_p_target": pick.get("sim_p_target"),
                "sim_p_stop": pick.get("sim_p_stop"),
                # Volume + pattern
                "volume_vs_avg": pick.get("volume_vs_avg"),
                "volume_confirmed": pick.get("volume_confirmed"),
                "pattern_name": pick.get("pattern_name"),
                # Belief
                "belief_conviction": pick.get("belief_conviction"),
                # Context
                "counter_thesis": pick.get("key_risk") or pick.get("belief_narrative"),
                # Close price for validator entry gap cap (defense-in-depth)
                "close": pick.get("close"),
            }
        )

    # 2. HOLD/EXIT/TRIM/ADD from position alerts
    alerts = (position_alerts or {}).get("alerts") or []
    for alert in alerts:
        ticker = (alert.get("ticker") or "").upper()
        if not ticker:
            continue
        action = (alert.get("action") or "HOLD").upper()
        if action not in _VALID_ACTIONS:
            logger.warning(
                "Invalid position alert action '%s' for %s — defaulting to HOLD",
                action,
                ticker,
            )
            action = "HOLD"
        seen_by_section[SECTION_MY_HOLDINGS].add(ticker)

        holding_data = holdings_by_ticker.get(ticker) or {}

        # ADD uses current market price as entry (new capital deployment).
        # HOLD/TRIM/EXIT use avg_cost (cost basis reference, not a new entry).
        # ADD must NOT fall back to avg_cost — that would masquerade old
        # cost basis as a fresh entry price (Phase 2 §2.2 sibling). When
        # neither current_price_vnd nor alert.entry_price is fresh, log
        # the defect and skip the ADD rec rather than emit a poisoned row.
        if action == "ADD":
            entry_price = holding_data.get("current_price_vnd") or _parse_alert_price(
                alert.get("entry_price")
            )
            if not entry_price:
                logger.error(
                    "recommendation_builder: dropping ADD %s — no fresh "
                    "current_price_vnd and no alert.entry_price; refusing to "
                    "fall back to avg_cost (Phase 2 §2.2 SWI-121 sibling).",
                    ticker,
                )
                continue
        else:
            entry_price = holding_data.get("avg_cost") or _parse_alert_price(
                alert.get("entry_price")
            )

        stop_price = _parse_alert_price(alert.get("stop"))
        target_price = _parse_alert_price(alert.get("target"))

        risk_reward = None
        if action == "ADD" and entry_price and stop_price and target_price:
            cost_pct = get_trading_config().transaction_cost_pct or 0.0
            risk_reward = (
                compute_net_rr_only(entry_price, stop_price, target_price, cost_pct) or 0.0
            )

        new_rec = {
            "ticker": ticker,
            "action": action,
            "section": SECTION_MY_HOLDINGS,
            "source": "position_alerts",
            # plan_type sourced from actual holdings slice (migration 318:
            # FPT+TCB LONGTERM). Watchlist-based fallback in the inserter
            # would mislabel these as SWING and poison retro evaluations.
            "plan_type": holding_data.get("plan_type"),
            "rationale": alert.get("reason") or "",
            "urgency": alert.get("urgency"),
            "counter_thesis": (
                alert.get("counter_thesis") or format_dissent(alert.get("dissenting_views"))
            ),
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "risk_reward": risk_reward,
            "strategy_confidence": accuracy_discounted_confidence(
                alert.get("consensus", ""), calibration_stats
            ),
            "belief_conviction": (_beliefs.get(ticker) or {}).get("conviction"),
            "verdict": build_verdict(
                SECTION_MY_HOLDINGS,
                action,
                {**alert, "source": "position_alerts"},
                holding_data,
            ),
        }
        _backfill_stop_from_holding(new_rec, holding_data)
        recs.append(new_rec)

    # 3. Auto-HOLD for holdings not covered by position alerts
    logger.info(
        "Auto-HOLD check: holdings=%s, my_holdings_seen=%s",
        sorted(holdings_tickers),
        sorted(seen_by_section[SECTION_MY_HOLDINGS]),
    )
    for ticker in holdings_tickers or set():
        ticker = ticker.upper()
        if ticker in seen_by_section[SECTION_MY_HOLDINGS]:
            continue
        seen_by_section[SECTION_MY_HOLDINGS].add(ticker)
        holding_data = holdings_by_ticker.get(ticker) or {}
        new_rec = {
            "ticker": ticker,
            "action": "HOLD",
            "section": SECTION_MY_HOLDINGS,
            "source": "auto_hold",
            # plan_type sourced from actual holdings slice (see position
            # alerts above for the dual-listed rationale).
            "plan_type": holding_data.get("plan_type"),
            "rationale": "Position held — no alert triggered",
            "entry_price": holding_data.get("avg_cost"),
            "strategy_confidence": accuracy_discounted_confidence("no_data", calibration_stats),
            "belief_conviction": (_beliefs.get(ticker) or {}).get("conviction"),
            "verdict": build_verdict(
                SECTION_MY_HOLDINGS, "HOLD", {"source": "auto_hold"}, holding_data
            ),
        }
        _backfill_stop_from_holding(new_rec, holding_data)
        recs.append(new_rec)

    # 4. SKIP_THESE — delegated to the shared skip_selector so the brief
    # renderer and this builder emit identical ticker sets. Exclusions
    # match the legacy rec-builder behavior (top_picks ∪ my_holdings).
    sector_signal_by_ticker = {
        (s.get("ticker") or "").upper(): s for s in sector_signals or [] if s.get("ticker")
    }
    gated_by_ticker = {
        (g.get("ticker") or "").upper(): g for g in gated_tickers or [] if g.get("ticker")
    }
    skip_exclusions = seen_by_section[SECTION_TOP_PICKS] | seen_by_section[SECTION_MY_HOLDINGS]
    skip_entries = select_skip_tickers(sector_signals, gated_tickers, skip_exclusions)
    for entry in skip_entries:
        seen_by_section[SECTION_SKIP_THESE].add(entry["ticker"])
    recs.extend(
        build_skip_recs(
            skip_entries,
            sector_signal_by_ticker=sector_signal_by_ticker,
            gated_by_ticker=gated_by_ticker,
            beliefs_by_ticker=_beliefs,
            trade_setups_by_ticker=_setups,
        )
    )

    # 5. WATCH/WAIT from sector signals (non-BUY, non-SKIP).
    for signal in sector_signals or []:
        ticker = (signal.get("ticker") or "").upper()
        if not ticker:
            continue
        raw_signal = (signal.get("signal") or "").upper()
        if raw_signal in ("BUY", "AVOID", "SKIP"):
            continue  # BUY handled by picks; AVOID/SKIP handled by select_skip_tickers above
        if ticker in seen_by_section[SECTION_TOP_PICKS]:
            continue
        if ticker in seen_by_section[SECTION_MY_HOLDINGS]:
            continue

        action = raw_signal if raw_signal in ("WATCH", "WAIT") else "WATCH"
        section = SECTION_WHAT_TO_DO

        if ticker in seen_by_section[section]:
            continue
        seen_by_section[section].add(ticker)

        setup = _setups.get(ticker, {}) or {}
        state = setup.get("setup_state", "invalid")

        # Effective plan_shape: LLM > setup_calc > strategy_classifier fallback.
        shape = (signal.get("plan_shape") or "").upper()
        if shape in ("", "NONE"):
            shape = (setup.get("plan_shape") or "NONE").upper()
        if shape == "NONE":
            tech = (technicals_by_ticker or {}).get(ticker) or {}
            if tech:
                cls = classify_strategy(
                    tech, rsi_at_swing_low=None, has_positive_active_catalyst=False
                )
                shape = _STRATEGY_TO_SHAPE.get(cls.strategy, "NONE")

        watch_entry: dict = {
            "ticker": ticker,
            "action": action,
            "section": section,
            "source": "sector_signals",
            "rationale": signal.get("note") or "",
            "counter_thesis": signal.get("key_risk"),
            "belief_conviction": (_beliefs.get(ticker) or {}).get("conviction"),
            "strategy_confidence": SIGNAL_CONFIDENCE.get(
                (signal.get("confidence") or "").upper(), 0.5
            ),
            "verdict": build_verdict(section, action, signal),
            "plan_shape": shape,
            "invalidation_note": setup.get("invalidation_note"),
            "gate_floor_at_build": gate_floor_at_build,
            "gate_passes_at_build": gate_passes_at_build,
        }
        # Ship trigger/stop/target whenever the setup geometry is usable, even
        # if RR is below the floor (state == 'conditional'). The alert→BUY
        # loop re-evaluates the gate at trigger time.
        if state in ("triggered", "conditional") and shape != "NONE":
            watch_entry["trigger_price"] = setup.get("trigger_price") or setup.get("entry")
            watch_entry["stop_price"] = setup.get("stop")
            watch_entry["target_price"] = setup.get("target")
            watch_entry["risk_reward"] = setup.get("risk_reward")
        # Single source of truth for plan_shape ↔ trigger invariant. Rule
        # defined in shared/rules/plan_shape.py — keep DB CHECK migration 342
        # in lockstep.
        watch_entry["plan_shape"] = coerce_plan_shape_for_check(
            watch_entry.get("plan_shape"),
            action,
            watch_entry.get("trigger_price"),
            strict=False,
        )
        recs.append(watch_entry)

    # 6. Longterm watchlist. Dedupes against LONG_TERM, TOP_PICKS, and
    # MY_HOLDINGS — a ticker on sector WATCH still lands here, but a
    # ticker already held or in BUY picks does not.
    for ticker, longterm_info in (longterm_watchlist or {}).items():
        ticker = ticker.upper()
        if ticker in seen_by_section[SECTION_LONG_TERM]:
            continue
        if ticker in seen_by_section[SECTION_TOP_PICKS]:
            continue
        if ticker in seen_by_section[SECTION_MY_HOLDINGS]:
            continue
        seen_by_section[SECTION_LONG_TERM].add(ticker)
        entry_zone = longterm_info.get("entry_zone") or 0
        conviction = longterm_info.get("conviction") or "Medium"
        recs.append(
            {
                "ticker": ticker,
                "action": "WATCH",
                "section": SECTION_LONG_TERM,
                "source": "longterm",
                "rationale": f"Long-term watchlist ({conviction} conviction)",
                "entry_price": entry_zone if entry_zone > 0 else None,
                "strategy_confidence": CONVICTION_CONFIDENCE.get((conviction or "").lower(), 0.5),
                "belief_conviction": (_beliefs.get(ticker) or {}).get("conviction"),
                "verdict": build_verdict(SECTION_LONG_TERM, "WATCH", longterm_info),
            }
        )

    # Universe gate: drop rec rows for tickers not in the authoritative
    # universe (swing watchlist ∪ longterm watchlist ∪ portfolio). Legitimate
    # zero-universe fetches must raise UNIVERSE_FETCH_FAILED in the caller;
    # reaching here with a non-None but empty set means genuine emptiness.
    if valid_tickers is not None:
        filtered: list[dict] = []
        for row in recs:
            ticker = (row.get("ticker") or "").upper()
            if ticker and ticker not in valid_tickers:
                logger.warning(
                    "REC_OFF_WATCHLIST ticker=%s source=%s section=%s — dropped",
                    ticker,
                    row.get("source"),
                    row.get("section"),
                )
                continue
            filtered.append(row)
        return filtered

    return recs


def _parse_alert_price(value) -> int | None:
    """Parse position alert price ('93k', '93,000', None) to VND int."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None

    text = str(value).strip().replace(",", "").replace("N/A", "").replace("n/a", "")
    if not text:
        return None

    # Handle "93k" format (thousands VND shorthand)
    if text.lower().endswith("k"):
        try:
            return int(float(text[:-1]) * 1000)
        except (ValueError, TypeError):
            return None

    try:
        parsed = float(text)
        if parsed <= 0:
            return None
        if 0 < parsed < 1000:
            logger.warning(
                "_parse_alert_price: rejecting suspicious value %.1f (< 1000 VND) — likely k-VND without suffix",
                parsed,
            )
            return None
        return int(parsed)
    except (ValueError, TypeError):
        return None
