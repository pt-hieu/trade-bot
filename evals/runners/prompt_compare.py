"""
Prompt A/B comparison runner — same dataset with different prompt variants.

Prompt variants stored in evals/prompt_variants/{agent_key}/*.json
"""

import json
from pathlib import Path

from pydantic_evals import Dataset

VARIANTS_DIR = Path(__file__).parent.parent / "prompt_variants"


def list_prompt_variants(agent_key: str) -> dict[str, str]:
    """List available prompt variants for an agent.

    Returns:
        Dict of variant_name -> prompt text
    """
    variant_dir = VARIANTS_DIR / agent_key
    if not variant_dir.exists():
        return {}
    variants = {}
    for f in sorted(variant_dir.glob("*.json")):
        data = json.loads(f.read_text())
        variants[f.stem] = data["system_prompt"]
    return variants


async def compare_prompts(
    dataset: Dataset,
    task_factory,
    agent_key: str,
) -> dict[str, object]:
    """Run same dataset with different prompt variants.

    Args:
        dataset: Dataset to evaluate
        task_factory: Callable(prompt_text) -> async task function
        agent_key: Agent key for finding variants

    Returns:
        Dict of variant_name -> EvaluationReport
    """
    from evals.helpers import load_prompt

    variants = {"baseline": await load_prompt(agent_key)}
    variants.update(list_prompt_variants(agent_key))

    if len(variants) < 2:
        print(f"Only {len(variants)} variant(s) found. Add variants to {VARIANTS_DIR / agent_key}/")
        if len(variants) == 1:
            name, prompt = next(iter(variants.items()))
            report = await dataset.evaluate(task_factory(prompt), name=f"prompt_{name}")
            report.print()
            return {name: report}
        return {}

    reports = {}
    for name, prompt_text in variants.items():
        print(f"\n{'=' * 60}")
        print(f"Prompt variant: {name}")
        print(f"{'=' * 60}")

        try:
            report = await dataset.evaluate(task_factory(prompt_text), name=f"prompt_{name}")
            report.print(include_input=False, include_output=True)
            reports[name] = report
        except Exception as e:
            print(f"  ERROR: {e}")
            reports[name] = None

    # Summary
    print(f"\n{'=' * 60}")
    print("PROMPT COMPARISON SUMMARY")
    print(f"{'=' * 60}")
    for name, report in reports.items():
        if report:
            avg = report.averages()
            rate = avg.assertions if avg and avg.assertions is not None else 0.0
            print(f"  {name:30s}: assertions={rate:.0%}")
        else:
            print(f"  {name:30s}: FAILED")

    return reports
