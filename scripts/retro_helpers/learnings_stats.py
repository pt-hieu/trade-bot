"""Deterministic stat calculators for learnings metrics."""


def calc_midday_adjustment_stats(midday_records: list[dict]) -> dict:
    """Aggregate midday adjustment metrics from midday_summaries data."""
    total_adjustments = 0
    total_helpful = 0
    accuracy_values: list[float] = []
    when_helpful: list[str] = []
    when_harmful: list[str] = []

    for record in midday_records:
        summary = record.get("midday_summary") or {}
        made = summary.get("adjustments_made") or 0
        helpful = summary.get("adjustments_helpful") or 0
        harmful = summary.get("adjustments_harmful") or 0
        total_adjustments += made
        total_helpful += helpful

        accuracy = summary.get("afternoon_accuracy")
        if accuracy is not None:
            accuracy_values.append(float(accuracy))

        key_adj = summary.get("key_adjustment")
        if key_adj and made > 0:
            if helpful > harmful:
                when_helpful.append(key_adj)
            elif harmful > helpful:
                when_harmful.append(key_adj)

    return {
        "adjustment_win_rate": round(total_helpful / total_adjustments, 2)
        if total_adjustments > 0
        else 0.0,
        "when_helpful": when_helpful[-5:],
        "when_harmful": when_harmful[-5:],
        "average_improvement": round(sum(accuracy_values) / len(accuracy_values), 4)
        if accuracy_values
        else 0.0,
    }


def calc_mode_appropriate_win_rate(midday_records: list[dict]) -> float:
    """Win rate of evaluations on mode-compliant days (0-1 ratio)."""
    wins = 0
    total = 0
    for record in midday_records:
        if not record.get("mode_compliance", True):
            continue
        for evaluation in record.get("evaluations", []):
            if evaluation.get("won") is not None:
                total += 1
                if evaluation.get("won"):
                    wins += 1
    return round(wins / total, 2) if total > 0 else 0.0
