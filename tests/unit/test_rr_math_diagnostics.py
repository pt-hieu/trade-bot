"""SWI-358: compute_net_rr_diagnosed surfaces geometry anomalies."""

from __future__ import annotations

import pytest

from shared.rules.rr_math import (
    EXTREME_RR_THRESHOLD,
    MIN_RISK_PCT,
    compute_net_rr,
    compute_net_rr_diagnosed,
)


class TestDiagnostics:
    def test_normal_geometry(self):
        """1:3 trade — neither degenerate_risk nor extreme_rr fires."""
        rr_net, rr_gross, diag = compute_net_rr_diagnosed(entry=10000, stop=9500, target=11500)
        assert rr_net == pytest.approx(3.0, rel=1e-6)
        assert rr_gross == pytest.approx(3.0, rel=1e-6)
        assert diag["degenerate_risk"] is False
        assert diag["extreme_rr"] is False
        assert diag["risk_gross"] == pytest.approx(500.0)
        assert diag["rr_raw"] == pytest.approx(3.0)

    def test_degenerate_risk(self):
        """Risk well below MIN_RISK_PCT × entry flags degenerate_risk."""
        rr_net, rr_gross, diag = compute_net_rr_diagnosed(entry=100.0, stop=99.5, target=110.0)
        # 0.5 / 100 = 0.005 — boundary; pick a value just below to be unambiguous.
        rr_net2, _, diag2 = compute_net_rr_diagnosed(entry=100.0, stop=99.7, target=110.0)
        assert diag2["degenerate_risk"] is True
        assert rr_net2 > 0  # still finite, not zeroed
        # 99.5 sits exactly at floor; should NOT fire (strict <).
        assert diag["degenerate_risk"] is False
        assert MIN_RISK_PCT == 0.005

    def test_extreme_rr(self):
        """rr_raw > EXTREME_RR_THRESHOLD flips extreme_rr."""
        # entry=100, stop=99 → risk=1; target=200 → reward=100 → ratio=100.
        _, _, diag = compute_net_rr_diagnosed(entry=100.0, stop=99.0, target=200.0)
        assert diag["extreme_rr"] is True
        assert diag["rr_raw"] > EXTREME_RR_THRESHOLD

    @pytest.mark.parametrize(
        "entry,stop,target,cost_pct",
        [
            (10000.0, 9500.0, 11500.0, 0.0),
            (10000.0, 9500.0, 11500.0, 0.003),
            (50000.0, 48000.0, 56000.0, 0.0),
            (123.0, 100.0, 200.0, 0.0),
            (1.0, 0.5, 2.0, 0.001),
        ],
    )
    def test_backward_compatible(self, entry, stop, target, cost_pct):
        """compute_net_rr tuple unchanged across representative cases."""
        legacy = compute_net_rr(entry, stop, target, cost_pct)
        rr_net, rr_gross, _ = compute_net_rr_diagnosed(entry, stop, target, cost_pct)
        assert legacy == (rr_net, rr_gross)

    def test_invalid_geometry_zeroed(self):
        """risk <= 0 returns (0, 0, diag) — diagnostics still populated."""
        rr_net, rr_gross, diag = compute_net_rr_diagnosed(entry=100.0, stop=110.0, target=120.0)
        assert rr_net == 0.0
        assert rr_gross == 0.0
        assert diag["risk_gross"] == -10.0
        assert diag["rr_raw"] == 0.0
        assert diag["degenerate_risk"] is False
