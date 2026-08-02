#!/usr/bin/env python3
"""
Platt scaling for belief probability calibration.

Fits logistic regression P_calibrated = 1/(1+exp(-(a*P_raw + b)))
on historical (predicted_probability, actual_outcome) pairs.

Research: AIA Forecaster achieved Brier improvement 0.1140 → 0.1076
with Platt coefficient sqrt(3) ~ 1.73. KalshiBench showed all LLMs
are systematically overconfident — post-hoc calibration is mandatory.
"""

import logging
import math

logger = logging.getLogger(__name__)

# Minimum scored beliefs before fitting Platt parameters
MIN_SAMPLES_FOR_FIT = 30


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


def fit_platt_parameters(
    predicted_probabilities: list[float],
    actual_outcomes: list[int],  # 0 or 1
    learning_rate: float = 0.01,
    iterations: int = 1000,
) -> tuple[float, float] | None:
    """Fit Platt scaling parameters (a, b) via gradient descent.

    Pure Python — no sklearn dependency.

    Args:
        predicted_probabilities: raw model probabilities
        actual_outcomes: binary outcomes (1=event occurred, 0=not)
        learning_rate: gradient descent step size
        iterations: number of gradient descent iterations

    Returns:
        (a, b) parameters for sigmoid calibration, or None if insufficient data
    """
    if len(predicted_probabilities) < MIN_SAMPLES_FOR_FIT:
        logger.info(
            "Only %d samples, need %d for Platt fit — skipping calibration",
            len(predicted_probabilities),
            MIN_SAMPLES_FOR_FIT,
        )
        return None  # caller should skip Platt scaling entirely

    platt_a = 1.0
    platt_b = 0.0
    n = len(predicted_probabilities)

    for _ in range(iterations):
        gradient_a = 0.0
        gradient_b = 0.0

        for predicted, actual in zip(predicted_probabilities, actual_outcomes, strict=False):
            calibrated = _sigmoid(platt_a * predicted + platt_b)
            error = calibrated - actual
            gradient_a += error * predicted
            gradient_b += error

        platt_a -= learning_rate * gradient_a / n
        platt_b -= learning_rate * gradient_b / n

    logger.info("Platt fit: a=%.4f, b=%.4f (n=%d)", platt_a, platt_b, n)
    return platt_a, platt_b


def apply_platt_scaling(
    raw_probability: float,
    platt_a: float,
    platt_b: float,
) -> float:
    """Apply Platt scaling to a single probability."""
    return _sigmoid(platt_a * raw_probability + platt_b)


def calibrate_belief_probabilities(
    bull: float,
    base: float,
    bear: float,
    platt_a: float,
    platt_b: float,
) -> tuple[float, float, float]:
    """Apply Platt scaling to all three scenario probabilities and renormalize.

    WARNING: Parameters (a, b) are fit on bull_probability only. Applying the
    same sigmoid to base and bear is mathematically unsound for 3-way distributions
    and causes signal inversion when a < 0. This function should only be used for
    binary calibration targets. See MON-2026-04-13-003 for the production impact.
    """
    calibrated_bull = apply_platt_scaling(bull, platt_a, platt_b)
    calibrated_base = apply_platt_scaling(base, platt_a, platt_b)
    calibrated_bear = apply_platt_scaling(bear, platt_a, platt_b)

    total = calibrated_bull + calibrated_base + calibrated_bear
    if total == 0:
        return 0.35, 0.40, 0.25  # fallback to base rates

    return (
        round(calibrated_bull / total, 4),
        round(calibrated_base / total, 4),
        round(calibrated_bear / total, 4),
    )
