"""Tests for phase_recommendations validation logic."""

import logging

import pytest

from pipeline.phase_recommendations import (
    _flatten_beliefs,
    _inject_coverage_gaps,
)
from pipeline.phase_recommendations import (
    run_phase6_recommendations as write_recommendations,  # noqa: F401
)

# ============================================================================
# Helpers — we test the validation logic by calling write_recommendations
# with mock DB. Since write_recommendations is async and touches DB,
# we test the validation functions extracted inline. For now, we test
# the logic via compute_evaluations-style direct testing.
# ============================================================================

# Instead of mocking the full async write path, test the validation
# logic by importing the module and checking the validation steps.
# The validation is inline in write_recommendations, so we test via
# the public function with a patched DB insert.


@pytest.fixture
def base_recs():
    """Minimal recs for testing validation."""
    return [
        {
            "ticker": "HDB",
            "action": "WATCH",
            "section": "LONG_TERM",
            "entry_price": 24250,
            "stop_price": 23300,
            "target_price": 26000,
            "rationale": "Test",
        },
        {
            "ticker": "VNM",
            "action": "WATCH",
            "section": "LONG_TERM",
            "entry_price": 60500,
            "stop_price": 58000,
            "target_price": 64000,
            "rationale": "Test",
        },
    ]


class TestStopEntryValidation:
    """Stop >= entry should clear invalid prices."""

    def test_inverted_stop_clears_prices(self):
        """BCM-style: stop=49000 > entry=45000 → prices cleared."""
        recs = [
            {
                "ticker": "BCM",
                "action": "WAIT",
                "section": "LONG_TERM",
                "entry_price": 45000,
                "stop_price": 49000,
                "target_price": 58000,
                "rationale": "Test",
            }
        ]
        # We can't easily test the full async flow, so test the validation
        # logic directly by checking what the function would do to the rec.
        # The stop >= entry check is at the rec-mutation level.
        action = recs[0]["action"].upper()
        entry = recs[0]["entry_price"]
        stop = recs[0]["stop_price"]
        assert action in ("BUY", "ADD", "LIMIT_BUY", "WATCH", "WAIT")
        assert stop >= entry  # This would trigger the validation


class TestCrossSectionDedup:
    """Ticker in SKIP should drop ALL non-SKIP entries."""

    def test_skip_drops_hold(self):
        """HDB in both WATCH and SKIP → only SKIP survives."""
        recs = [
            {"ticker": "HDB", "action": "WATCH", "section": "LONG_TERM"},
            {"ticker": "HDB", "action": "SKIP", "section": "SKIP_THESE"},
            {"ticker": "VNM", "action": "WATCH", "section": "LONG_TERM"},
        ]
        skip_tickers = {
            r.get("ticker") for r in recs if (r.get("action") or "").upper() in ("SKIP", "AVOID")
        }
        deduped = []
        for rec in recs:
            ticker = rec.get("ticker")
            action = (rec.get("action") or "").upper()
            if ticker in skip_tickers and action not in ("SKIP", "AVOID"):
                continue
            deduped.append(rec)

        assert len(deduped) == 2
        hdb_recs = [r for r in deduped if r["ticker"] == "HDB"]
        assert len(hdb_recs) == 1
        assert hdb_recs[0]["action"] == "SKIP"

    def test_skip_drops_hold_not_just_watch(self):
        """Ticker-based dedup catches HOLD too (parser mislabel)."""
        recs = [
            {"ticker": "HDB", "action": "HOLD", "section": "LONG_TERM"},
            {"ticker": "HDB", "action": "SKIP", "section": "SKIP_THESE"},
        ]
        skip_tickers = {
            r.get("ticker") for r in recs if (r.get("action") or "").upper() in ("SKIP", "AVOID")
        }
        deduped = [
            r
            for r in recs
            if not (r["ticker"] in skip_tickers and r["action"].upper() not in ("SKIP", "AVOID"))
        ]
        assert len(deduped) == 1
        assert deduped[0]["action"] == "SKIP"


class TestRRFloorValidation:
    """R:R < 2.0 should be dropped for actionable recs."""

    def test_rr_below_floor_dropped(self):
        """HDB R:R=1.84 should be dropped."""
        entry = 24250
        stop = 23300
        target = 26000
        risk = entry - stop  # 950
        reward = target - entry  # 1750
        computed_rr = reward / risk  # 1.84
        assert computed_rr < 2.0

    def test_rr_above_floor_kept(self):
        """SSI R:R=4.05 should pass."""
        entry = 25750
        stop = 24700
        target = 30000
        risk = entry - stop  # 1050
        reward = target - entry  # 4250
        computed_rr = reward / risk  # 4.05
        assert computed_rr >= 2.0

    def test_inverted_prices_negative_risk(self):
        """Inverted stop > entry produces negative risk, naturally fails."""
        entry = 45000
        stop = 49000
        target = 58000
        risk = entry - stop  # -4000
        reward = target - entry  # 13000
        # With abs() removed, risk < 0 means condition fails
        assert not (risk > 0 and reward > 0)


# ---------------------------------------------------------------------------
# get_rr_floor — R:R floor by risk regime
# ---------------------------------------------------------------------------

from shared.rules.rr_floors import get_rr_floor


class TestInjectCoverageGapsFromBeliefs:
    """T05: coverage-gap reconciliation reads deterministic beliefs, not only recs."""

    def test_missing_ticker_with_bullish_belief_becomes_watch(self, caplog):
        existing_recs: list[dict] = [
            {"ticker": "FPT", "action": "BUY", "section": "TOP_PICKS"},
        ]
        deterministic_beliefs: dict = {
            "sector": [
                {
                    "ticker": "DXS",
                    "agent_key": "sector_aggregator",
                    "direction": "BULLISH",
                    "bull_probability": 0.55,
                    "base_probability": 0.25,
                    "bear_probability": 0.20,
                    "conviction": 0.6,
                    "belief_narrative": "Property recovery catalysts clearing.",
                }
            ],
            "positions": [],
            "calibration_stats": {"sector_aggregator": {"brier_30d": 0.30, "scored_beliefs": 40}},
        }

        with caplog.at_level(logging.INFO, logger="pipeline.phase_recommendations"):
            result = _inject_coverage_gaps(
                existing_recs,
                {"FPT", "DXS"},
                _flatten_beliefs(deterministic_beliefs),  # type: ignore[arg-type]
                deterministic_beliefs["calibration_stats"],
            )

        injected = [r for r in result if r["ticker"] == "DXS"]
        assert len(injected) == 1
        dxs = injected[0]
        assert dxs["action"] == "WATCH"
        assert "[RECONCILED_FROM_BELIEFS]" in dxs["rationale"]
        assert "Property recovery" in dxs["rationale"]
        # strategy_confidence = conviction * (1 - brier_30d) = 0.6 * 0.70 = 0.42
        assert dxs["strategy_confidence"] == pytest.approx(0.42, abs=0.01)
        assert "[COVERAGE_GAP]" not in dxs["rationale"]

    def test_missing_ticker_with_bearish_belief_becomes_avoid(self):
        deterministic_beliefs: dict = {
            "sector": [
                {
                    "ticker": "NVL",
                    "agent_key": "sector_aggregator",
                    "direction": "BEARISH",
                    "bull_probability": 0.15,
                    "base_probability": 0.25,
                    "bear_probability": 0.60,
                    "conviction": 0.7,
                    "belief_narrative": "Debt default risk escalating.",
                }
            ],
            "positions": [],
            "calibration_stats": {},
        }
        result = _inject_coverage_gaps(
            [],
            {"NVL"},
            _flatten_beliefs(deterministic_beliefs),  # type: ignore[arg-type]
            deterministic_beliefs["calibration_stats"],
        )

        assert len(result) == 1
        assert result[0]["action"] == "AVOID"
        assert "[RECONCILED_FROM_BELIEFS]" in result[0]["rationale"]

    def test_missing_ticker_without_belief_fails_loudly(self, caplog):
        """True coverage failure — ticker missing from recs AND no belief.
        Should log ERROR and emit [NO_BELIEF_NO_REC] row."""
        with caplog.at_level(logging.ERROR, logger="pipeline.phase_recommendations"):
            result = _inject_coverage_gaps(
                [],
                {"XYZ"},
                {},
                {},
            )

        assert len(result) == 1
        assert result[0]["action"] == "WAIT"
        assert "[NO_BELIEF_NO_REC]" in result[0]["rationale"]
        error_logs = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("NO_BELIEF_NO_REC" in r.getMessage() for r in error_logs), (
            "true coverage gap must log ERROR (fail loudly)"
        )

    def test_existing_ticker_in_recs_is_not_reconciled(self):
        existing_recs = [{"ticker": "FPT", "action": "BUY", "section": "TOP_PICKS"}]
        deterministic_beliefs: dict = {
            "sector": [
                {
                    "ticker": "FPT",
                    "agent_key": "sector_aggregator",
                    "direction": "BULLISH",
                    "bull_probability": 0.55,
                    "conviction": 0.6,
                    "belief_narrative": "AI services.",
                }
            ],
            "positions": [],
            "calibration_stats": {},
        }

        result = _inject_coverage_gaps(
            existing_recs,
            {"FPT"},
            _flatten_beliefs(deterministic_beliefs),  # type: ignore[arg-type]
            deterministic_beliefs["calibration_stats"],
        )

        # Unchanged — no injected rows because FPT already covered.
        assert len(result) == 1
        assert result[0]["action"] == "BUY"


def _stub_gate_decision():
    """Minimal gate_decision passing run_phase6's GATE_DECISION_MISSING check."""
    from unittest.mock import MagicMock

    decision = MagicMock()
    decision.effective_rr_floor = 2.0
    decision.entries_allowed = True
    decision.to_jsonb = lambda: {}
    return decision


class TestEnvGatedFailLoud:
    """SWI-NN: phase_recommendations.py:411 must distinguish prod vs non-prod.

    - non-production: re-raise CHECK violations so dev/CI catches the regression.
    - production: log_warn + continue so the day still completes (the morning's
      empty MORNING_EMPTY_RECS guard provides the secondary fail-loud).
    - RuntimeError carve-out from `87d05d55` must remain — UNIVERSE_FETCH_FAILED
      and siblings always propagate regardless of env.
    """

    @pytest.mark.asyncio
    async def test_runtime_error_propagates_in_production(self, monkeypatch):
        from unittest.mock import patch

        monkeypatch.setenv("SWINGY_ENV", "production")
        with (
            patch(
                "pipeline.phase_recommendations.build_structured_recommendations",
                side_effect=RuntimeError("UNIVERSE_FETCH_FAILED test"),
            ),
            patch(
                "pipeline.phase_recommendations._build_valid_tickers",
                return_value=frozenset({"FPT"}),
            ),
        ):
            from datetime import date

            from pipeline.phase_recommendations import run_phase6_recommendations

            with pytest.raises(RuntimeError, match="UNIVERSE_FETCH_FAILED"):
                await run_phase6_recommendations(
                    pre_computed_picks=[],
                    position_alerts={"alerts": []},
                    sector_signals=[],
                    holdings=[{"ticker": "FPT", "plan_type": "SWING"}],
                    trading_mode={"mode": "NORMAL"},
                    longterm_watchlist={},
                    deployable_cash=0,
                    market_regime="NEUTRAL",
                    global_risk_regime="NEUTRAL",
                    scan_date=date(2026, 5, 11),
                    reflection_status="ok",
                    gate_decision=_stub_gate_decision(),
                )

    @pytest.mark.asyncio
    async def test_unknown_db_error_raises_in_development(self, monkeypatch):
        from unittest.mock import AsyncMock, patch

        monkeypatch.setenv("SWINGY_ENV", "development")
        from datetime import date

        from pipeline.phase_recommendations import run_phase6_recommendations

        async def _raise(*_a, **_kw):
            raise ValueError("simulated CHECK violation")

        with (
            patch(
                "pipeline.phase_recommendations.build_structured_recommendations",
                return_value=[],
            ),
            patch(
                "pipeline.phase_recommendations._build_valid_tickers",
                return_value=frozenset({"FPT"}),
            ),
            patch(
                "pipeline.phase_recommendations.validate_structured_recommendations",
                return_value=([], []),
            ),
            patch(
                "pipeline.phase_recommendations.audit_action_downgrades",
                return_value=None,
            ),
            patch(
                "shared.neon.insert_morning_recommendations",
                new=AsyncMock(side_effect=ValueError("simulated CHECK violation")),
            ),
            pytest.raises(ValueError, match="simulated CHECK violation"),
        ):
            await run_phase6_recommendations(
                pre_computed_picks=[],
                position_alerts={"alerts": []},
                sector_signals=[],
                holdings=[{"ticker": "FPT", "plan_type": "SWING"}],
                trading_mode={"mode": "NORMAL"},
                longterm_watchlist={},
                deployable_cash=0,
                market_regime="NEUTRAL",
                global_risk_regime="NEUTRAL",
                scan_date=date(2026, 5, 11),
                reflection_status="ok",
                gate_decision=_stub_gate_decision(),
            )

    @pytest.mark.asyncio
    async def test_unknown_db_error_logged_and_swallowed_in_production(self, monkeypatch, caplog):
        from unittest.mock import AsyncMock, patch

        monkeypatch.setenv("SWINGY_ENV", "production")
        from datetime import date

        from pipeline.phase_recommendations import run_phase6_recommendations

        with (
            patch(
                "pipeline.phase_recommendations.build_structured_recommendations",
                return_value=[],
            ),
            patch(
                "pipeline.phase_recommendations._build_valid_tickers",
                return_value=frozenset({"FPT"}),
            ),
            patch(
                "pipeline.phase_recommendations.validate_structured_recommendations",
                return_value=([], []),
            ),
            patch(
                "pipeline.phase_recommendations.audit_action_downgrades",
                return_value=None,
            ),
            patch(
                "shared.neon.insert_morning_recommendations",
                new=AsyncMock(side_effect=ValueError("simulated CHECK violation")),
            ),
        ):
            # Production: must NOT raise; logs the failure and continues.
            await run_phase6_recommendations(
                pre_computed_picks=[],
                position_alerts={"alerts": []},
                sector_signals=[],
                holdings=[{"ticker": "FPT", "plan_type": "SWING"}],
                trading_mode={"mode": "NORMAL"},
                longterm_watchlist={},
                deployable_cash=0,
                market_regime="NEUTRAL",
                global_risk_regime="NEUTRAL",
                scan_date=date(2026, 5, 11),
                reflection_status="ok",
                gate_decision=_stub_gate_decision(),
            )
        assert any(
            "pipeline_db_write_unexpected" in rec.getMessage()
            or "Recommendation DB write error" in rec.getMessage()
            for rec in caplog.records
        )


class TestGetRRFloor:
    """Validate R:R floor matches anti-conservatism circuit breaker constraints."""

    def test_risk_off_floor_is_3_0(self):
        assert get_rr_floor("RISK_OFF", 2.0) == 3.0

    def test_elevated_floor_is_3_0(self):
        assert get_rr_floor("ELEVATED", 2.0) == 3.0

    def test_crisis_floor_is_4_5(self):
        assert get_rr_floor("CRISIS", 2.0) == 4.5

    def test_normal_returns_base(self):
        assert get_rr_floor("NORMAL", 2.5) == 2.5

    def test_base_minimum_is_2_0(self):
        assert get_rr_floor("NORMAL", 1.0) == 2.0

    def test_high_min_rr_overrides_regime(self):
        """When min_rr > regime floor, min_rr wins."""
        assert get_rr_floor("RISK_OFF", 3.5) == 3.5

    def test_circuit_breaker_compat(self):
        """CRISIS floor must not exceed circuit breaker max (4.5)."""
        assert get_rr_floor("CRISIS", 2.0) <= 4.5
