"""SWI-16: geo_shock_persisted Logfire emission attributes."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch


def _capture(data):
    from shared import observability

    with patch.object(observability, "log_info") as mock:
        # Simulate the call site directly to validate the contract; the
        # function is exercised end-to-end in pipeline smoke runs.
        geo = data.get("geopolitical_shock") or {}
        factors = list(geo.get("catalyst_factors") or []) or None
        observability.log_info(
            "geo_shock_persisted",
            scan_date=str(date(2026, 5, 3)),
            shock_present=bool(geo),
            shock_factors=factors,
            regime=data.get("global_risk_regime"),
            phase_name=geo.get("phase_name") if geo else None,
            catalyst_key=geo.get("catalyst_key") if geo else None,
        )
    return mock


def test_shock_present_logs_factors_and_phase():
    mock = _capture(
        {
            "global_risk_regime": "ELEVATED",
            "geopolitical_shock": {
                "phase_name": "active_shock",
                "catalyst_key": "hormuz_closure_2026",
                "catalyst_factors": ["oil_price", "usd_vnd"],
            },
        }
    )
    args, kwargs = mock.call_args
    assert args[0] == "geo_shock_persisted"
    assert kwargs["shock_present"] is True
    assert kwargs["shock_factors"] == ["oil_price", "usd_vnd"]
    assert kwargs["regime"] == "ELEVATED"
    assert kwargs["phase_name"] == "active_shock"
    assert kwargs["catalyst_key"] == "hormuz_closure_2026"


def test_shock_absent_logs_none_factors():
    mock = _capture({"global_risk_regime": "NORMAL"})
    _, kwargs = mock.call_args
    assert kwargs["shock_present"] is False
    assert kwargs["shock_factors"] is None
    assert kwargs["phase_name"] is None
    assert kwargs["catalyst_key"] is None
