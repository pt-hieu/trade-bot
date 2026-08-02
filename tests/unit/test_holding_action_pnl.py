"""Tests for HoldingAction.pnl_pct derivation from portfolio rows.

Group 8 of 2026-04-19 pipeline review fixes. Resolves MON-2026-04-19-003
(FPT brief showed -12.3% while portfolio showed -10.1%). Root cause:
`derive_holding_actions` read non-existent `pnl_pct`/`unrealized_pnl_pct`
keys instead of the canonical `pct_from_entry` from
`shared.neon.portfolio.get_portfolio_holdings`.
"""

from __future__ import annotations

from pipeline.rendering.models import derive_holding_actions


def test_pct_from_entry_becomes_holding_action_pnl_pct():
    """FPT portfolio row with pct_from_entry=-10.1 → HoldingAction.pnl_pct=-10.1."""
    portfolio_rows = {
        "FPT": {
            "shares": 100,
            "avg_cost_vnd": 80000,
            "current_price_vnd": 71920,
            "pct_from_entry": -10.1,
        }
    }
    actions = derive_holding_actions(
        position_alerts={"alerts": [{"ticker": "FPT", "action": "HOLD"}]},
        holdings_tickers=["FPT"],
        portfolio_rows=portfolio_rows,
    )
    assert len(actions) == 1
    assert actions[0].ticker == "FPT"
    assert actions[0].pnl_pct == -10.1


def test_legacy_pnl_pct_key_no_longer_read():
    """The producer emits only `pct_from_entry`; legacy keys must not sneak in."""
    # Row only has the legacy key (simulating stale producer). The renderer
    # must NOT fall back to it — renderer gets None, and my_holdings will
    # omit the P/L line rather than render a paraphrased stale number.
    portfolio_rows = {
        "FPT": {
            "avg_cost_vnd": 80000,
            "current_price_vnd": 71920,
            "pnl_pct": -99.9,  # legacy key; must be ignored
        }
    }
    actions = derive_holding_actions(
        position_alerts={"alerts": [{"ticker": "FPT", "action": "HOLD"}]},
        holdings_tickers=["FPT"],
        portfolio_rows=portfolio_rows,
    )
    assert actions[0].pnl_pct is None


def test_missing_portfolio_row_pnl_is_none():
    actions = derive_holding_actions(
        position_alerts={"alerts": [{"ticker": "FPT", "action": "HOLD"}]},
        holdings_tickers=["FPT"],
        portfolio_rows={},
    )
    assert actions[0].pnl_pct is None
