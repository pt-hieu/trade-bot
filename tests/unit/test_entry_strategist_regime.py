"""Phase 2 §2.8 — entry_strategist regime drift fail-loud.

When the gate decides RISK_OFF but the technical market_regime is
NEUTRAL, the entry_strategist context MUST contain BOTH labels with
the GLOBAL RISK REGIME marked AUTHORITATIVE. The strategist must emit
``Regime: RISK_OFF`` (not NEUTRAL) in MARKET MOOD.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_entry_strategist_dual_label_in_prompt(monkeypatch):
    """The MARKET REGIME context block must label global_risk_regime as
    AUTHORITATIVE and technical regime as CONTEXT ONLY.
    """
    from scripts.agents import entry_strategist

    captured: dict = {}

    async def _stub_run(agent, prompt, **_kwargs):
        captured["prompt"] = prompt

        class _Result:
            output = "STANCE\nSELECTIVE\n"

        return _Result()

    monkeypatch.setattr(entry_strategist, "run_agent_with_total_timeout", _stub_run)

    async def _stub_create():
        class _Agent:
            pass

        class _Cfg:
            request_limit = 30
            agent_key = "entry_strategist"

        return _Agent(), _Cfg()

    monkeypatch.setattr(entry_strategist, "create_entry_strategist_agent", _stub_create)
    monkeypatch.setattr(entry_strategist, "build_usage_limits", lambda _cfg: None)

    phase1_results = {
        "market_level": {"regime": "NEUTRAL", "regime_confidence": 0.55},
        "macro_metrics": {"global_risk_regime": "RISK_OFF"},
    }

    await entry_strategist.generate_entry_strategy(
        phase1_results=phase1_results,
        phase2_results={},
        trading_mode=None,
        deterministic_sections="",
    )

    prompt = captured.get("prompt", "")
    assert "GLOBAL RISK REGIME (AUTHORITATIVE" in prompt, (
        "entry_strategist must label global_risk_regime as AUTHORITATIVE "
        "in its injected MARKET REGIME block."
    )
    assert "RISK_OFF" in prompt, (
        "entry_strategist must inject the literal RISK_OFF regime, not the technical NEUTRAL value."
    )
    assert "Technical market regime (CONTEXT ONLY)" in prompt, (
        "entry_strategist must label the technical regime as CONTEXT ONLY."
    )
