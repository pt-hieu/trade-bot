"""
PydanticAI agents for retrospective analysis.

Analyzes morning brief recommendations vs actual outcomes.
"""

from .compute import compute_day_summary, compute_evaluations  # noqa: F401
from .evaluator import DaySummary, Evaluation, evaluate_day_with_agent
from .generator import generate_retro_with_agent
from .macro import evaluate_macro_for_day
from .mode import compute_mode_compliance  # noqa: F401
from .patterns import calc_action_stats, extract_patterns
from .rotation import calculate_sector_returns, evaluate_rotation, evaluate_rotation_for_day
from .validate import ValidationResult, validate_eval_commentary

__all__ = [
    # Evaluator
    "evaluate_day_with_agent",
    "Evaluation",
    "DaySummary",
    # Validation
    "validate_eval_commentary",
    "ValidationResult",
    # Patterns
    "extract_patterns",
    "calc_action_stats",
    # Generator
    "generate_retro_with_agent",
    # Rotation
    "evaluate_rotation_for_day",
    "evaluate_rotation",
    "calculate_sector_returns",
    # Macro
    "evaluate_macro_for_day",
]
