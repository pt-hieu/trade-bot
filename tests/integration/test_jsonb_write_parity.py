"""Integration — fleet-wide JSONB write parity.

Drives every known ``shared.neon`` JSONB writer through the real Database and
asserts the column round-trips as ``object`` / ``array`` — not ``string``. A
``string`` result means the code pre-serialized with ``json.dumps`` while the
SQL lacked a matching ``::jsonb`` cast and the registered asyncpg codec
double-encoded the value — the bug migration 307 cleaned up.

Run requires a test Postgres (local Docker or Neon preview branch)::

    SWINGY_INTEGRATION_DB_URL=postgresql://swingy:swingy@localhost:5432/swingy_test \\
        uv run pytest tests/integration/test_jsonb_write_parity.py -v

Adding a new JSONB write site in ``shared/neon``? Add a test here. The AST
pre-commit guard and this suite together form the write-parity contract.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

# Tests need a real test DB — CI sets this env var, unit runs skip.
_TEST_DB_URL = os.environ.get("SWINGY_INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(
    not _TEST_DB_URL,
    reason="SWINGY_INTEGRATION_DB_URL not set — integration DB required",
)

_SENTINEL_DATE = date(1999, 12, 31)
_SENTINEL_SOURCE = "parity-test"
_SENTINEL_TICKER = "__TST__"
_SENTINEL_CATALYST_KEY = "__test_parity_catalyst__"
_SENTINEL_PHASE = "__parity_test__"


@pytest.mark.asyncio
async def test_jsonb_write_parity_macro_metrics():
    """macro_metrics.geopolitical_shock — the RC2 entry point."""
    from shared.database import Database
    from shared.neon.insert_market import insert_macro_metrics

    payload = {
        "scan_date": _SENTINEL_DATE,
        "dxy_value": 100.0,
        "dxy_change_pct": 0.1,
        "dxy_signal": "NEUTRAL",
        "vix_value": 20.0,
        "vix_change_pct": 0.5,
        "vix_signal": "MODERATE",
        "usd_vnd_rate": 25300,
        "usd_vnd_signal": "STABLE",
        "global_risk_regime": "CAUTIOUS",
        "interpretation": "parity test",
        "geopolitical_shock": {
            "phase_name": "sustained_pressure",
            "catalyst_event": "TEST Hormuz",
            "behavior": "behavior text",
            "impact": "NEGATIVE",
            "affected_tickers": ["VN-INDEX"],
            "notes": "",
            "catalyst_key": "test_key",
            "days_active": 1,
            "phase_stale": False,
        },
    }
    async with Database(dsn=_TEST_DB_URL) as db:  # type: ignore[call-arg]
        await db.execute("DELETE FROM macro_metrics WHERE scan_date = $1", _SENTINEL_DATE)
        try:
            assert await insert_macro_metrics(_SENTINEL_DATE, payload)
            typeof = await db.fetch_val(
                "SELECT jsonb_typeof(geopolitical_shock) FROM macro_metrics WHERE scan_date = $1",
                _SENTINEL_DATE,
            )
            assert typeof == "object", f"expected object, got {typeof}"
            phase = await db.fetch_val(
                "SELECT geopolitical_shock->>'phase_name' FROM macro_metrics WHERE scan_date = $1",
                _SENTINEL_DATE,
            )
            assert phase == "sustained_pressure"
        finally:
            await db.execute("DELETE FROM macro_metrics WHERE scan_date = $1", _SENTINEL_DATE)


@pytest.mark.asyncio
async def test_jsonb_write_parity_catalyst_phases():
    """catalysts.phases — agent write path unblocked by RC1."""
    from shared.database import Database
    from shared.neon.catalysts import upsert_catalyst

    payload = {
        "catalyst_key": _SENTINEL_CATALYST_KEY,
        "event": "test event",
        "expected": "test expected",
        "affected_tickers": ["VN-INDEX"],
        "impact": "NEGATIVE",
        "confidence": "MEDIUM",
        "source": _SENTINEL_SOURCE,
        "added_date": _SENTINEL_DATE,
        "phases": {
            "immediate_shock": {
                "period": "Jan 1-7, 2099",
                "impact": "NEGATIVE",
                "behavior": "test behavior",
            },
        },
    }
    async with Database(dsn=_TEST_DB_URL) as db:  # type: ignore[call-arg]
        await db.execute("DELETE FROM catalysts WHERE catalyst_key = $1", _SENTINEL_CATALYST_KEY)
        try:
            assert await upsert_catalyst(payload)
            typeof = await db.fetch_val(
                "SELECT jsonb_typeof(phases) FROM catalysts WHERE catalyst_key = $1",
                _SENTINEL_CATALYST_KEY,
            )
            assert typeof == "object"
            period = await db.fetch_val(
                "SELECT phases->'immediate_shock'->>'period' FROM catalysts WHERE catalyst_key = $1",
                _SENTINEL_CATALYST_KEY,
            )
            assert period == "Jan 1-7, 2099"
        finally:
            await db.execute(
                "DELETE FROM catalysts WHERE catalyst_key = $1", _SENTINEL_CATALYST_KEY
            )


@pytest.mark.asyncio
async def test_jsonb_write_parity_alerts_all_four_sites():
    """Covers alerts.alert_metadata, alert_conditions.params, alerts.triggered_values,
    and alert_history.event_data in a single lifecycle — register + trigger."""
    from shared.database import Database
    from shared.neon.alerts import register_alert, trigger_alert

    alert = {
        "ticker": "VN-INDEX",
        "source": _SENTINEL_SOURCE,
        "source_date": _SENTINEL_DATE,
        "conditions": [
            {
                "type": "price_above",
                "value": 1234.0,
                "params": {"foo": "bar", "threshold": 1.0},
            },
        ],
        "action_type": "notify",
        "status": "active",
        "alert_metadata": {"kind": "parity", "nested": {"n": 1}},
    }
    async with Database(dsn=_TEST_DB_URL) as db:  # type: ignore[call-arg]
        await db.execute(
            "DELETE FROM alerts WHERE source_date = $1 AND source = $2",
            _SENTINEL_DATE,
            _SENTINEL_SOURCE,
        )
        alert_id: int | None = None
        try:
            alert_id = await register_alert(alert)
            assert alert_id > 0
            meta_type = await db.fetch_val(
                "SELECT jsonb_typeof(alert_metadata) FROM alerts WHERE id = $1", alert_id
            )
            assert meta_type == "object"
            meta_nested = await db.fetch_val(
                "SELECT alert_metadata->'nested'->>'n' FROM alerts WHERE id = $1", alert_id
            )
            assert meta_nested == "1"
            params_type = await db.fetch_val(
                "SELECT jsonb_typeof(params) FROM alert_conditions WHERE alert_id = $1",
                alert_id,
            )
            assert params_type == "object"
            params_foo = await db.fetch_val(
                "SELECT params->>'foo' FROM alert_conditions WHERE alert_id = $1", alert_id
            )
            assert params_foo == "bar"

            await trigger_alert(alert_id, {"price": 1250.5, "meta": {"note": "parity"}})
            tv_type = await db.fetch_val(
                "SELECT jsonb_typeof(triggered_values) FROM alerts WHERE id = $1", alert_id
            )
            assert tv_type == "object"
            ed_type = await db.fetch_val(
                "SELECT jsonb_typeof(event_data) FROM alert_history "
                "WHERE alert_id = $1 AND event_type = 'triggered'",
                alert_id,
            )
            assert ed_type == "object"
        finally:
            # Clean up anything we may have inserted, even on alert_id = None.
            await db.execute(
                "DELETE FROM alert_conditions WHERE alert_id IN "
                "(SELECT id FROM alerts WHERE source_date = $1 AND source = $2)",
                _SENTINEL_DATE,
                _SENTINEL_SOURCE,
            )
            await db.execute(
                "DELETE FROM alert_history WHERE alert_id IN "
                "(SELECT id FROM alerts WHERE source_date = $1 AND source = $2)",
                _SENTINEL_DATE,
                _SENTINEL_SOURCE,
            )
            await db.execute(
                "DELETE FROM alerts WHERE source_date = $1 AND source = $2",
                _SENTINEL_DATE,
                _SENTINEL_SOURCE,
            )


@pytest.mark.asyncio
async def test_jsonb_write_parity_strategy_directive():
    """strategy_directives.constraints — pre-existing ::jsonb cast, must stay."""
    from shared.database import Database
    from shared.neon.directives import save_strategy_directive

    async with Database(dsn=_TEST_DB_URL) as db:  # type: ignore[call-arg]
        await db.execute("DELETE FROM strategy_directives WHERE scan_date = $1", _SENTINEL_DATE)
        try:
            await save_strategy_directive(
                _SENTINEL_DATE, "parity test", {"min_rr": 3.5, "nested": {"ok": True}}
            )
            typeof = await db.fetch_val(
                "SELECT jsonb_typeof(constraints) FROM strategy_directives WHERE scan_date = $1",
                _SENTINEL_DATE,
            )
            assert typeof == "object"
        finally:
            await db.execute("DELETE FROM strategy_directives WHERE scan_date = $1", _SENTINEL_DATE)


@pytest.mark.asyncio
async def test_jsonb_write_parity_company_profile():
    """company_profiles — 6 jsonb columns, pattern-B (::jsonb casts)."""
    from shared.database import Database
    from shared.neon.company_profiles import upsert_company_profile

    profile = {
        "business_summary": "parity test",
        "revenue_segments": [{"name": "seg1", "pct": 100}],
        "supply_chain": [{"step": "procure"}],
        "export_split": {"VN": 100},
        "macro_sensitivities": [{"factor": "oil", "direction": "NEGATIVE", "magnitude": "HIGH"}],
        "regulatory_exposure": [{"regulation": "tax"}],
        "competitive_position": {"moat": "strong"},
    }
    expected_types = {
        "revenue_segments": "array",
        "supply_chain": "array",
        "export_split": "object",
        "macro_sensitivities": "array",
        "regulatory_exposure": "array",
        "competitive_position": "object",
    }
    async with Database(dsn=_TEST_DB_URL) as db:  # type: ignore[call-arg]
        await db.execute("DELETE FROM company_profiles WHERE ticker = $1", _SENTINEL_TICKER)
        await db.execute(
            "INSERT INTO stocks (ticker, sector_id) VALUES ($1, NULL) ON CONFLICT DO NOTHING",
            _SENTINEL_TICKER,
        )
        try:
            await upsert_company_profile(_SENTINEL_TICKER, profile, _SENTINEL_SOURCE)
            for col, expected in expected_types.items():
                typeof = await db.fetch_val(
                    f"SELECT jsonb_typeof({col}) FROM company_profiles WHERE ticker = $1",
                    _SENTINEL_TICKER,
                )
                assert typeof == expected, f"{col}: got {typeof}, expected {expected}"
        finally:
            await db.execute("DELETE FROM company_profiles WHERE ticker = $1", _SENTINEL_TICKER)


@pytest.mark.asyncio
async def test_jsonb_write_parity_pipeline_checkpoint():
    """pipeline_checkpoints.data — save_checkpoint pattern-B."""
    from shared.database import Database
    from shared.neon.checkpoints import save_checkpoint

    async with Database(dsn=_TEST_DB_URL) as db:  # type: ignore[call-arg]
        await db.execute(
            "DELETE FROM pipeline_checkpoints WHERE scan_date = $1 AND phase = $2",
            _SENTINEL_DATE,
            _SENTINEL_PHASE,
        )
        try:
            assert await save_checkpoint(
                _SENTINEL_DATE, _SENTINEL_PHASE, {"foo": "bar", "nested": {"ok": True}}
            )
            typeof = await db.fetch_val(
                "SELECT jsonb_typeof(data) FROM pipeline_checkpoints "
                "WHERE scan_date = $1 AND phase = $2",
                _SENTINEL_DATE,
                _SENTINEL_PHASE,
            )
            assert typeof == "object"
        finally:
            await db.execute(
                "DELETE FROM pipeline_checkpoints WHERE scan_date = $1 AND phase = $2",
                _SENTINEL_DATE,
                _SENTINEL_PHASE,
            )


@pytest.mark.asyncio
async def test_jsonb_write_parity_midday_checks():
    """midday_checks.recommendation_overrides — insert_midday_check ::jsonb."""
    from shared.database import Database
    from shared.neon.insert_content import insert_midday_check

    data = {
        "trading_mode": "NORMAL",
        "morning_reflection": "parity",
        "afternoon_plan": [
            {
                "ticker": "VCB",
                "action": "HOLD",
                "confidence": "HIGH",
                "reason": "parity test",
            }
        ],
        "capital_note": "",
        "recommendation_overrides": [{"ticker": "VCB", "action": "HOLD"}],
        "entries_hit": [],
        "big_movers": [],
        "position_alerts": [],
    }
    async with Database(dsn=_TEST_DB_URL) as db:  # type: ignore[call-arg]
        await db.execute("DELETE FROM midday_checks WHERE scan_date = $1", _SENTINEL_DATE)
        try:
            assert await insert_midday_check(_SENTINEL_DATE, data)
            typeof = await db.fetch_val(
                "SELECT jsonb_typeof(recommendation_overrides) "
                "FROM midday_checks WHERE scan_date = $1",
                _SENTINEL_DATE,
            )
            assert typeof == "array"
            plan_typeof = await db.fetch_val(
                "SELECT jsonb_typeof(afternoon_plan) FROM midday_checks WHERE scan_date = $1",
                _SENTINEL_DATE,
            )
            assert plan_typeof == "array", f"expected array, got {plan_typeof}"
            plan_reason = await db.fetch_val(
                "SELECT afternoon_plan->0->>'reason' FROM midday_checks WHERE scan_date = $1",
                _SENTINEL_DATE,
            )
            assert plan_reason == "parity test"
        finally:
            # Child-table cleanup is a no-op today (the payload has empty lists)
            # but kept in case future tests populate them.
            await db.execute(
                "DELETE FROM midday_entries_hit WHERE midday_id IN "
                "(SELECT id FROM midday_checks WHERE scan_date = $1)",
                _SENTINEL_DATE,
            )
            await db.execute(
                "DELETE FROM midday_big_movers WHERE midday_id IN "
                "(SELECT id FROM midday_checks WHERE scan_date = $1)",
                _SENTINEL_DATE,
            )
            await db.execute(
                "DELETE FROM midday_position_alerts WHERE midday_id IN "
                "(SELECT id FROM midday_checks WHERE scan_date = $1)",
                _SENTINEL_DATE,
            )
            await db.execute("DELETE FROM midday_checks WHERE scan_date = $1", _SENTINEL_DATE)
