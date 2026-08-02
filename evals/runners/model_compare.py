"""
Model comparison runner — same dataset across multiple models.

Usage:
    from evals.runners.model_compare import compare_models
    reports = await compare_models(dataset, task_factory)
"""

import os

from pydantic_evals import Dataset

from evals.helpers import EVAL_MODELS


async def compare_models(
    dataset: Dataset,
    task_fn,
    models: dict[str, str] | None = None,
) -> dict[str, object]:
    """Run same dataset against each model, return comparison.

    Args:
        dataset: Dataset to evaluate
        task_fn: Async task function
        models: Dict of name -> model_id (defaults to EVAL_MODELS)

    Returns:
        Dict of model_name -> EvaluationReport
    """
    models = models or EVAL_MODELS
    reports = {}

    for name, model_id in models.items():
        print(f"\n{'=' * 60}")
        print(f"Model: {name} ({model_id})")
        print(f"{'=' * 60}")

        os.environ["EVAL_MODEL_OVERRIDE"] = model_id
        try:
            report = await dataset.evaluate(task_fn, name=f"model_{name}")
            report.print(include_input=False, include_output=True)
            reports[name] = report
        except Exception as e:
            print(f"  ERROR: {e}")
            reports[name] = None
        finally:
            os.environ.pop("EVAL_MODEL_OVERRIDE", None)

    # Summary comparison
    print(f"\n{'=' * 60}")
    print("COMPARISON SUMMARY")
    print(f"{'=' * 60}")
    for name, report in reports.items():
        if report:
            avg = report.averages()
            rate = avg.assertions if avg and avg.assertions is not None else 0.0
            print(f"  {name:20s}: assertions={rate:.0%}")
        else:
            print(f"  {name:20s}: FAILED")

    return reports
