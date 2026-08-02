"""Tests for deterministic WHAT TO DO TODAY renderer.

Replay of 2026-04-15 pipeline review defect (MON-2026-04-16-002):
synthesis_picks wrote "HOLD FPT and TCB" while synthesis_holdings
chose "TRIM 30% FPT". The fix moves WHAT TO DO TODAY generation to a
deterministic Python renderer driven by structured HoldingAction — no
LLM prose can paraphrase-drift from the upstream decision.
"""

from __future__ import annotations

from pipeline.rendering import (
    HoldingAction,
    derive_holding_actions,
    render_what_to_do_today,
)


class TestDeriveHoldingActions:
    def test_extracts_trim_with_qty_pct(self):
        position_alerts = {
            "alerts": [
                {
                    "ticker": "FPT",
                    "action": "TRIM",
                    "urgency": "HIGH",
                    "reason": "Reduce position by 30% due to tech headwinds",
                }
            ]
        }
        actions = derive_holding_actions(position_alerts, holdings_tickers=["FPT"])
        assert len(actions) == 1
        assert actions[0].ticker == "FPT"
        assert actions[0].verb == "TRIM"
        assert actions[0].qty_pct == 30
        assert "tech headwinds" in actions[0].rationale

    def test_holding_without_alert_implicit_hold(self):
        position_alerts = {"alerts": []}
        actions = derive_holding_actions(position_alerts, holdings_tickers=["TCB", "FPT"])
        assert len(actions) == 2
        assert all(a.verb == "HOLD" for a in actions)

    def test_unknown_action_coerces_to_hold(self):
        position_alerts = {"alerts": [{"ticker": "VHM", "action": "BOGUS_ACTION", "reason": ""}]}
        actions = derive_holding_actions(position_alerts)
        assert actions[0].verb == "HOLD"

    def test_dedup_ticker_alerts_prefers_explicit(self):
        position_alerts = {
            "alerts": [{"ticker": "FPT", "action": "TRIM", "reason": "30% reduction"}]
        }
        actions = derive_holding_actions(position_alerts, holdings_tickers=["FPT"])
        # FPT appears once (explicit TRIM beats implicit HOLD).
        assert len(actions) == 1
        assert actions[0].verb == "TRIM"


class TestRenderWhatToDoToday:
    def test_2026_04_15_replay_trim_fpt_not_hold_fpt(self):
        """Canonical replay: FPT must render as TRIM, never HOLD, when
        the upstream action is TRIM. Before deterministic rendering,
        synthesis_picks wrote "HOLD FPT and TCB" from stale MINDSET."""
        actions = [
            HoldingAction(
                ticker="FPT",
                verb="TRIM",
                qty_pct=30,
                rationale="Reduce 30% on tech sector headwinds",
                urgency="HIGH",
            ),
            HoldingAction(
                ticker="TCB",
                verb="HOLD",
                rationale="Banking strength intact",
                urgency="LOW",
            ),
        ]
        output = render_what_to_do_today(
            holdings_actions=actions,
            top_picks=[],
            min_rr_floor=3.5,
        )
        assert "TRIM FPT 30%" in output
        assert "HOLD TCB" in output
        # Critical regression guard: `HOLD FPT` must NEVER appear when
        # FPT's authoritative verb is TRIM.
        assert "HOLD FPT" not in output

    def test_zero_picks_emits_wait_line(self):
        actions = [HoldingAction(ticker="TCB", verb="HOLD")]
        output = render_what_to_do_today(holdings_actions=actions, top_picks=None, min_rr_floor=3.5)
        assert "WAIT" in output
        assert "3.5" in output

    def test_all_top_picks_rendered_as_bullets(self):
        """SWI-274 (run2 2026-05-14): every TOP PICKS BUY must surface in
        WHAT TO DO TODAY. The old `max_picks=2` cap silently dropped the
        3rd pick (VRE shipped as a full BUY in TOP PICKS but vanished here).
        `top_picks` is already bounded upstream by `extract_top_picks` (<=5)."""
        actions = [HoldingAction(ticker="TCB", verb="HOLD")]
        picks = [
            {
                "ticker": "VCB",
                "entry_price_vnd": 85500,
                "risk_reward": 3.8,
                "why": "Breakout",
            },
            {
                "ticker": "MBB",
                "entry_price_vnd": 22000,
                "risk_reward": 3.2,
                "why": "Value",
            },
            # Third pick must now also render — no cap.
            {
                "ticker": "BID",
                "entry_price_vnd": 40000,
                "risk_reward": 3.0,
            },
        ]
        output = render_what_to_do_today(
            holdings_actions=actions, top_picks=picks, min_rr_floor=3.5
        )
        assert "BUY VCB" in output
        assert "BUY MBB" in output
        assert "BUY BID" in output  # no longer capped

    def test_section_header_present(self):
        output = render_what_to_do_today(holdings_actions=[], top_picks=[], min_rr_floor=3.0)
        assert output.startswith("WHAT TO DO TODAY")

    def test_exit_verb_renders_correctly(self):
        actions = [
            HoldingAction(
                ticker="VHM",
                verb="EXIT",
                rationale="Breakdown below 110k support",
                urgency="HIGH",
                stop_price_vnd=107000,
            ),
        ]
        output = render_what_to_do_today(holdings_actions=actions, top_picks=[], min_rr_floor=3.5)
        assert "EXIT VHM" in output
        assert "107,000" in output

    def test_max_new_entries_zero_capital_preservation(self):
        actions = [HoldingAction(ticker="TCB", verb="HOLD")]
        output = render_what_to_do_today(
            holdings_actions=actions,
            top_picks=[],
            min_rr_floor=3.5,
            max_new_entries=0,
        )
        assert "Capital preservation" in output
        assert "max 0 new entries" in output

    def test_top_picks_atr_trail_renders_trailing(self):
        """SWI-340 + 2026-05-14 regression: ATR_TRAIL pick (risk_reward=None)
        must render as `R:R trailing`, NEVER `R:R 0.0`. Today's morning brief
        shipped `BUY VHM at 118,200 (R:R 0.0)` because `_pick_bullets` did
        `pick.get("risk_reward") or 0`. The fix routes through `read_rr()`
        and branches on the sentinel."""
        actions = [HoldingAction(ticker="TCB", verb="HOLD")]
        picks = [
            {
                "ticker": "VHM",
                "entry_price_vnd": 118200,
                "exit_family": "ATR_TRAIL",
                "strategy": "TREND",
                "risk_reward": None,
                "target": None,
                "why": "Trailing breakout",
            },
        ]
        output = render_what_to_do_today(
            holdings_actions=actions, top_picks=picks, min_rr_floor=3.5
        )
        assert "R:R trailing" in output
        assert "R:R 0.0" not in output

    def test_top_picks_producer_leak_renders_na(self):
        """Non-trailing pick missing risk_reward = upstream producer leak.
        Render as `R:R n/a` (not `R:R 0.0`) so the brief surfaces the gap."""
        actions = [HoldingAction(ticker="TCB", verb="HOLD")]
        picks = [
            {
                "ticker": "FPT",
                "entry_price_vnd": 80000,
                "exit_family": "FIXED_TARGET",
                "strategy": "PULLBACK",
                "target": 92000,
                # risk_reward absent → producer leak
                "why": "Support reclaim",
            },
        ]
        output = render_what_to_do_today(
            holdings_actions=actions, top_picks=picks, min_rr_floor=3.5
        )
        assert "R:R n/a" in output
        assert "R:R 0.0" not in output

    def test_top_picks_fixed_target_unchanged(self):
        """Regression guard for the fixed-target happy path — `R:R 3.8`
        must still render exactly as before the refactor."""
        actions = [HoldingAction(ticker="TCB", verb="HOLD")]
        picks = [
            {
                "ticker": "VCB",
                "entry_price_vnd": 85500,
                "exit_family": "FIXED_TARGET",
                "target": 95000,
                "risk_reward": 3.8,
                "why": "Breakout",
            },
        ]
        output = render_what_to_do_today(
            holdings_actions=actions, top_picks=picks, min_rr_floor=3.5
        )
        assert "R:R 3.8" in output

    def test_sub_floor_pick_dropped_above_floor_kept(self):
        """SWI-327: a pick with a genuine R:R below the floor must not render
        as an actionable BUY; an above-floor pick still does."""
        actions = [HoldingAction(ticker="TCB", verb="HOLD")]
        picks = [
            {
                "ticker": "SUB",
                "entry_price_vnd": 50000,
                "exit_family": "FIXED_TARGET",
                "target": 52000,
                "risk_reward": 2.0,  # below 3.5 floor
                "why": "Thin setup",
            },
            {
                "ticker": "OKK",
                "entry_price_vnd": 60000,
                "exit_family": "FIXED_TARGET",
                "target": 70000,
                "risk_reward": 4.2,  # clears floor
                "why": "Clean breakout",
            },
        ]
        output = render_what_to_do_today(
            holdings_actions=actions, top_picks=picks, min_rr_floor=3.5
        )
        assert "BUY SUB" not in output
        assert "BUY OKK" in output

    def test_urgency_sort_high_before_medium(self):
        actions = [
            HoldingAction(ticker="A", verb="TRIM", qty_pct=20, urgency="MEDIUM"),
            HoldingAction(ticker="B", verb="EXIT", urgency="HIGH"),
        ]
        output = render_what_to_do_today(holdings_actions=actions, top_picks=[], min_rr_floor=3.5)
        # Urgent EXIT B bullet must appear before TRIM A.
        idx_b = output.index("EXIT B")
        idx_a = output.index("TRIM A")
        assert idx_b < idx_a
