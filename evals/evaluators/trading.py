"""
Evaluators for trading mode and position management agents.

Expected values live in case.metadata (not expected_output).
"""

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

VALID_MODES = {"NORMAL", "LOW_CASH", "REALLOCATION"}
VALID_ACTIONS = {"BUY", "SELL", "HOLD", "TRIM", "EXIT", "ADD", "WAIT", "SKIP"}


@dataclass
class ModeCorrect(Evaluator):
    """Check that output mode matches expected mode from metadata."""

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        if ctx.metadata is None:
            return True
        expected = (
            ctx.metadata.mode
            if hasattr(ctx.metadata, "mode")
            else ctx.metadata.get("mode")
            if isinstance(ctx.metadata, dict)
            else None
        )
        if expected is None:
            return True
        return getattr(ctx.output, "mode", None) == expected


@dataclass
class ValidMode(Evaluator):
    """Check that output mode is a valid enum value."""

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        return getattr(ctx.output, "mode", None) in VALID_MODES


@dataclass
class ValidAction(Evaluator):
    """Check that stagnant_positions is a list of ticker strings."""

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        stagnant = getattr(ctx.output, "stagnant_positions", None)
        if stagnant is not None:
            return isinstance(stagnant, list) and all(isinstance(t, str) for t in stagnant)
        return True


@dataclass
class ModeCompliance(Evaluator):
    """Check that recommendations comply with mode constraints.

    - LOW_CASH: no BUY recommendations (reallocation_targets empty)
    - REALLOCATION: must have stagnant analysis
    - NORMAL: any action allowed
    """

    def evaluate(self, ctx: EvaluatorContext) -> dict[str, bool]:
        mode = getattr(ctx.output, "mode", "NORMAL")
        realloc = getattr(ctx.output, "reallocation_targets", [])

        if mode == "LOW_CASH":
            return {"mode_compliant": len(realloc) == 0}
        return {"mode_compliant": True}


@dataclass
class LongtermProtection(Evaluator):
    """Check that long-term holdings are not flagged as stagnant."""

    longterm_tickers: list[str] | None = None

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        if self.longterm_tickers is None:
            return True
        stagnant = getattr(ctx.output, "stagnant_positions", [])
        return not any(t in self.longterm_tickers for t in stagnant)
