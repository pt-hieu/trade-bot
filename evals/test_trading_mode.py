"""
Trading mode agent evaluation tests.

Usage:
    uv run pytest evals/test_trading_mode.py -m eval -k smoke
"""

from pathlib import Path

import pytest
from pydantic_evals import Dataset

from evals.evaluators.trading import (
    LongtermProtection,
    ModeCompliance,
    ModeCorrect,
    ValidAction,
    ValidMode,
)
from evals.tasks.trading_mode import (
    TradingModeInput,
    TradingModeMetadata,
    TradingModeResult,
    trading_mode_task,
)

DATASET_DIR = Path(__file__).parent / "datasets" / "trading_mode"

EVALUATORS = [ValidMode(), ModeCorrect(), ValidAction(), ModeCompliance()]


def _load_dataset(name: str) -> Dataset[TradingModeInput, TradingModeResult, TradingModeMetadata]:
    path = DATASET_DIR / f"{name}.yaml"
    return Dataset[TradingModeInput, TradingModeResult, TradingModeMetadata].from_file(
        path,
        custom_evaluator_types=[
            ValidMode,
            ModeCorrect,
            ValidAction,
            ModeCompliance,
            LongtermProtection,
        ],
    )


@pytest.mark.eval
async def test_trading_mode_smoke():
    """Smoke test — deterministic cases + one REALLOCATION LLM case."""
    dataset = _load_dataset("smoke")
    for case in dataset.cases:
        case.evaluators = case.evaluators + EVALUATORS
    report = await dataset.evaluate(trading_mode_task, name="trading_mode_smoke")
    report.print(include_input=False, include_output=True)
    avg = report.averages()
    rate = avg.assertions if avg and avg.assertions is not None else 0.0
    assert rate >= 0.8, f"Trading mode assertion rate {rate:.0%} < 80%"


@pytest.mark.eval
async def test_trading_mode_deterministic():
    """Verify deterministic mode selection (no LLM needed)."""
    from agents.trading_mode import determine_mode

    assert determine_mode(25_000_000) == "NORMAL"
    assert determine_mode(5_000_001) == "NORMAL"
    assert determine_mode(5_000_000) == "LOW_CASH"
    assert determine_mode(3_000_000) == "LOW_CASH"
    assert determine_mode(1) == "LOW_CASH"
    assert determine_mode(0) == "REALLOCATION"
    assert determine_mode(-1_000_000) == "REALLOCATION"
