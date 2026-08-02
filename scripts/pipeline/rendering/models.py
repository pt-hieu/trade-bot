"""Structured types for deterministic brief rendering.

`HoldingAction` is the authoritative source for holding decisions once
derived — every brief section that refers to a holding (MY HOLDINGS,
WHAT TO DO TODAY, MINDSET verb-coherence check) must read from the
same `list[HoldingAction]` and never reparse prose.

Derived from `position_alerts` (produced upstream by the positions
ensemble aggregator), not from an LLM's prose restatement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from shared.text_utils import split_first_sentence
from shared.types.holding_verb import HoldingVerb

Urgency = Literal["HIGH", "MEDIUM", "LOW"]

__all__ = [
    "GeoBadge",
    "HoldingAction",
    "HoldingVerb",
    "Urgency",
    "derive_holding_actions",
]

# Verbs that accept or imply a quantity adjustment. HOLD/EXIT/EVALUATE do not.
_QTY_VERBS: frozenset[str] = frozenset({"TRIM", "ADD"})


GeoBadge = Literal["VICTIM"]


@dataclass(frozen=True)
class HoldingAction:
    """One decision for one held ticker.

    Attributes:
        ticker: Stock symbol (e.g. "FPT").
        verb: HOLD / TRIM / ADD / EXIT / EVALUATE.
        qty_pct: % of position to TRIM or ADD (None for HOLD/EXIT/EVALUATE).
        rationale: One-sentence "why" — used as WHAT TO DO TODAY bullet.
        stop_price_vnd: Catastrophic stop reference (optional, only
            rendered for non-HOLD actions).
        urgency: HIGH / MEDIUM / LOW from position_alerts.
        entry_price_vnd: Avg entry cost from portfolio row (MY HOLDINGS).
        current_price_vnd: Latest close (MY HOLDINGS).
        pnl_pct: Realized + unrealized P/L % (MY HOLDINGS).
        catastrophic_floor_vnd: Hard-stop price from portfolio row.
        breakeven_stop_vnd: Breakeven floor (entry + fees) when active.
        trailing_stop_vnd: Trailing stop price when active; None when not.
        geo_badge: ``VICTIM`` only when ticker is in the geo-shock
            downside-exposure set. Populated from structured data,
            never from LLM prose.
    """

    ticker: str
    verb: HoldingVerb
    qty_pct: int | None = None
    rationale: str = ""
    stop_price_vnd: int | None = None
    urgency: Urgency = "MEDIUM"
    entry_price_vnd: int | None = None
    current_price_vnd: int | None = None
    pnl_pct: float | None = None
    catastrophic_floor_vnd: int | None = None
    breakeven_stop_vnd: int | None = None
    trailing_stop_vnd: int | None = None
    geo_badge: GeoBadge | None = None

    def bullet_verb(self) -> str:
        """Human-readable verb for bullet rendering, including qty if any."""
        if self.verb in _QTY_VERBS and self.qty_pct is not None:
            return f"{self.verb} {self.ticker} {self.qty_pct}%"
        return f"{self.verb} {self.ticker}"


def _extract_qty_pct(reason: str) -> int | None:
    """Extract a `30%` / `50 percent` pattern from a free-text reason."""
    import re

    match = re.search(r"(\d{1,3})\s*%", reason or "")
    if match:
        try:
            value = int(match.group(1))
            if 1 <= value <= 100:
                return value
        except ValueError:
            return None
    return None


def _coerce_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _coerce_urgency(value: object) -> Urgency:
    if isinstance(value, str):
        upper = value.upper()
        if upper in ("HIGH", "MEDIUM", "LOW"):
            return upper  # type: ignore[return-value]
    return "MEDIUM"


def derive_holding_actions(
    position_alerts: dict | None,
    holdings_tickers: list[str] | None = None,
    *,
    portfolio_rows: dict | None = None,
    impacted_tickers_victim: set[str] | None = None,
) -> list[HoldingAction]:
    """Convert upstream `position_alerts` dict into `list[HoldingAction]`.

    `position_alerts` is produced by the positions ensemble aggregator
    and has the shape `{"alerts": [{"ticker", "action", "urgency",
    "reason", ...}, ...]}`. This function is the single canonical
    extraction — all brief renderers read from its output so verb
    coherence is guaranteed.

    Holdings present in `holdings_tickers` but missing from alerts get
    an implicit HOLD (no alert means no action required).

    Optional kwargs for the MY HOLDINGS renderer:
      portfolio_rows: ``{ticker: portfolio_row_dict}`` with keys like
        ``avg_cost_vnd``, ``current_price_vnd``, ``pnl_pct``,
        ``catastrophic_floor_vnd``, ``breakeven_stop_vnd``,
        ``trailing_stop_vnd``. Missing rows or fields simply make the
        renderer omit those lines — preferred over LLM paraphrase.
      impacted_tickers_victim: geo-shock downside-exposure set. A
        ``GEO_VICTIM`` badge is rendered only when a ticker is in this
        set; the default empty set renders no badges at all.
    """
    alerts_list: list[dict] = []
    if position_alerts:
        alerts_list = list(position_alerts.get("alerts") or [])

    victim_set = {t.upper() for t in (impacted_tickers_victim or set())}

    def _portfolio_row(ticker: str) -> dict:
        if not portfolio_rows:
            return {}
        row = portfolio_rows.get(ticker)
        return row or {}

    def _geo_badge(ticker: str) -> GeoBadge | None:
        return "VICTIM" if ticker in victim_set else None

    def _build_action(
        ticker: str,
        verb: HoldingVerb,
        qty_pct: int | None,
        rationale: str,
        stop_price_vnd: int | None,
        urgency: Urgency,
    ) -> HoldingAction:
        row = _portfolio_row(ticker)
        return HoldingAction(
            ticker=ticker,
            verb=verb,
            qty_pct=qty_pct,
            rationale=rationale,
            stop_price_vnd=stop_price_vnd,
            urgency=urgency,
            entry_price_vnd=_coerce_int(row.get("avg_cost_vnd") or row.get("entry_price_vnd")),
            current_price_vnd=_coerce_int(
                row.get("current_price_vnd") or row.get("last_price_vnd")
            ),
            # `pct_from_entry` is the canonical key emitted by
            # shared.neon.portfolio.get_portfolio_holdings. The old keys
            # (`pnl_pct`, `unrealized_pnl_pct`) were never set by the
            # producer — the resulting None caused the MY HOLDINGS brief
            # to render LLM-paraphrased stale numbers (MON-2026-04-19-003).
            pnl_pct=_coerce_float(row.get("pct_from_entry")),
            catastrophic_floor_vnd=_coerce_int(row.get("catastrophic_floor_vnd")),
            breakeven_stop_vnd=_coerce_int(row.get("breakeven_stop_vnd")),
            trailing_stop_vnd=_coerce_int(row.get("trailing_stop_vnd")),
            geo_badge=_geo_badge(ticker),
        )

    actions: list[HoldingAction] = []
    seen: set[str] = set()

    for alert in alerts_list:
        ticker = (alert.get("ticker") or "").upper()
        if not ticker:
            continue
        raw_verb = (alert.get("action") or "HOLD").upper()
        if raw_verb not in ("HOLD", "TRIM", "ADD", "EXIT", "EVALUATE"):
            raw_verb = "HOLD"
        verb: HoldingVerb = raw_verb  # type: ignore[assignment]
        reason = alert.get("reason") or ""
        qty_pct = _extract_qty_pct(reason) if verb in _QTY_VERBS else None

        rationale_snippet = split_first_sentence(reason, max_len=240)
        actions.append(
            _build_action(
                ticker=ticker,
                verb=verb,
                qty_pct=qty_pct,
                rationale=rationale_snippet,
                stop_price_vnd=_coerce_int(alert.get("stop_price_vnd")),
                urgency=_coerce_urgency(alert.get("urgency")),
            )
        )
        seen.add(ticker)

    # Holdings with no alert → implicit HOLD (present but no action needed).
    if holdings_tickers:
        for ticker in holdings_tickers:
            canonical = (ticker or "").upper()
            if not canonical or canonical in seen:
                continue
            actions.append(
                _build_action(
                    ticker=canonical,
                    verb="HOLD",
                    qty_pct=None,
                    rationale="No action required today",
                    stop_price_vnd=None,
                    urgency="LOW",
                )
            )

    return actions
