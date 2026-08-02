#!/usr/bin/env python3
"""
Post-hoc Python validators for watchlist update pipeline.

Deterministic enforcement of rules that LLM prompts alone cannot guarantee:
- Confidence downgrade on conflicting technicals
- Churn detection (flip-flop between weeks)
- Portfolio conflict auto-removal
- Sector cap enforcement (max additions per sector)
"""

import logging

from .watchlist_update import SECTOR_MAP, StockScore

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

CHURN_SCORE_PENALTY = 15
MAX_ADDITIONS_PER_SECTOR = 2


# ── Confidence validation ────────────────────────────────────────────────────


def validate_confidence(additions: list[StockScore], technicals: dict) -> list[StockScore]:
    """Downgrade 'high' confidence if conflicting technical indicators present."""
    validated = []
    for stock in additions:
        if stock.confidence != "high":
            validated.append(stock)
            continue
        data = technicals.get(stock.ticker) or {}
        conflicts = 0
        reasons = list(stock.reasons)

        supertrend_data = data.get("supertrend") or {}
        if (
            isinstance(supertrend_data, dict)
            and (supertrend_data.get("direction") or "").upper() == "DOWN"
        ):
            conflicts += 1
            reasons.append("[POST-HOC] Supertrend bearish — downgraded from high")

        adx_data = data.get("adx") or {}
        adx_value = adx_data.get("adx") if isinstance(adx_data, dict) else None
        if adx_value is not None and adx_value < 20:
            conflicts += 1
            reasons.append(f"[POST-HOC] Weak trend (ADX {adx_value:.0f}) — downgraded from high")

        close = data.get("close") or data.get("price")
        sma50 = data.get("sma50")
        if close and sma50 and close < sma50:
            conflicts += 1
            reasons.append("[POST-HOC] Price below MA50 — downgraded from high")

        if conflicts > 0:
            new_confidence = "low" if conflicts >= 2 else "medium"
            logger.info(
                "Confidence downgrade: %s high->%s (%d conflicts)",
                stock.ticker,
                new_confidence,
                conflicts,
            )
            validated.append(
                stock.model_copy(update={"confidence": new_confidence, "reasons": reasons})
            )
        else:
            validated.append(stock)
    return validated


# ── Churn detection ──────────────────────────────────────────────────────────


def _apply_churn_flag(
    stocks: list[StockScore],
    conflict_set: set[str],
    note: str,
    log_suffix: str,
) -> list[StockScore]:
    """Annotate flip-flopped stocks, penalize score, and downgrade confidence."""
    out = []
    for stock in stocks:
        if stock.ticker in conflict_set:
            original_score = stock.score
            reasons = list(stock.reasons) + [
                note,
                f"(-{CHURN_SCORE_PENALTY}) churn penalty",
            ]
            penalized = stock.model_copy(
                update={
                    "confidence": ("medium" if stock.confidence == "high" else stock.confidence),
                    "reasons": reasons,
                }
            )
            out.append(penalized)
            logger.info(
                "Churn detected: %s %s (score %d->%d)",
                stock.ticker,
                log_suffix,
                original_score,
                penalized.score,
            )
        else:
            out.append(stock)
    return out


def detect_churn(
    additions: list[StockScore],
    removals: list[StockScore],
    previous_report: dict | None,
) -> tuple[list[StockScore], list[StockScore]]:
    """Flag and annotate flip-flop decisions vs previous week."""
    if not previous_report:
        return additions, removals

    previously_added = {record["ticker"] for record in previous_report.get("additions", [])}
    previously_removed = {record["ticker"] for record in previous_report.get("removals", [])}

    return (
        _apply_churn_flag(
            additions,
            previously_removed,
            "[CHURN] Was removed last week — re-add needs justification",
            "removed->added in consecutive weeks",
        ),
        _apply_churn_flag(
            removals,
            previously_added,
            "[CHURN] Was added last week — removal needs strong justification",
            "added->removed in consecutive weeks",
        ),
    )


# ── Portfolio conflict auto-removal ──────────────────────────────────────────


def remove_portfolio_conflicts(
    current_watchlist: set[str],
    held_tickers: set[str],
    removals: list[StockScore],
) -> list[StockScore]:
    """Auto-add held tickers on watchlist to removals list.

    Tickers already in portfolio should not remain on swing watchlist —
    they are actively managed as positions, not candidates.
    """
    existing_removal_tickers = {removal.ticker for removal in removals}
    portfolio_conflicts = (current_watchlist & held_tickers) - existing_removal_tickers

    additional_removals = []
    for ticker in sorted(portfolio_conflicts):
        sector = SECTOR_MAP.get(ticker, "Other")
        additional_removals.append(
            StockScore(
                ticker=ticker,
                sector=sector,
                confidence="high",
                reasons=["[AUTO] Portfolio conflict — ticker is actively held (+100)"],
            )
        )
        logger.info(
            "Portfolio conflict: auto-removing %s from watchlist (actively held)",
            ticker,
        )

    return removals + additional_removals


# ── Sector cap enforcement ───────────────────────────────────────────────────


def enforce_sector_cap(
    additions: list[StockScore],
    max_per_sector: int = MAX_ADDITIONS_PER_SECTOR,
) -> list[StockScore]:
    """Keep top N additions per sector by score, drop the rest.

    Deterministic enforcement of the diversification cap that the
    coordinator prompt requests but LLM sometimes ignores.
    """
    sector_buckets: dict[str, list[StockScore]] = {}
    for addition in additions:
        sector_buckets.setdefault(addition.sector, []).append(addition)

    capped_additions: list[StockScore] = []
    for sector, sector_additions in sector_buckets.items():
        sorted_by_score = sorted(sector_additions, key=lambda stock: stock.score, reverse=True)
        if len(sorted_by_score) > max_per_sector:
            kept = sorted_by_score[:max_per_sector]
            dropped = sorted_by_score[max_per_sector:]
            logger.info(
                "Sector cap: %s has %d additions, keeping top %d (dropped: %s)",
                sector,
                len(sorted_by_score),
                max_per_sector,
                [stock.ticker for stock in dropped],
            )
            capped_additions.extend(kept)
        else:
            capped_additions.extend(sorted_by_score)

    return capped_additions


# ── Duplicate addition filter ─────────────────────────────────────────────────


def filter_existing_additions(
    additions: list[StockScore],
    current_watchlist: set[str],
) -> list[StockScore]:
    """Remove additions that are already on the watchlist.

    LLM evaluators sometimes propose 'adding' a stock that is already tracked.
    The DB upsert masks this, but it wastes an addition slot.
    """
    filtered = []
    for stock in additions:
        if stock.ticker in current_watchlist:
            logger.info(
                "Duplicate addition blocked: %s is already on watchlist",
                stock.ticker,
            )
        else:
            filtered.append(stock)
    return filtered


# ── RSI overbought enforcement ────────────────────────────────────────────────

RSI_OVERBOUGHT = 70
RSI_WARNING_ZONE = 60


def flag_overbought_stocks(
    additions: list[StockScore],
    removals: list[StockScore],
    current_watchlist: set[str],
    pinned_tickers: set[str],
    technicals: dict,
) -> tuple[list[StockScore], list[StockScore]]:
    """Deterministic RSI-based overbought scoring.

    - Non-pinned watchlist stocks with RSI > 70: propose removal with +40 score
    - Pinned stocks with RSI > 70: log warning only
    - Additions with RSI 60-70: annotate with warning reason
    - Missing RSI data: log debug for observability
    """
    existing_removal_tickers = {removal.ticker for removal in removals}
    overbought_removals: list[StockScore] = []

    for ticker in current_watchlist:
        data = technicals.get(ticker) or {}
        rsi = data.get("rsi")
        if rsi is None:
            logger.debug("RSI data missing for watchlist ticker: %s", ticker)
            continue
        if rsi > RSI_OVERBOUGHT:
            if ticker in pinned_tickers:
                logger.warning(
                    "RSI overbought on PINNED stock: %s RSI=%.1f (no auto-removal)",
                    ticker,
                    rsi,
                )
            elif ticker not in existing_removal_tickers:
                sector = SECTOR_MAP.get(ticker, "Other")
                overbought_removals.append(
                    StockScore(
                        ticker=ticker,
                        sector=sector,
                        confidence="medium",
                        reasons=[f"[POST-HOC] RSI overbought ({rsi:.1f} > {RSI_OVERBOUGHT}) (+40)"],
                    )
                )
                logger.info("RSI overbought removal proposed: %s RSI=%.1f", ticker, rsi)

    annotated_additions: list[StockScore] = []
    for stock in additions:
        data = technicals.get(stock.ticker) or {}
        rsi = data.get("rsi")
        if rsi is not None and RSI_WARNING_ZONE < rsi <= RSI_OVERBOUGHT:
            reasons = list(stock.reasons) + [f"[WARNING] RSI approaching overbought ({rsi:.1f})"]
            annotated_additions.append(stock.model_copy(update={"reasons": reasons}))
        else:
            annotated_additions.append(stock)

    return annotated_additions, removals + overbought_removals
