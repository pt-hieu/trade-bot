"""Phase 2 §2.8 — regime consistency across all agents that emit a label.

When the gate runs RISK_OFF, every regime-emitting agent must echo the
GLOBAL RISK REGIME label. The dual-label injection lives in:
  * entry_strategist (agents/entry_strategist.py)
  * critic (agents/critic.py)
  * sector_rotation (agents/sector_rotation.py — emits global_risk_regime
    in result dict)
  * meta_controller (agents/meta_controller.py — leads context_summary
    with global_macro_regime)

These tests assert the AUTHORITATIVE label is the visible one downstream.
"""

from __future__ import annotations


def test_meta_controller_leads_with_global_macro_regime():
    """meta_controller's context_summary leads with the authoritative
    global_macro_regime, not the technical market_regime.
    """
    from scripts.agents.meta_controller import determine_workflow

    decision = determine_workflow(
        trading_mode="NORMAL",
        market_regime="NEUTRAL",
        global_macro_regime="ELEVATED",
        is_trading_day=True,
        deployable_cash=10_000_000,
        urgent_exits=0,
    )
    # The context_summary must lead with global_macro_regime (ELEVATED)
    # and label market_regime as technical context.
    assert "ELEVATED" in decision.context_summary, (
        "meta_controller must surface global_macro_regime in context_summary"
    )
    assert "technical" in decision.context_summary.lower(), (
        "meta_controller must label market_regime as technical context"
    )


def test_sector_rotation_result_carries_global_risk_regime():
    """sector_rotation.detect_rotation_with_agent must return both
    market_regime (technical) and global_risk_regime (authoritative).
    Verified via the failure path which never invokes the LLM.
    """
    import asyncio

    from scripts.agents import sector_rotation

    async def _stub_create(_scan_date=None):
        class _StubAgent:
            pass

        return _StubAgent()

    async def _stub_run(*_args, **_kwargs):
        raise RuntimeError("stubbed timeout for test")

    original_create = sector_rotation.create_rotation_agent
    original_run = sector_rotation.run_agent_with_total_timeout
    sector_rotation.create_rotation_agent = _stub_create  # type: ignore[assignment]
    sector_rotation.run_agent_with_total_timeout = _stub_run  # type: ignore[assignment]
    try:
        result = asyncio.run(
            sector_rotation.detect_rotation_with_agent(
                global_risk_regime="RISK_OFF",
            )
        )
    finally:
        sector_rotation.create_rotation_agent = original_create  # type: ignore[assignment]
        sector_rotation.run_agent_with_total_timeout = original_run  # type: ignore[assignment]

    assert result["global_risk_regime"] == "RISK_OFF", (
        "sector_rotation result must echo the authoritative regime label"
    )
    assert "market_regime" in result, (
        "sector_rotation result must still carry the technical regime for back-compat consumers"
    )
