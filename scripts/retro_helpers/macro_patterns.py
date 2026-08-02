"""
Deterministic macro and rotation pattern calculations.
Extracted from retrospective.py for the 300-line file limit.
"""


def calculate_macro_patterns(macro_records: list[dict]) -> dict:
    """
    Calculate rolling macro regime accuracy metrics from daily records.

    Args:
        macro_records: List of daily macro_evaluation dicts

    Returns:
        Aggregated macro patterns
    """
    if not macro_records:
        return {
            "total_days": 0,
            "overall_accuracy": 0.0,
            "regime_accuracy": {
                "CALM": {"days": 0, "correct": 0, "avg_vn_change": 0.0},
                "CAUTIOUS": {"days": 0, "correct": 0, "avg_vn_change": 0.0},
                "ELEVATED": {"days": 0, "correct": 0, "avg_vn_change": 0.0},
                "CRISIS": {"days": 0, "correct": 0, "avg_vn_change": 0.0},
            },
            "false_alarms": 0,
            "missed_drops": 0,
            "missed_opportunities": 0,
        }

    total_days = len(macro_records)
    correct_predictions = 0
    false_alarms = 0
    missed_drops = 0
    missed_opportunities = 0

    regime_stats = {
        "CALM": {"days": 0, "correct": 0, "vn_changes": []},
        "CAUTIOUS": {"days": 0, "correct": 0, "vn_changes": []},
        "ELEVATED": {"days": 0, "correct": 0, "vn_changes": []},
        "CRISIS": {"days": 0, "correct": 0, "vn_changes": []},
    }

    for record in macro_records:
        regime = record.get("global_risk_regime") or "CAUTIOUS"
        appropriate = record.get("regime_appropriate")
        vn_change = record.get("vn_index_change_pct")

        if regime in regime_stats:
            regime_stats[regime]["days"] += 1
            if vn_change is not None:
                regime_stats[regime]["vn_changes"].append(vn_change)
            if appropriate is True:
                regime_stats[regime]["correct"] += 1
                correct_predictions += 1
            elif appropriate is False:
                # False alarm: predicted danger but market rallied strongly (>1%)
                if regime in ("ELEVATED", "CRISIS") and vn_change is not None and vn_change > 1.0:
                    false_alarms += 1
                elif regime == "CALM" and vn_change is not None and vn_change < -1.0:
                    missed_drops += 1

            # Missed opportunity: defensive regime but market rallied >1.5%.
            # Intentionally independent of appropriate/false_alarms — measures opportunity
            # cost across all defensive days, not just incorrect ones.
            if (
                regime in ("CAUTIOUS", "ELEVATED", "CRISIS")
                and vn_change is not None
                and vn_change > 1.5
            ):
                missed_opportunities += 1

    regime_accuracy = {}
    for regime, stats in regime_stats.items():
        avg_change = (
            round(sum(stats["vn_changes"]) / len(stats["vn_changes"]), 2)
            if stats["vn_changes"]
            else 0.0
        )
        regime_accuracy[regime] = {
            "days": stats["days"],
            "correct": stats["correct"],
            "avg_vn_change": avg_change,
        }

    overall_accuracy = round(correct_predictions / total_days, 2) if total_days > 0 else 0.0

    return {
        "total_days": total_days,
        "overall_accuracy": overall_accuracy,
        "regime_accuracy": regime_accuracy,
        "false_alarms": false_alarms,
        "missed_drops": missed_drops,
        "missed_opportunities": missed_opportunities,
    }


def calculate_rotation_patterns(rotation_records: list[dict]) -> dict:
    """
    Calculate rolling rotation accuracy metrics from daily records.

    Args:
        rotation_records: List of daily rotation_evaluation dicts

    Returns:
        Aggregated rotation patterns
    """
    if not rotation_records:
        return {
            "total_days": 0,
            "overall_accuracy": 0.0,
            "hot_hit_rate": 0.0,
            "cold_hit_rate": 0.0,
            "avg_hot_vs_market": 0.0,
            "avg_cold_vs_market": 0.0,
            "sector_rotation_score": {},
        }

    total_days = len(rotation_records)

    hot_hit_rates = [record.get("hot_hit_rate") or 0 for record in rotation_records]
    cold_hit_rates = [record.get("cold_hit_rate") or 0 for record in rotation_records]
    hot_vs_market = [record.get("hot_vs_market") or 0 for record in rotation_records]
    cold_vs_market = [record.get("cold_vs_market") or 0 for record in rotation_records]

    avg_hot_hit = sum(hot_hit_rates) / len(hot_hit_rates) if hot_hit_rates else 0
    avg_cold_hit = sum(cold_hit_rates) / len(cold_hit_rates) if cold_hit_rates else 0

    sector_scores: dict[str, dict] = {}
    for record in rotation_records:
        sector_returns = record.get("sector_returns") or {}
        market_avg = record.get("market_avg_return") or 0

        for sector_name in record.get("hot_sectors") or []:
            if sector_name not in sector_scores:
                sector_scores[sector_name] = {"as_hot": [], "as_cold": []}
            was_accurate = (sector_returns.get(sector_name) or 0) > market_avg
            sector_scores[sector_name]["as_hot"].append(1 if was_accurate else 0)

        for sector_name in record.get("cold_sectors") or []:
            if sector_name not in sector_scores:
                sector_scores[sector_name] = {"as_hot": [], "as_cold": []}
            was_accurate = (sector_returns.get(sector_name) or 0) < market_avg
            sector_scores[sector_name]["as_cold"].append(1 if was_accurate else 0)

    sector_rotation_score = {}
    for sector_name, scores in sector_scores.items():
        sector_rotation_score[sector_name] = {
            "as_hot": round(sum(scores["as_hot"]) / len(scores["as_hot"]), 2)
            if scores["as_hot"]
            else 0,
            "as_cold": round(sum(scores["as_cold"]) / len(scores["as_cold"]), 2)
            if scores["as_cold"]
            else 0,
        }

    return {
        "total_days": total_days,
        "overall_accuracy": round((avg_hot_hit + avg_cold_hit) / 2, 2),
        "hot_hit_rate": round(avg_hot_hit, 2),
        "cold_hit_rate": round(avg_cold_hit, 2),
        "avg_hot_vs_market": round(sum(hot_vs_market) / len(hot_vs_market), 2)
        if hot_vs_market
        else 0,
        "avg_cold_vs_market": round(sum(cold_vs_market) / len(cold_vs_market), 2)
        if cold_vs_market
        else 0,
        "sector_rotation_score": sector_rotation_score,
    }
