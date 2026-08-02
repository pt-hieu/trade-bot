"""Plan-type-aware MAX LOSS ceiling rule.

Pure deterministic core + thin async DB wrapper. Callers must supply
`(ticker, plan_type)` slices — collapsing to ticker-keyed dicts before
calling defeats the purpose of this module (the FPT defect class).
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.neon._utils import safe_float
from shared.trading_config import TradingConfig

SWING_PLAN = "SWING"
LONGTERM_PLAN = "LONGTERM"


@dataclass(frozen=True)
class Breach:
    ticker: str
    plan_type: str
    loss_pct: float
    ceiling_pct: float
    avg_cost_vnd: float
    current_price_vnd: float
    shares: float

    def describe(self) -> str:
        return (
            f"{self.ticker} {self.plan_type}: loss {self.loss_pct:.1f}% "
            f"vs ceiling {self.ceiling_pct:.0f}% "
            f"(entry {self.avg_cost_vnd:,.0f} → current {self.current_price_vnd:,.0f})"
        )

    def to_alert_dict(self) -> dict[str, object]:
        """Render this breach as the alert-dict shape consumed by
        `send_immediate_position_directives`. Keeps the breach → urgent-alert
        translation single-sourced so all callers share one reason wording.
        """
        return {
            "ticker": self.ticker,
            "action": "EXIT",
            "urgency": "high",
            "reason": f"MAX LOSS CEILING BREACH ({self.plan_type}): {self.describe()}",
        }


def slice_loss_pct(avg_cost: float, current_price: float) -> float:
    """Loss as a positive percentage; 0 when break-even or non-positive inputs."""
    if avg_cost <= 0 or current_price <= 0:
        return 0.0
    return max(0.0, (avg_cost - current_price) / avg_cost * 100.0)


def floor_for_slice(
    avg_cost_vnd: float,
    plan_type: str,
    config: TradingConfig,
) -> float | None:
    """Return the absolute VND floor below which a slice has breached its
    plan-type max-loss ceiling, or None when the plan is unknown / cost is
    non-positive.

    Single source for the (avg_cost × (1 − ceiling_pct/100)) arithmetic so
    midday breach detection, position_ensemble rules, and the critic
    holdings-context all stay aligned with `ceiling_for_plan` dispatch.
    """
    if avg_cost_vnd <= 0:
        return None
    ceiling_pct = ceiling_for_plan(plan_type, config)
    if ceiling_pct is None:
        return None
    return avg_cost_vnd * (1 - ceiling_pct / 100.0)


def ceiling_for_plan(plan_type: str, config: TradingConfig) -> float | None:
    """Return the MAX LOSS ceiling for a plan_type, or None if the plan is unknown.

    Also consumed by `scripts/agents/positions_ensemble_rules.py` so the
    two branches (rule engine + midday) share one source of truth.
    """
    plan = (plan_type or "").upper()
    if plan == SWING_PLAN:
        return config.swing_max_loss_pct
    if plan == LONGTERM_PLAN:
        return config.longterm_catastrophic_pct
    return None


def compute_ceiling_breaches_from_rows(
    rows: list[dict],
    config: TradingConfig,
) -> list[Breach]:
    """Apply per-plan MAX LOSS ceilings to raw portfolio slices."""
    breaches: list[Breach] = []
    for row in rows:
        if (row.get("holding_type") or "Stock") == "Cash":
            continue
        ticker = row.get("ticker") or ""
        plan_type = (row.get("plan_type") or "").upper()
        shares = safe_float(row.get("shares"), 0.0) or 0.0
        avg_cost = safe_float(row.get("avg_cost_vnd"), 0.0) or 0.0
        current = safe_float(row.get("current_price_vnd"), 0.0) or 0.0
        if not ticker or shares <= 0 or avg_cost <= 0 or current <= 0:
            continue

        ceiling = ceiling_for_plan(plan_type, config)
        if ceiling is None:
            continue

        loss_pct = slice_loss_pct(avg_cost, current)
        if loss_pct > ceiling:
            breaches.append(
                Breach(
                    ticker=ticker,
                    plan_type=plan_type,
                    loss_pct=loss_pct,
                    ceiling_pct=ceiling,
                    avg_cost_vnd=avg_cost,
                    current_price_vnd=current,
                    shares=shares,
                )
            )
    return breaches


async def fetch_portfolio_slices() -> list[dict]:
    """Read raw `(ticker, plan_type)` portfolio slices directly from Neon."""
    from shared.database import fetch_all

    rows = await fetch_all(
        """
        SELECT ticker, plan_type, shares, avg_cost_vnd, current_price_vnd,
               holding_type
        FROM portfolio_holdings
        WHERE shares > 0 AND holding_type != 'Cash'
        ORDER BY ticker, plan_type
        """
    )
    return [dict(r) for r in rows]


async def compute_ceiling_breaches(config: TradingConfig) -> list[Breach]:
    rows = await fetch_portfolio_slices()
    return compute_ceiling_breaches_from_rows(rows, config)


def format_breaches_for_agent(breaches: list[Breach]) -> str:
    """Compact agent-injection block; empty when no breach so the section can be omitted."""
    if not breaches:
        return ""
    lines = [f"- {breach.describe()} → EXIT required" for breach in breaches]
    return (
        "MAX LOSS CEILING BREACHES (NON-NEGOTIABLE — must emit EXIT override per slice):\n"
        + "\n".join(lines)
    )
