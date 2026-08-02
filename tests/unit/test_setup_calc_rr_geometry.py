"""SWI-358: _build_single_setup emits rr_geometry_anomaly + diag fields.

Setup remains `valid=True` for both degenerate-risk and extreme-rr cases
(user binding decision: visibility, not gating). The diag flags ride on
the returned setup dict so downstream scoring_health can audit shipped rows.
"""

from __future__ import annotations

import pytest

from agents.tools.technicals.setup_calc import _build_single_setup


@pytest.mark.usefixtures("mock_trading_config")
class TestRrGeometryAnomaly:
    def test_normal_geometry_no_flags(self):
        setup = _build_single_setup("FPT", entry=100000, stop=95000, target=120000, close=100000)
        assert setup["valid"] is True
        assert setup["degenerate_risk"] is False
        assert setup["extreme_rr"] is False

    def test_degenerate_risk_flagged_but_valid(self):
        # risk = 100, entry = 100_000 → 0.1% << MIN_RISK_PCT (0.5%).
        setup = _build_single_setup("SAB", entry=100000, stop=99900, target=110000, close=100000)
        assert setup["valid"] is True  # surface, do not gate
        assert setup["degenerate_risk"] is True

    def test_extreme_rr_flagged_but_valid(self):
        # rr ≈ 100 — well above EXTREME_RR_THRESHOLD (20).
        setup = _build_single_setup("XYZ", entry=10000, stop=9900, target=20000, close=10000)
        assert setup["valid"] is True
        assert setup["extreme_rr"] is True
