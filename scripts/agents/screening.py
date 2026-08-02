#!/usr/bin/env python3
"""Deterministic quantitative screening for BUY signal candidates.

Filters BUY signals from sector agents by fundamental quality gates
before extract_top_picks() computes trade setups. Non-BUY signals
(WATCH, WAIT, AVOID) always pass through unchanged.

Thresholds live in trading_config (global defaults) with optional
per-sector overrides in sector_screening_overrides. The scorer is
tolerance-aware: each metric gets 0 (pass), 1 (soft miss — within
cfg.screen_tolerance_pct of the threshold), or 2 (hard miss). A signal
passes when composite <= cfg.screen_composite_limit AND no metric
hard-fails, picking up ``fundamental_flag='borderline'`` when it has
any soft misses so downstream advocate/critic can see the context.
"""

from typing import TypedDict

from shared.api.earnings_quality import compute_earnings_quality
from shared.api.fundamentals import get_financial_ratios_batch
from shared.neon.sectors import SectorThresholdRow, get_sector_thresholds_batch
from shared.trading_config import TradingConfig


class ScoreResult(TypedDict):
    """Per-ticker fundamental-score aggregate. Produced by ``_score_thresholds``."""

    composite: float
    distances: dict[str, float]
    scores: dict[str, int]
    soft_miss_reasons: list[str]
    hard_fail_metrics: list[str]


async def screen_buy_signals(
    sector_signals: list[dict],
    cfg: TradingConfig,
) -> tuple[list[dict], list[dict]]:
    """Filter BUY signals through fundamental quality gates.

    Non-BUY signals pass through unchanged. BUY signals are checked
    against the latest financial ratios + per-sector threshold overrides.

    Args:
        sector_signals: List of signal dicts with 'ticker', 'signal', etc.
        cfg: TradingConfig with screen_* threshold fields + tolerance.

    Returns:
        (all_signals_with_passed_buys, rejected_signals)
        Rejected signals include 'rejection_reason' for logging.
        Passed signals include 'screen_score' (0-100), 'stock_category',
        and — on soft misses — 'fundamental_flag', 'borderline_reasons',
        'fundamental_distance' so downstream prompts can weigh the case.
    """
    buy_signals = [s for s in sector_signals if s.get("signal", "").upper() == "BUY"]
    non_buy = [s for s in sector_signals if s.get("signal", "").upper() != "BUY"]

    if not buy_signals:
        return sector_signals, []

    tickers = [s["ticker"].upper() for s in buy_signals]
    ratios_batch, sector_thresholds = await _fetch_inputs(tickers)

    passed: list[dict] = []
    rejected: list[dict] = []

    for signal in buy_signals:
        ticker = signal["ticker"].upper()
        ratios = ratios_batch.get(ticker)

        if not ratios:
            enriched = {**signal}
            if cfg.screen_missing_data_policy == "fail":
                enriched["rejection_reason"] = "no fundamental data"
                rejected.append(enriched)
            else:
                enriched["screen_note"] = "NO_FUNDAMENTAL_DATA"
                passed.append(enriched)
            continue

        sector_row = sector_thresholds.get(ticker)
        result = _score_thresholds(ratios, cfg, sector_row)

        if result["hard_fail_metrics"] or result["composite"] > cfg.screen_composite_limit:
            reasons = _format_rejection(result)
            enriched = {**signal, "rejection_reason": "; ".join(reasons)}
            if sector_row and "sector_name" in sector_row:
                enriched["sector_name"] = sector_row["sector_name"]
            rejected.append(enriched)
            continue

        # Earnings quality gate — second pass, unchanged behavior.
        min_core = getattr(cfg, "screen_min_core_ratio", 0.4)
        eq_data = await compute_earnings_quality(ticker, periods=4)
        core_ratio = eq_data.get("latest", {}).get("core_ratio")
        if core_ratio is not None and core_ratio < min_core:
            enriched = {
                **signal,
                "rejection_reason": f"Low earnings quality: {core_ratio:.0%} core ratio < {min_core:.0%}",
            }
            rejected.append(enriched)
            continue

        from shared.longterm_calculations import score_conviction

        _, score = score_conviction(ticker, [ratios])
        category = _classify_stock_category(ticker, ratios, core_ratio)

        enriched = {**signal, "screen_score": score, "stock_category": category}
        if sector_row and "sector_name" in sector_row:
            enriched["sector_name"] = sector_row["sector_name"]

        # Borderline enrichment: continuous distances preserved so advocate
        # / critic / entry_strategist prompts can decide qualitatively
        # whether the borderline fundamental is acceptable.
        if result["soft_miss_reasons"]:
            enriched["fundamental_flag"] = "borderline"
            enriched["borderline_reasons"] = result["soft_miss_reasons"]
            enriched["fundamental_distance"] = result["distances"]
        else:
            enriched["fundamental_flag"] = "pass"

        passed.append(enriched)

    return non_buy + passed, rejected


async def _fetch_inputs(
    tickers: list[str],
) -> tuple[dict[str, dict], dict[str, SectorThresholdRow]]:
    """Batch-fetch ratios + sector thresholds in parallel.

    Returns two dicts keyed by upper-case ticker. Missing sector row =
    "no override for this ticker" — caller falls back to cfg defaults.
    """
    import asyncio

    ratios_batch, sector_thresholds = await asyncio.gather(
        get_financial_ratios_batch(tickers),
        get_sector_thresholds_batch(tickers),
    )
    return ratios_batch, sector_thresholds


def _classify_stock_category(ticker: str, ratios: dict, core_ratio: float | None) -> str:
    """Classify stock: GROWTH, VALUE_TRAP, or SPECULATIVE.

    GROWTH: ROE > 10%, positive margin, core earnings ratio > 0.6
    VALUE_TRAP: Low PE but weak ROE or low core ratio
    SPECULATIVE: core_ratio < 0.3 (majority non-core income)
    """
    roe_pct = ratios.get("roe") or 0
    nm_pct = ratios.get("net_margin") or 0
    pe = ratios.get("pe") or 99
    cr = core_ratio if core_ratio is not None else 1.0

    if cr < 0.3:
        return "SPECULATIVE"
    if pe < 10 and (roe_pct < 8 or cr < 0.4):
        return "VALUE_TRAP"
    if roe_pct >= 10 and nm_pct >= 5 and cr >= 0.6:
        return "GROWTH"
    return "GROWTH"


def _score_thresholds(
    ratios: dict,
    cfg: TradingConfig,
    sector_row: SectorThresholdRow | None,
) -> ScoreResult:
    """Score each metric 0/1/2 and aggregate.

    0 = pass (value meets threshold)
    1 = soft miss (within cfg.screen_tolerance_pct of the threshold)
    2 = hard miss (beyond tolerance band)

    Sector overrides replace the matching default threshold when present.
    Banks historically got D/E=12.0 via a hardcoded frozenset — that is
    now expressed as the banking sector's `max_de` override row.
    """
    tolerance = float(cfg.screen_tolerance_pct or 0.10)
    overrides = sector_row or {}

    max_pe = float(overrides.get("max_pe", cfg.screen_max_pe))
    max_pb = float(overrides.get("max_pb", cfg.screen_max_pb))
    min_roe_pct = float(overrides.get("min_roe_pct", cfg.screen_min_roe_pct))
    min_margin_pct = float(overrides.get("min_margin_pct", cfg.screen_min_margin_pct))
    # The legacy screen_bank_max_de default is now unused once the
    # banking sector row carries max_de=12.0 (migration 327). Until that
    # migration runs we still fall back to the banking override via
    # sector_row; non-bank sectors fall back to screen_max_de.
    max_de = float(overrides.get("max_de", cfg.screen_max_de))

    distances: dict[str, float] = {}
    scores: dict[str, int] = {}
    soft_miss_reasons: list[str] = []
    hard_fail_metrics: list[str] = []

    # PE (skip check when value is non-positive — loss-making handled by margin)
    pe = ratios.get("pe")
    if pe is not None and pe > 0:
        _record(
            metric="PE",
            value=pe,
            threshold=max_pe,
            direction="max",
            tolerance=tolerance,
            distances=distances,
            scores=scores,
            soft=soft_miss_reasons,
            hard=hard_fail_metrics,
            fmt_value=f"{pe:.1f}",
            fmt_threshold=f"{max_pe:.0f}",
        )

    pb = ratios.get("pb")
    if pb is not None and pb > 0:
        _record(
            metric="PB",
            value=pb,
            threshold=max_pb,
            direction="max",
            tolerance=tolerance,
            distances=distances,
            scores=scores,
            soft=soft_miss_reasons,
            hard=hard_fail_metrics,
            fmt_value=f"{pb:.1f}",
            fmt_threshold=f"{max_pb:.1f}",
        )

    roe_pct = ratios.get("roe")
    if roe_pct is not None:
        _record(
            metric="ROE",
            value=roe_pct,
            threshold=min_roe_pct,
            direction="min",
            tolerance=tolerance,
            distances=distances,
            scores=scores,
            soft=soft_miss_reasons,
            hard=hard_fail_metrics,
            fmt_value=f"{roe_pct:.1f}%",
            fmt_threshold=f"{min_roe_pct:.0f}%",
        )

    nm_pct = ratios.get("net_margin")
    if nm_pct is not None:
        _record(
            metric="Margin",
            value=nm_pct,
            threshold=min_margin_pct,
            direction="min",
            tolerance=tolerance,
            distances=distances,
            scores=scores,
            soft=soft_miss_reasons,
            hard=hard_fail_metrics,
            fmt_value=f"{nm_pct:.1f}%",
            fmt_threshold=f"{min_margin_pct:.0f}%",
        )

    de = ratios.get("debt_to_equity")
    if de is not None:
        _record(
            metric="D/E",
            value=de,
            threshold=max_de,
            direction="max",
            tolerance=tolerance,
            distances=distances,
            scores=scores,
            soft=soft_miss_reasons,
            hard=hard_fail_metrics,
            fmt_value=f"{de:.1f}",
            fmt_threshold=f"{max_de:.1f}",
        )

    composite = float(sum(scores.values()))
    return ScoreResult(
        composite=composite,
        distances=distances,
        scores=scores,
        soft_miss_reasons=soft_miss_reasons,
        hard_fail_metrics=hard_fail_metrics,
    )


def _record(
    *,
    metric: str,
    value: float,
    threshold: float,
    direction: str,
    tolerance: float,
    distances: dict[str, float],
    scores: dict[str, int],
    soft: list[str],
    hard: list[str],
    fmt_value: str,
    fmt_threshold: str,
) -> None:
    """Classify one metric and push into the aggregate buckets.

    ``direction='max'`` means the candidate fails when value > threshold.
    ``direction='min'`` means the candidate fails when value < threshold.
    Distance is the positive, fractional, on-the-bad-side miss; 0 on a
    pass. Soft fails produce a human-readable reason the caller surfaces
    to advocate/critic.
    """
    if threshold <= 0:
        distances[metric] = 0.0
        scores[metric] = 0
        return

    if direction == "max":
        raw_distance = (value - threshold) / threshold
    else:
        raw_distance = (threshold - value) / threshold

    distance = max(0.0, raw_distance)
    distances[metric] = distance

    if distance <= 0:
        scores[metric] = 0
        return

    if distance <= tolerance:
        scores[metric] = 1
        soft.append(f"{metric} {fmt_value} vs {fmt_threshold} (soft miss +{distance * 100:.0f}%)")
        return

    scores[metric] = 2
    hard.append(f"{metric} {fmt_value} vs {fmt_threshold} (+{distance * 100:.0f}%)")


def _format_rejection(result: ScoreResult) -> list[str]:
    """Build a list of rejection reasons from a failed score result."""
    reasons: list[str] = list(result["hard_fail_metrics"])
    reasons.extend(result["soft_miss_reasons"])
    if not reasons and result["composite"] > 0:
        reasons.append(f"composite {result['composite']:.1f} over limit")
    return reasons
