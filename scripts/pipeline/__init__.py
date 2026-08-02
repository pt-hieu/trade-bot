"""Pipeline phase extraction modules."""

from .helpers import (
    derive_intermediates,
    determine_adaptive_workflow,
    extract_risk_regime,
    get_market_level,
    load_db_context,
    load_sector_rotation,
    patch_oil_from_commodities,
    persist_phase1,
    post_process_phase1,
    reconcile_regimes,
    resolve_trading_mode,
)
from .phase_advocate import apply_advocate_gate, run_advocate_reviews
from .phase_alerts import run_alert_registration, run_phase5_alert_pipeline
from .phase_context_builder import build_injected_context
from .phase_parallel import run_phase1_parallel, run_phase2_parallel
from .phase_picks import compute_top_picks
from .phase_recommendations import run_phase6_recommendations
from .phase_strategy import run_strategy_director
from .phase_synthesis import run_synthesis_and_reflection
from .recommendation_builder import build_structured_recommendations
from .recommendation_validator import validate_structured_recommendations
from .trailing_stops import compute_and_persist_trailing_stops
from .types import (
    AdvocateResult,
    InjectedContext,
    Phase1Result,
    Phase2Result,
    Phase3aResult,
    Phase3bResult,
    Phase3Result,
    PhaseHealth,
    PhaseIntermediates,
    PipelineContext,
    SynthesisResult,
)
from .validation import validate_pipeline_data

__all__ = [
    "AdvocateResult",
    "InjectedContext",
    "Phase1Result",
    "Phase2Result",
    "Phase3aResult",
    "Phase3bResult",
    "Phase3Result",
    "PhaseHealth",
    "PhaseIntermediates",
    "PipelineContext",
    "SynthesisResult",
    "compute_and_persist_trailing_stops",
    "apply_advocate_gate",
    "run_advocate_reviews",
    "build_injected_context",
    "compute_top_picks",
    "derive_intermediates",
    "determine_adaptive_workflow",
    "extract_risk_regime",
    "get_market_level",
    "load_db_context",
    "load_sector_rotation",
    "patch_oil_from_commodities",
    "persist_phase1",
    "post_process_phase1",
    "reconcile_regimes",
    "resolve_trading_mode",
    "run_alert_registration",
    "run_phase5_alert_pipeline",
    "run_phase6_recommendations",
    "run_phase1_parallel",
    "run_phase2_parallel",
    "run_strategy_director",
    "run_synthesis_and_reflection",
    "validate_pipeline_data",
    "build_structured_recommendations",
    "validate_structured_recommendations",
]
