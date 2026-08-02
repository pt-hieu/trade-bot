"""
Shared helpers for eval infrastructure.

- load_prompt: Load agent system prompt from YAML config
- load_config: Load full AgentConfig from YAML config
- get_eval_model: Get model with optional override for comparison runs
"""

import os
from pathlib import Path

from pydantic_ai.models.openai import OpenAIChatModel

DATASETS_DIR = Path(__file__).parent / "datasets"


async def load_prompt(agent_key: str) -> str:
    """Load system prompt from YAML config.

    Args:
        agent_key: Agent identifier (e.g., 'market_level')

    Returns:
        System prompt string
    """
    config = await load_config(agent_key)
    return config.system_prompt


async def load_config(agent_key: str):
    """Load full AgentConfig from YAML config.

    Args:
        agent_key: Agent identifier (e.g., 'market_level')

    Returns:
        AgentConfig instance
    """
    from shared.agent_config import load_agent_config

    return await load_agent_config(agent_key)


# Cost per million tokens (input, output) by model
MODEL_COSTS = {
    "moonshotai/Kimi-K2.5": (0.50, 2.80),
    "minimax/minimax-m2.7": (0.50, 2.80),
    "Qwen/Qwen2.5-7B-Instruct-Turbo": (0.30, 0.30),
}

# Default models for comparison runs
EVAL_MODELS = {
    "kimi_k25": "moonshotai/Kimi-K2.5",
    "minimax_m27": "minimax/minimax-m2.7",
    "qwen_25_7b": "Qwen/Qwen2.5-7B-Instruct-Turbo",
}

_DEFAULT_EVAL_MODEL = "moonshotai/Kimi-K2.5"


def get_eval_model(role: str = "heavy") -> OpenAIChatModel:
    """Get model for eval runs — supports EVAL_MODEL_OVERRIDE env var.

    Priority:
    1. EVAL_MODEL_OVERRIDE env var (for model comparison)
    2. Default eval model (Kimi-K2.5)

    Args:
        role: Unused, kept for call-site compatibility

    Returns:
        Configured OpenAIChatModel
    """
    from agents.model import _get_provider

    model_id = os.environ.get("EVAL_MODEL_OVERRIDE") or _DEFAULT_EVAL_MODEL
    return OpenAIChatModel(model_id, provider=_get_provider())


def estimate_cost(
    n_cases: int,
    n_trials: int = 1,
    avg_input_tokens: int = 2000,
    avg_output_tokens: int = 500,
    models: dict[str, str] | None = None,
) -> dict[str, float]:
    """Estimate cost for an eval run.

    Args:
        n_cases: Number of test cases
        n_trials: Trials per case
        avg_input_tokens: Average input tokens per case
        avg_output_tokens: Average output tokens per case
        models: Model dict (name -> model_id), defaults to EVAL_MODELS

    Returns:
        Dict of model_name -> estimated cost in USD
    """
    models = models or EVAL_MODELS
    total_calls = n_cases * n_trials
    costs = {}
    for name, model_id in models.items():
        in_cost, out_cost = MODEL_COSTS.get(model_id, (1.0, 3.0))
        cost = (
            total_calls * avg_input_tokens * in_cost / 1_000_000
            + total_calls * avg_output_tokens * out_cost / 1_000_000
        )
        costs[name] = round(cost, 4)
    return costs
