"""
Cost estimator — print estimated cost before running evals.
"""

from evals.helpers import EVAL_MODELS, estimate_cost


def print_cost_estimate(
    agent_name: str,
    n_cases: int,
    n_trials: int = 1,
    avg_input_tokens: int = 2000,
    avg_output_tokens: int = 500,
    models: dict[str, str] | None = None,
) -> dict[str, float]:
    """Print estimated cost for an eval run.

    Returns:
        Cost dict for programmatic use
    """
    models = models or EVAL_MODELS
    costs = estimate_cost(n_cases, n_trials, avg_input_tokens, avg_output_tokens, models)
    total = sum(costs.values())

    print(f"\nEstimated cost for {agent_name} ({n_cases} cases, {n_trials} trials):")
    for name, cost in costs.items():
        model_id = models[name]
        print(f"  {name:20s} ({model_id}): ${cost:.4f}")
    print(f"  {'All models':20s}: ${total:.4f}")

    return costs
