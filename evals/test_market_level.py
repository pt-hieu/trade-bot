"""
Market level agent evaluation tests.

Usage:
    # Smoke (fast, cheap model)
    uv run pytest evals/test_market_level.py -m eval -k smoke

    # Comprehensive (model comparison quality)
    uv run pytest evals/test_market_level.py -m eval -k comprehensive

    # All
    uv run pytest evals/test_market_level.py -m eval
"""

from pathlib import Path

import pytest
from pydantic_evals import Dataset

from evals.evaluators.regime import (
    ConfidenceInRange,
    HasKeySignal,
    RegimeMatchesExpected,
    ValidRegime,
)
from evals.tasks.market_level import (
    MarketLevelInput,
    MarketLevelMetadata,
    MarketRegimeResult,
    market_level_task,
)

DATASET_DIR = Path(__file__).parent / "datasets" / "market_level"

EVALUATORS = [ValidRegime(), RegimeMatchesExpected(), ConfidenceInRange(), HasKeySignal()]


def _load_dataset(name: str) -> Dataset[MarketLevelInput, MarketRegimeResult, MarketLevelMetadata]:
    """Load a YAML dataset with typed input/output models."""
    path = DATASET_DIR / f"{name}.yaml"
    return Dataset[MarketLevelInput, MarketRegimeResult, MarketLevelMetadata].from_file(
        path,
        custom_evaluator_types=[
            ValidRegime,
            RegimeMatchesExpected,
            ConfidenceInRange,
            HasKeySignal,
        ],
    )


def _assertion_rate(report) -> float:
    """Get assertion pass rate (0.0-1.0) from report averages."""
    avg = report.averages()
    return avg.assertions if avg and avg.assertions is not None else 0.0


@pytest.mark.eval
async def test_market_level_smoke():
    """Smoke test — 5 clear-cut cases, fast CI gate."""
    dataset = _load_dataset("smoke")
    for case in dataset.cases:
        case.evaluators = case.evaluators + EVALUATORS
    report = await dataset.evaluate(market_level_task, name="market_level_smoke")
    report.print(include_input=False, include_output=True)
    rate = _assertion_rate(report)
    assert rate >= 0.6, f"Smoke test assertion rate {rate:.0%} < 60%"


@pytest.mark.eval
async def test_market_level_comprehensive():
    """Comprehensive — 12 cases including edge cases and negatives."""
    dataset = _load_dataset("comprehensive")
    for case in dataset.cases:
        case.evaluators = case.evaluators + EVALUATORS
    report = await dataset.evaluate(market_level_task, name="market_level_comprehensive")
    report.print(include_input=False, include_output=True)
    rate = _assertion_rate(report)
    assert rate >= 0.5, f"Comprehensive assertion rate {rate:.0%} < 50%"


@pytest.mark.eval
async def test_market_level_consistency():
    """Run 3 trials on smoke dataset — check pass^3 consistency."""
    dataset = _load_dataset("smoke")
    for case in dataset.cases:
        case.evaluators = case.evaluators + EVALUATORS

    results = []
    for trial in range(3):
        report = await dataset.evaluate(market_level_task, name=f"consistency_trial_{trial}")
        results.append(report)

    # Check assertions pass rate across all trials
    rates = [_assertion_rate(r) for r in results]
    avg_rate = sum(rates) / len(rates)
    print(f"\nConsistency: trial rates = {[f'{r:.0%}' for r in rates]}, avg = {avg_rate:.0%}")
    assert avg_rate >= 0.6, f"Avg consistency {avg_rate:.0%} < 60%"
