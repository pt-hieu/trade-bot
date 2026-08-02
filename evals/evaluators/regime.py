"""
Evaluators for market regime classification agent.

Expected values live in case.metadata (not expected_output) because
pydantic-evals types expected_output as OutputT which is the full MarketRegimeResult.
"""

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

VALID_REGIMES = {"RISK_ON", "RISK_OFF", "NEUTRAL"}


@dataclass
class ValidRegime(Evaluator):
    """Check that output regime is one of the valid enum values."""

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        return getattr(ctx.output, "regime", None) in VALID_REGIMES


@dataclass
class RegimeMatchesExpected(Evaluator):
    """Check that output regime matches expected regime from metadata."""

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        if ctx.metadata is None:
            return True
        expected = (
            ctx.metadata.regime
            if hasattr(ctx.metadata, "regime")
            else ctx.metadata.get("regime")
            if isinstance(ctx.metadata, dict)
            else None
        )
        if expected is None:
            return True
        return getattr(ctx.output, "regime", None) == expected


@dataclass
class ConfidenceInRange(Evaluator):
    """Check confidence is in [0.0, 1.0] and above minimum threshold from metadata."""

    def evaluate(self, ctx: EvaluatorContext) -> dict[str, bool]:
        confidence = getattr(ctx.output, "regime_confidence", None)
        if confidence is None:
            return {"valid_range": False, "above_minimum": False}

        valid = 0.0 <= confidence <= 1.0

        # Get min_confidence from metadata
        min_conf = 0.0
        if ctx.metadata is not None:
            min_conf = (
                ctx.metadata.min_confidence
                if hasattr(ctx.metadata, "min_confidence")
                else ctx.metadata.get("min_confidence", 0.0)
                if isinstance(ctx.metadata, dict)
                else 0.0
            )

        return {
            "valid_range": valid,
            "above_minimum": valid and confidence >= min_conf,
        }


@dataclass
class HasKeySignal(Evaluator):
    """Check that key_signal is a non-empty string."""

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        signal = getattr(ctx.output, "key_signal", "")
        return isinstance(signal, str) and len(signal.strip()) > 5
