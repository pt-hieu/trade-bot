"""End-to-end-ish coverage for the DEF-005 catalyst-revision pick path.

Exercises ``generate_revision_picks`` with mocked DB + technicals so the
whole pipeline (universe fetch → catalyst selection → batch technicals →
per-candidate gate → pick list) runs in memory. Verifies the three
behavioural contracts called out in the plan:

1. **Positive pathway** — HIGH/POSITIVE catalyst names 3 tickers (1 held,
   1 watched, 1 outside). Only 2 candidates survive the universe bound
   and both clear the catalyst-discounted floor → 2 BUY picks emerge with
   ``source=catalyst_revision``.
2. **Bounded universe** — same catalyst affecting only OUT-OF-WATCHLIST
   tickers produces 0 new picks.
3. **NEGATIVE catalyst** — NEGATIVE/HIGH catalyst is never promoted.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from shared.rules.catalyst_override import CatalystBoost
from shared.rules.recommendation_gate import RecommendationGateDecision

_SCAN_DATE = date(2026, 4, 23)


def _rec_gate(*, floor: float = 3.0, max_new_entries: int = 3) -> RecommendationGateDecision:
    return RecommendationGateDecision(
        effective_rr_floor=floor,
        max_new_entries=max_new_entries,
        entries_allowed=True,
        entries_blocked_reason=None,
        applied_rules=("base_floor",),
        inputs_digest={"global_risk_regime": "CAUTIOUS"},
        shock_rr_floor=floor,
    )


def _boost(ticker: str, adjustment: float = 0.5) -> CatalystBoost:
    return {
        "ticker": ticker,
        "catalyst_key": "fuel_tax_0",
        "catalyst_event": "fuel tax 0% until Jun 30, 2026",
        "phase_lifecycle": "ACTIVE",
        "phase_name": "immediate",
        "reason": "fuel tax 0% — active catalyst",
        "rr_floor_adjustment": adjustment,
    }


def _tech(*, ticker: str, rr: float, close: int = 120_000) -> dict:
    """Shape matching get_batch_ticker_data_async's enriched output."""
    entry = close
    stop = int(close * 0.96)
    target = int(entry + (entry - stop) * rr)
    return {
        "ticker": ticker,
        "close": close,
        "atr": 2500,
        "levels": {
            "nearest_support": stop,
            "swing_low": stop,
            "nearest_resistance": target,
            "swing_high": target + 5000,
            "range_20d_low": stop,
            "range_20d_high": target + 5000,
        },
        "sector": "energy",
        "supertrend_direction": "UP",
        "adx_dmp": 25.0,
        "adx_dmn": 15.0,
    }


def _setup_compute_patch(rr_by_ticker: dict[str, float]) -> dict:
    """Build mock compute_setup_from_levels outputs keyed by ticker."""
    return {
        ticker: {
            "entry": 120_000,
            "stop": 115_000,
            "target": int(120_000 + (120_000 - 115_000) * rr),
            "risk_reward": rr,
            "position_vnd": 12_000_000,
            "valid": True,
            "exit_state": None,
            "exit_family": "FIXED_TARGET",
        }
        for ticker, rr in rr_by_ticker.items()
    }


@pytest.fixture
def mock_db():
    """Patch the DB + technicals surface that generate_revision_picks uses."""
    with (
        patch(
            "pipeline.phase_catalyst_revision_picks.get_portfolio_holdings",
            new_callable=AsyncMock,
        ) as mock_holdings,
        patch(
            "pipeline.phase_catalyst_revision_picks.load_all_watchlist_tickers",
            new_callable=AsyncMock,
        ) as mock_watchlist,
        patch(
            "pipeline.phase_catalyst_revision_picks.get_batch_ticker_data_async",
            new_callable=AsyncMock,
        ) as mock_batch,
        patch("pipeline.phase_catalyst_revision_picks.compute_setup_from_levels") as mock_setup,
        patch("pipeline.phase_catalyst_revision_picks.is_structural_uptrend") as mock_uptrend,
    ):
        mock_uptrend.return_value = True
        yield {
            "holdings": mock_holdings,
            "watchlist": mock_watchlist,
            "batch": mock_batch,
            "setup": mock_setup,
        }


class TestCatalystRevisionPositivePath:
    @pytest.mark.asyncio
    async def test_high_positive_emits_bounded_picks(self, mock_db):
        # Holdings = {PLX}, Watchlist = {BSR, FPT}, catalyst names PLX, BSR, OUTSIDER.
        # Expected candidates after bound: PLX, BSR.
        mock_db["holdings"].return_value = [{"ticker": "PLX"}]
        mock_db["watchlist"].return_value = {"BSR", "FPT"}
        mock_db["batch"].return_value = {
            "PLX": _tech(ticker="PLX", rr=2.8),
            "BSR": _tech(ticker="BSR", rr=2.7),
        }
        # Both rr_net above the catalyst-discounted floor 2.5 (3.0 - 0.5).
        mock_db["setup"].side_effect = lambda **kwargs: _setup_compute_patch(
            {"PLX": 2.8, "BSR": 2.7}
        )[kwargs["ticker"]]

        from pipeline.phase_catalyst_revision_picks import generate_revision_picks

        picks = await generate_revision_picks(
            scan_date=_SCAN_DATE,
            morning_recs=[],  # 0 BUYs from morning
            changed_catalysts=[
                {
                    "catalyst_key": "fuel_tax_0",
                    "event": "fuel tax 0%",
                    "impact": "POSITIVE",
                    "confidence": "HIGH",
                    "affected_tickers": ["PLX", "BSR", "OUTSIDER"],
                }
            ],
            rec_gate=_rec_gate(floor=3.0),
            catalyst_boost={
                "PLX": _boost("PLX"),
                "BSR": _boost("BSR"),
                "OUTSIDER": _boost("OUTSIDER"),
            },
        )

        tickers = {pick["ticker"] for pick in picks}
        assert tickers == {"PLX", "BSR"}
        for pick in picks:
            assert pick["source"] == "catalyst_revision"
            assert pick["action"] == "BUY"
            assert pick["strategy"] == "CATALYST_REVISION"
            assert pick["catalyst_key"] == "fuel_tax_0"

    @pytest.mark.asyncio
    async def test_morning_bay_kept_alongside_revision_picks(self, mock_db):
        # Morning already picked FPT — revision must NOT overwrite or dedup
        # it, only ADD candidates.
        mock_db["holdings"].return_value = [{"ticker": "PLX"}]
        mock_db["watchlist"].return_value = {"FPT"}
        mock_db["batch"].return_value = {"PLX": _tech(ticker="PLX", rr=2.8)}
        mock_db["setup"].side_effect = lambda **kwargs: _setup_compute_patch({"PLX": 2.8})[
            kwargs["ticker"]
        ]

        from pipeline.phase_catalyst_revision_picks import generate_revision_picks

        picks = await generate_revision_picks(
            scan_date=_SCAN_DATE,
            morning_recs=[
                {
                    "ticker": "FPT",
                    "entry_price": 130_000,
                    "stop_price": 125_000,
                    "target_price": 145_000,
                    "risk_reward": 3.2,
                    "action": "BUY",
                    "strategy": "TREND",
                    "section": "tech",
                }
            ],
            changed_catalysts=[
                {
                    "catalyst_key": "fuel_tax_0",
                    "event": "fuel tax 0%",
                    "impact": "POSITIVE",
                    "confidence": "HIGH",
                    "affected_tickers": ["PLX"],
                }
            ],
            rec_gate=_rec_gate(floor=3.0, max_new_entries=5),
            catalyst_boost={"PLX": _boost("PLX")},
        )

        tickers = {pick["ticker"] for pick in picks}
        assert tickers == {"FPT", "PLX"}
        fpt_pick = next(pick for pick in picks if pick["ticker"] == "FPT")
        plx_pick = next(pick for pick in picks if pick["ticker"] == "PLX")
        assert fpt_pick["source"] != "catalyst_revision"
        assert plx_pick["source"] == "catalyst_revision"


class TestCatalystRevisionBoundedUniverse:
    @pytest.mark.asyncio
    async def test_out_of_universe_catalyst_emits_zero_picks(self, mock_db):
        mock_db["holdings"].return_value = [{"ticker": "PLX"}]
        mock_db["watchlist"].return_value = {"BSR"}
        mock_db["batch"].return_value = {}

        from pipeline.phase_catalyst_revision_picks import generate_revision_picks

        picks = await generate_revision_picks(
            scan_date=_SCAN_DATE,
            morning_recs=[],
            changed_catalysts=[
                {
                    "catalyst_key": "c_xyz",
                    "event": "outside catalyst",
                    "impact": "POSITIVE",
                    "confidence": "HIGH",
                    "affected_tickers": ["OUTSIDER1", "OUTSIDER2"],
                }
            ],
            rec_gate=_rec_gate(),
            catalyst_boost={},
        )

        assert picks == []
        mock_db["batch"].assert_not_called()


class TestCatalystRevisionFailClosed:
    @pytest.mark.asyncio
    async def test_negative_catalyst_never_promoted(self, mock_db):
        mock_db["holdings"].return_value = [{"ticker": "PLX"}]
        mock_db["watchlist"].return_value = {"BSR"}
        mock_db["batch"].return_value = {}

        from pipeline.phase_catalyst_revision_picks import generate_revision_picks

        picks = await generate_revision_picks(
            scan_date=_SCAN_DATE,
            morning_recs=[],
            changed_catalysts=[
                {
                    "catalyst_key": "bad_news",
                    "event": "export ban",
                    "impact": "NEGATIVE",
                    "confidence": "HIGH",
                    "affected_tickers": ["PLX", "BSR"],
                }
            ],
            rec_gate=_rec_gate(),
            catalyst_boost={},
        )

        assert picks == []
        mock_db["batch"].assert_not_called()

    @pytest.mark.asyncio
    async def test_rr_below_effective_floor_rejected(self, mock_db):
        # Catalyst discount = 0.5; floor = 3.0 → effective 2.5. RR 2.4
        # should reject; RR 2.6 should pass.
        mock_db["holdings"].return_value = [{"ticker": "PLX"}]
        mock_db["watchlist"].return_value = {"BSR"}
        mock_db["batch"].return_value = {
            "PLX": _tech(ticker="PLX", rr=2.4),
            "BSR": _tech(ticker="BSR", rr=2.6),
        }
        mock_db["setup"].side_effect = lambda **kwargs: _setup_compute_patch(
            {"PLX": 2.4, "BSR": 2.6}
        )[kwargs["ticker"]]

        from pipeline.phase_catalyst_revision_picks import generate_revision_picks

        picks = await generate_revision_picks(
            scan_date=_SCAN_DATE,
            morning_recs=[],
            changed_catalysts=[
                {
                    "catalyst_key": "fuel_tax_0",
                    "event": "fuel tax 0%",
                    "impact": "POSITIVE",
                    "confidence": "HIGH",
                    "affected_tickers": ["PLX", "BSR"],
                }
            ],
            rec_gate=_rec_gate(floor=3.0),
            catalyst_boost={"PLX": _boost("PLX"), "BSR": _boost("BSR")},
        )

        tickers = {pick["ticker"] for pick in picks}
        assert tickers == {"BSR"}


class TestCatalystRevisionActiveSetSeed:
    """SWI-19 (2026-04-27): selector seed = changed_catalysts ∪ active_catalysts.

    Pre-fix, only ``changed_catalysts`` fed the selector — a HIGH/POSITIVE
    catalyst discovered yesterday and unchanged today produced 0 candidates.
    """

    @pytest.mark.asyncio
    async def test_active_only_catalyst_emits_pick(self, mock_db):
        # No catalyst CHANGED today, but an active HIGH/POSITIVE catalyst
        # tags PLX (held). Without the union, generate_revision_picks
        # returned [] — with it, PLX produces a catalyst_revision pick.
        mock_db["holdings"].return_value = [{"ticker": "PLX"}]
        mock_db["watchlist"].return_value = set()
        mock_db["batch"].return_value = {"PLX": _tech(ticker="PLX", rr=2.8)}
        mock_db["setup"].side_effect = lambda **kwargs: _setup_compute_patch({"PLX": 2.8})[
            kwargs["ticker"]
        ]

        from pipeline.phase_catalyst_revision_picks import generate_revision_picks

        picks = await generate_revision_picks(
            scan_date=_SCAN_DATE,
            morning_recs=[],
            changed_catalysts=[],  # CRITICAL: no changes today
            rec_gate=_rec_gate(floor=3.0),
            catalyst_boost={"PLX": _boost("PLX")},
            active_catalysts=[
                {
                    "catalyst_key": "fuel_tax_0",
                    "event": "fuel tax 0%",
                    "impact": "POSITIVE",
                    "confidence": "HIGH",
                    "affected_tickers": ["PLX"],
                    "phases": None,
                    "supporting_article_count": 3,
                    "catalyst_type": "regulatory",
                }
            ],
        )

        tickers = {pick["ticker"] for pick in picks}
        assert tickers == {"PLX"}

    @pytest.mark.asyncio
    async def test_dedup_when_in_both_sets(self, mock_db):
        # Same catalyst_key in both — counted once (caller dedup).
        mock_db["holdings"].return_value = [{"ticker": "PLX"}]
        mock_db["watchlist"].return_value = set()
        mock_db["batch"].return_value = {"PLX": _tech(ticker="PLX", rr=2.8)}
        mock_db["setup"].side_effect = lambda **kwargs: _setup_compute_patch({"PLX": 2.8})[
            kwargs["ticker"]
        ]

        from pipeline.phase_catalyst_revision_picks import generate_revision_picks

        catalyst_dict = {
            "catalyst_key": "fuel_tax_0",
            "event": "fuel tax 0%",
            "impact": "POSITIVE",
            "confidence": "HIGH",
            "affected_tickers": ["PLX"],
        }
        active_dict = {
            **catalyst_dict,
            "phases": None,
            "supporting_article_count": 3,
            "catalyst_type": "regulatory",
        }

        picks = await generate_revision_picks(
            scan_date=_SCAN_DATE,
            morning_recs=[],
            changed_catalysts=[catalyst_dict],
            rec_gate=_rec_gate(floor=3.0),
            catalyst_boost={"PLX": _boost("PLX")},
            active_catalysts=[active_dict],
        )

        # PLX appears once even though same catalyst is seeded twice.
        plx_picks = [p for p in picks if p["ticker"] == "PLX"]
        assert len(plx_picks) == 1


class TestCatalystRevisionShockRegime:
    @pytest.mark.asyncio
    async def test_shock_floor_with_catalyst_discount_passes_3_5(self, mock_db):
        # Shock regime: rec_gate.effective_rr_floor = 4.0. HIGH/POS catalyst
        # discount = 0.5 → effective floor 3.5. RR 3.6 passes, 3.4 rejects.
        mock_db["holdings"].return_value = [{"ticker": "PLX"}]
        mock_db["watchlist"].return_value = {"BSR"}
        mock_db["batch"].return_value = {
            "PLX": _tech(ticker="PLX", rr=3.6),
            "BSR": _tech(ticker="BSR", rr=3.4),
        }
        mock_db["setup"].side_effect = lambda **kwargs: _setup_compute_patch(
            {"PLX": 3.6, "BSR": 3.4}
        )[kwargs["ticker"]]

        from pipeline.phase_catalyst_revision_picks import generate_revision_picks

        picks = await generate_revision_picks(
            scan_date=_SCAN_DATE,
            morning_recs=[],
            changed_catalysts=[
                {
                    "catalyst_key": "fuel_tax_0",
                    "event": "fuel tax 0%",
                    "impact": "POSITIVE",
                    "confidence": "HIGH",
                    "affected_tickers": ["PLX", "BSR"],
                }
            ],
            rec_gate=_rec_gate(floor=4.0),
            catalyst_boost={"PLX": _boost("PLX"), "BSR": _boost("BSR")},
        )

        tickers = {pick["ticker"] for pick in picks}
        assert tickers == {"PLX"}
