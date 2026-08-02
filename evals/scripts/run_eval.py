#!/usr/bin/env python3
"""
CLI entry point for running evals.

Usage:
    # Smoke test (cheap model)
    uv run python evals/scripts/run_eval.py --agent market_level --dataset smoke

    # Model comparison
    uv run python evals/scripts/run_eval.py --agent market_level --compare-models

    # Prompt A/B test
    uv run python evals/scripts/run_eval.py --agent market_level --compare-prompts

    # Cost estimate only
    uv run python evals/scripts/run_eval.py --agent market_level --estimate-cost

    # Specific model
    uv run python evals/scripts/run_eval.py --agent market_level --model kimi_k25
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add project paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env.local")

# Configure Logfire for eval results dashboard (before any eval imports)
import logfire

logfire.configure(
    send_to_logfire="if-token-present",
    service_name="swingy",
    environment="eval",
)


AGENTS = {
    "market_level": {
        "dataset_dir": "market_level",
        "avg_input_tokens": 2000,
        "avg_output_tokens": 500,
    },
    "trading_mode": {
        "dataset_dir": "trading_mode",
        "avg_input_tokens": 1500,
        "avg_output_tokens": 300,
    },
}


def _get_dataset_and_task(agent_name: str, dataset_name: str):
    """Load dataset and task function for an agent."""
    from evals.helpers import DATASETS_DIR

    config = AGENTS[agent_name]
    dataset_path = DATASETS_DIR / config["dataset_dir"] / f"{dataset_name}.yaml"

    if not dataset_path.exists():
        print(f"Dataset not found: {dataset_path}")
        sys.exit(1)

    if agent_name == "market_level":
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

        dataset = Dataset[MarketLevelInput, MarketRegimeResult, MarketLevelMetadata].from_file(
            dataset_path,
            custom_evaluator_types=[
                ValidRegime,
                RegimeMatchesExpected,
                ConfidenceInRange,
                HasKeySignal,
            ],
        )
        evaluators = [ValidRegime(), RegimeMatchesExpected(), ConfidenceInRange(), HasKeySignal()]
        for case in dataset.cases:
            case.evaluators = case.evaluators + evaluators
        return dataset, market_level_task

    elif agent_name == "trading_mode":
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

        dataset = Dataset[TradingModeInput, TradingModeResult, TradingModeMetadata].from_file(
            dataset_path,
            custom_evaluator_types=[
                ValidMode,
                ModeCorrect,
                ValidAction,
                ModeCompliance,
                LongtermProtection,
            ],
        )
        evaluators = [ValidMode(), ModeCorrect(), ValidAction(), ModeCompliance()]
        for case in dataset.cases:
            case.evaluators = case.evaluators + evaluators
        return dataset, trading_mode_task

    else:
        print(f"Unknown agent: {agent_name}")
        sys.exit(1)


async def main():
    parser = argparse.ArgumentParser(description="Run swingy agent evals")
    parser.add_argument("--agent", required=True, choices=list(AGENTS.keys()))
    parser.add_argument("--dataset", default="smoke")
    parser.add_argument("--compare-models", action="store_true")
    parser.add_argument("--compare-prompts", action="store_true")
    parser.add_argument("--estimate-cost", action="store_true")
    parser.add_argument("--model", help="Specific model key from EVAL_MODELS")
    parser.add_argument("--trials", type=int, default=1, help="Number of trials per case")
    args = parser.parse_args()

    config = AGENTS[args.agent]

    # Cost estimate
    if args.estimate_cost:
        from evals.runners.cost_estimator import print_cost_estimate

        dataset, _ = _get_dataset_and_task(args.agent, args.dataset)
        print_cost_estimate(
            args.agent,
            n_cases=len(dataset.cases),
            n_trials=args.trials,
            avg_input_tokens=config["avg_input_tokens"],
            avg_output_tokens=config["avg_output_tokens"],
        )
        return

    # Model comparison
    if args.compare_models:
        from evals.runners.model_compare import compare_models

        dataset, task_fn = _get_dataset_and_task(args.agent, args.dataset)
        await compare_models(dataset, task_fn)
        return

    # Prompt comparison
    if args.compare_prompts:
        dataset, _ = _get_dataset_and_task(args.agent, args.dataset)
        # For prompt comparison, we need a task factory that accepts prompt text
        print("Prompt comparison not yet fully implemented for CLI")
        print(f"Add variants to evals/prompt_variants/{args.agent}/")
        return

    # Single run
    if args.model:
        from evals.helpers import EVAL_MODELS

        if args.model in EVAL_MODELS:
            os.environ["EVAL_MODEL_OVERRIDE"] = EVAL_MODELS[args.model]
        else:
            os.environ["EVAL_MODEL_OVERRIDE"] = args.model

    dataset, task_fn = _get_dataset_and_task(args.agent, args.dataset)

    for trial in range(args.trials):
        name = f"{args.agent}_{args.dataset}"
        if args.trials > 1:
            name += f"_trial{trial}"
        report = await dataset.evaluate(task_fn, name=name)
        report.print(include_input=False, include_output=True)
        avg = report.averages()
        rate = avg.assertions if avg and avg.assertions is not None else 0.0
        print(f"\nAssertion rate: {rate:.0%}")


if __name__ == "__main__":
    asyncio.run(main())
