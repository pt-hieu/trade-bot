"""Shared helpers/fixtures for test_recommendation_builder splits."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_SCRIPTS = Path(__file__).parent.parent.parent.parent / "scripts"

# Stub `pipeline` as a bare namespace package so submodule imports don't
# trigger `pipeline/__init__.py` (which transitively pulls in heavy agent deps
# and creates a circular import on `BUY_ACTIONS`).
if "pipeline" not in sys.modules:
    _pipeline_pkg = types.ModuleType("pipeline")
    _pipeline_pkg.__path__ = [str(_SCRIPTS / "pipeline")]  # type: ignore[attr-defined]
    sys.modules["pipeline"] = _pipeline_pkg


def _import_module(name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_import_module(
    "pipeline.recommendation_helpers",
    _SCRIPTS / "pipeline" / "recommendation_helpers.py",
)
_builder = _import_module(
    "pipeline.recommendation_builder",
    _SCRIPTS / "pipeline" / "recommendation_builder.py",
)
_validator = _import_module(
    "pipeline.recommendation_validator",
    _SCRIPTS / "pipeline" / "recommendation_validator.py",
)

SECTION_LONG_TERM = _builder.SECTION_LONG_TERM
SECTION_MY_HOLDINGS = _builder.SECTION_MY_HOLDINGS
SECTION_SKIP_THESE = _builder.SECTION_SKIP_THESE
SECTION_TOP_PICKS = _builder.SECTION_TOP_PICKS
SECTION_WHAT_TO_DO = _builder.SECTION_WHAT_TO_DO
_parse_alert_price = _builder._parse_alert_price
build_structured_recommendations = _builder.build_structured_recommendations
validate_structured_recommendations = _validator.validate_structured_recommendations


def _full_pick(ticker="FPT") -> dict:
    return {
        "ticker": ticker,
        "action": "BUY",
        "sector": "tech",
        "note": "Strong breakout signal",
        "entry": 135000,
        "stop": 130000,
        "target": 145000,
        "risk_reward": 3.3,
        "risk_reward_gross": 3.5,
        "shares": 100,
        "position_vnd": 13500000,
        "target_basis": "conservative",
        "rr_stretch": 4.0,
        "verdict": "full_size",
        "exit_plan": {"legs": []},
        "volume_vs_avg": 1.5,
        "volume_confirmed": True,
        "pattern_name": "hammer",
        "pattern_signal": "bullish",
        "strategy": "BOUNCE",
        "strategy_confidence": 0.85,
        "strategy_signals": ["RSI_oversold", "support_bounce"],
        "sim_ev": 2.3,
        "sim_p_target": 0.65,
        "sim_p_stop": 0.25,
        "sim_action": "BUY",
        "belief_conviction": 0.7,
        "belief_direction": "BULLISH",
        "belief_narrative": "Strong momentum with volume confirmation",
        "key_risk": "Sector rotation risk",
    }


def _position_alert(ticker="TCB", action="HOLD") -> dict:
    return {
        "ticker": ticker,
        "action": action,
        "urgency": "low",
        "reason": "Price consolidating near support",
        "target": "55k",
        "stop": "48k",
        "confidence": "high",
        "counter_thesis": "Banking sector headwinds",
        "entry_price": "50k",
        "current_price": "52k",
        "consensus": "majority",
        "dissenting_views": ["Technical: EXIT (weak momentum)"],
    }


def _sector_signal(ticker="VCB", signal="WATCH") -> dict:
    return {
        "ticker": ticker,
        "signal": signal,
        "note": "Near resistance",
        "sector": "banking",
        "confidence": "MEDIUM",
        "key_risk": "Rate hike pressure",
    }


def _default_validator_params(**overrides):
    """Build validator kwargs."""
    from shared.rules.recommendation_gate import compose_recommendation_gate

    legacy = dict(
        global_risk_regime="CALM",
        min_rr=2.0,
        max_picks=5,
    )
    legacy.update(
        {
            k: overrides.pop(k)
            for k in ("global_risk_regime", "min_rr", "max_picks")
            if k in overrides
        }
    )

    gate_decision = compose_recommendation_gate(
        trading_mode="NORMAL",
        market_regime="NEUTRAL",
        global_risk_regime=legacy["global_risk_regime"],
        urgency_tier="NORMAL",
        urgency_min_rr=legacy["min_rr"],
        underlying_stress=False,
        urgency_max_picks=legacy["max_picks"],
    )

    params = dict(
        trading_mode={"mode": "NORMAL"},
        deployable_cash=50_000_000,
        gate_decision=gate_decision,
    )
    params.update(overrides)
    return params
