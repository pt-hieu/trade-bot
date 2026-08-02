"""SWI-304 rally_readmit pre-pass.

Counterweight to the weekly LLM watchlist rotation: if a ticker that lives in a
deactivated `swing_watchlist` row is rallying or sits on a HIGH-confidence
positive catalyst, re-admit it BEFORE the morning scan reads the watchlist.
This is the event-driven complement to weekly cadence — rallies do not wait a
week for the LLM to notice.

Triggers (any one fires):
  - rally_volume:     deactivated swing row + ret_5d >= cfg.rally_readmit_ret_5d_min
                      + vol_ratio_20d >= cfg.rally_readmit_vol_ratio_min
  - catalyst:         deactivated swing row + active HIGH-confidence positive catalyst
  - longterm_rally:   rallying longterm ticker WITH a prior swing_watchlist row
  - rally_volume_new: ticker present in `stocks` but NOT in swing_watchlist or
                      longterm_watchlist, rallying hard enough to pass the stricter
                      `rally_readmit_new_ticker_*` thresholds. SWI-322 (2026-05-11)
                      inverts the SWI-304 "never widen the tradable set" invariant
                      for Phase 0 only; catalyst revision still honors it.

Action: idempotent `add_swing_stock(ticker, sector)` — the existing
ON CONFLICT DO UPDATE flips is_active back to TRUE. Pure I/O fetchers and
numeric helpers live in `_data_sources.py`; this module owns orchestration.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import date
from typing import Literal

from . import _data_sources as ds

try:
    import logfire as _logfire
except ImportError:  # logfire optional in unit tests / local dev
    _logfire = None

logger = logging.getLogger(__name__)


Trigger = Literal["rally_volume", "catalyst", "longterm_rally", "rally_volume_new"]
SkipReason = Literal["no_sector", "cap_hit"]


@dataclass(frozen=True)
class ReadmitRecord:
    ticker: str
    trigger: Trigger
    sector: str | None
    ret_5d: float | None
    vol_ratio_20d: float | None
    catalyst_id: str | None
    admitted: bool
    skip_reason: SkipReason | None = None


def _score(rec: ReadmitRecord) -> float:
    ret = rec.ret_5d or 0.0
    vol = min(rec.vol_ratio_20d or 1.0, 3.0)
    bias = 0.05 if rec.trigger in ("catalyst", "rally_volume_new") else 0.0
    return ret * vol + bias


def _score_candidates(
    *,
    cfg,
    deactivated_tickers: set[str],
    deactivated_sectors: dict[str, str | None],
    longterm_with_prior: set[str],
    longterm_map: dict[str, str | None],
    catalyst_map: dict[str, str],
    new_universe_map: dict[str, str | None],
    metrics: dict[str, tuple[float | None, float | None]],
    technicals_failed: bool,
) -> list[ReadmitRecord]:
    candidates: list[ReadmitRecord] = []
    for ticker in deactivated_tickers:
        ret_5d, vol_ratio = metrics.get(ticker, (None, None))
        sector = deactivated_sectors.get(ticker)

        catalyst_id = catalyst_map.get(ticker)
        if catalyst_id:
            candidates.append(
                ReadmitRecord(
                    ticker=ticker,
                    trigger="catalyst",
                    sector=sector,
                    ret_5d=ret_5d,
                    vol_ratio_20d=vol_ratio,
                    catalyst_id=catalyst_id,
                    admitted=False,
                )
            )
            continue

        if technicals_failed:
            continue  # catalyst-only fallback

        if (
            ret_5d is not None
            and vol_ratio is not None
            and ret_5d >= cfg.rally_readmit_ret_5d_min
            and vol_ratio >= cfg.rally_readmit_vol_ratio_min
        ):
            candidates.append(
                ReadmitRecord(
                    ticker=ticker,
                    trigger="rally_volume",
                    sector=sector,
                    ret_5d=ret_5d,
                    vol_ratio_20d=vol_ratio,
                    catalyst_id=None,
                    admitted=False,
                )
            )

    if technicals_failed:
        return candidates

    # New-universe path (SWI-322). Inverts the SWI-304 "never widen the tradable set"
    # invariant for Phase 0 only — see module docstring.
    for ticker in sorted(new_universe_map):
        ret_5d, vol_ratio = metrics.get(ticker, (None, None))
        if ret_5d is None or vol_ratio is None:
            continue
        if (
            ret_5d >= cfg.rally_readmit_new_ticker_ret_5d_min
            and vol_ratio >= cfg.rally_readmit_new_ticker_vol_ratio_min
        ):
            candidates.append(
                ReadmitRecord(
                    ticker=ticker,
                    trigger="rally_volume_new",
                    sector=new_universe_map[ticker],
                    ret_5d=ret_5d,
                    vol_ratio_20d=vol_ratio,
                    catalyst_id=None,
                    admitted=False,
                )
            )

    for ticker in sorted(longterm_with_prior):
        ret_5d, vol_ratio = metrics.get(ticker, (None, None))
        if ret_5d is None or ret_5d < cfg.rally_readmit_ret_5d_min:
            continue
        candidates.append(
            ReadmitRecord(
                ticker=ticker,
                trigger="longterm_rally",
                sector=longterm_map.get(ticker),
                ret_5d=ret_5d,
                vol_ratio_20d=vol_ratio,
                catalyst_id=None,
                admitted=False,
            )
        )
    return candidates


def _emit_logfire_summary(
    *,
    admitted_records: list[ReadmitRecord],
    skipped_records: list[ReadmitRecord],
    total_evaluated: int,
    cap: int,
    technicals_failed: bool,
) -> None:
    if _logfire is None:
        return
    for rec in admitted_records + skipped_records:
        _logfire.info(
            "rally_readmit_candidate",
            ticker=rec.ticker,
            trigger=rec.trigger,
            ret_5d=rec.ret_5d,
            vol_ratio=rec.vol_ratio_20d,
            catalyst_id=rec.catalyst_id,
            admitted=rec.admitted,
            skip_reason=rec.skip_reason,
        )
    _logfire.info(
        "rally_readmit_summary",
        total_evaluated=total_evaluated,
        total_admitted=sum(1 for r in admitted_records if r.admitted),
        cap_hit=total_evaluated > cap,
        technicals_failed=technicals_failed,
    )


async def run_rally_readmit(scan_date: date) -> list[ReadmitRecord]:
    """Execute Phase 0 rally_readmit pass.

    MUST run BEFORE `load_db_context` reads `get_swing_watchlist()`.
    Mutates `swing_watchlist.is_active`. Idempotent.
    """
    from shared.neon import add_swing_stock
    from shared.trading_config import get_trading_config

    cfg = get_trading_config()

    span = (
        _logfire.span("rally_readmit", scan_date=str(scan_date))
        if _logfire is not None
        else nullcontext()
    )

    with span:
        (
            deactivated_rows,
            active_swing,
            prior_swing,
            longterm_map,
            catalyst_map,
            new_universe_map,
        ) = await asyncio.gather(
            ds.fetch_deactivated_swing_rows(),
            ds.fetch_active_swing_tickers(),
            ds.fetch_prior_swing_tickers(),
            ds.fetch_longterm_with_sector(),
            ds.fetch_high_positive_catalyst_tickers(),
            ds.fetch_new_universe_candidates(),
        )

        deactivated_sectors = {row["ticker"].upper(): row["sector"] for row in deactivated_rows}
        deactivated_tickers = set(deactivated_sectors.keys())

        longterm_with_prior = {
            t for t in longterm_map if t in prior_swing and t not in active_swing
        }
        new_universe_tickers = set(new_universe_map.keys())
        metrics_tickers = sorted(deactivated_tickers | longterm_with_prior | new_universe_tickers)
        metrics = await ds.fetch_metrics(metrics_tickers)
        technicals_failed = bool(metrics_tickers) and not metrics

        candidates = _score_candidates(
            cfg=cfg,
            deactivated_tickers=deactivated_tickers,
            deactivated_sectors=deactivated_sectors,
            longterm_with_prior=longterm_with_prior,
            longterm_map=longterm_map,
            catalyst_map=catalyst_map,
            new_universe_map=new_universe_map,
            metrics=metrics,
            technicals_failed=technicals_failed,
        )

        # Deduplicate by ticker, prefer the higher-scoring trigger.
        by_ticker: dict[str, ReadmitRecord] = {}
        for rec in candidates:
            existing = by_ticker.get(rec.ticker)
            if existing is None or _score(rec) > _score(existing):
                by_ticker[rec.ticker] = rec
        deduped = sorted(by_ticker.values(), key=_score, reverse=True)

        cap = cfg.rally_readmit_daily_cap
        admitted_records: list[ReadmitRecord] = []
        skipped_records: list[ReadmitRecord] = []

        for rec in deduped[:cap]:
            sector = rec.sector or await ds.fetch_stock_sector(rec.ticker)
            if not sector:
                logger.warning("rally_readmit: no sector for %s — skipping admit", rec.ticker)
                skipped_records.append(replace(rec, skip_reason="no_sector"))
                continue
            try:
                ok = await add_swing_stock(rec.ticker, sector)
            except Exception as exc:
                logger.warning("rally_readmit: add_swing_stock failed for %s: %s", rec.ticker, exc)
                ok = False
            admitted_records.append(replace(rec, sector=sector, admitted=bool(ok)))

        for rec in deduped[cap:]:
            skipped_records.append(replace(rec, skip_reason="cap_hit"))

        _emit_logfire_summary(
            admitted_records=admitted_records,
            skipped_records=skipped_records,
            total_evaluated=len(deduped),
            cap=cap,
            technicals_failed=technicals_failed,
        )

        if admitted_records:
            logger.info(
                "rally_readmit: admitted %d ticker(s): %s",
                sum(1 for r in admitted_records if r.admitted),
                ", ".join(r.ticker for r in admitted_records if r.admitted),
            )

        return admitted_records + skipped_records
