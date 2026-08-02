"""
Deterministic retro-feedback constraint computation.

Queries learning_patterns and learnings_summary directly (no embedding search).
Returns hard constraints that flow into strategy_director's deterministic sections.
"""

from datetime import date

from shared.trading_config import get_trading_config


async def compute_retro_constraints(scan_date: date | None = None) -> dict:
    """Compute hard constraints from historical pattern performance.

    Thresholds are read from the trading_config DB table (configurable via /config UI):
      - win_rate < retro_moderate_winrate → max_entries capped, min_rr raised
      - win_rate < retro_severe_winrate   → severe entry cap, scale reduced
      - losing pattern with loss_rate >= 70%, sample >= 3 → avoid_actions list

    Returns:
        {
          "max_entries": int | None,           # None = no override
          "scale_override": float | None,      # None = no override
          "min_rr_override": float | None,     # None = no override
          "avoid_actions": list[str],          # action types to avoid
          "constraint_text": str,              # formatted for directive
          "win_rate": float | None,            # overall recent win rate
        }
    """
    try:
        from shared.database import get_db

        db = await get_db()

        # Load learnings summary (overall win rate)
        summary_row = await db.fetch_one(
            "SELECT overall_win_rate, total_recs FROM learnings_summary LIMIT 1"
        )

        # Load high-loss patterns
        pattern_rows = await db.fetch_all(
            """
            SELECT pattern_type, pattern_description, loss_rate, sample_size, avoid_rule
            FROM learning_patterns
            WHERE pattern_type = 'losing'
              AND loss_rate >= 0.70
              AND sample_size >= 3
            ORDER BY loss_rate DESC
            LIMIT 5
            """
        )
    except Exception as e:
        return _empty_constraints(f"DB query failed: {e}")

    # Load configurable thresholds (falls back to dataclass defaults if not initialized)
    try:
        cfg = get_trading_config()
    except RuntimeError:
        from shared.trading_config import TradingConfig

        cfg = TradingConfig()  # use defaults (dev/test fallback)

    severe_threshold = cfg.retro_severe_winrate / 100
    moderate_threshold = cfg.retro_moderate_winrate / 100

    # Parse summary — overall_win_rate stored as 0-100 scale (e.g. 39.34), normalize to 0-1
    win_rate = None
    if summary_row:
        raw = summary_row.get("overall_win_rate")
        if raw is not None:
            win_rate = float(raw) / 100 if float(raw) > 1 else float(raw)

    # Build constraints from config values
    max_entries = None
    scale_override = None
    min_rr_override = None

    if win_rate is not None:
        if win_rate < severe_threshold:
            max_entries = cfg.retro_severe_max_entries
            scale_override = cfg.retro_severe_scale
            min_rr_override = cfg.retro_severe_min_rr
        elif win_rate < moderate_threshold:
            max_entries = cfg.retro_moderate_max_entries
            min_rr_override = cfg.retro_moderate_min_rr

    # Build avoid_actions from high-loss patterns
    avoid_actions = []
    avoid_lines = []
    for row in pattern_rows or []:
        avoid_rule = row.get("avoid_rule", "")
        desc = row.get("pattern_description", "")
        loss_rate = row.get("loss_rate", 0)
        n = row.get("sample_size", 0)
        if avoid_rule:
            avoid_actions.append(avoid_rule)
            avoid_lines.append(f"  - {desc}: {loss_rate:.0%} loss rate (n={n}) — {avoid_rule}")

    # Build constraint text
    parts = ["RETRO CONSTRAINTS"]
    if win_rate is not None:
        wr_pct = f"{win_rate:.0%}"
        if (
            max_entries is not None
            and max_entries <= cfg.retro_severe_max_entries
            and scale_override
        ):
            parts.append(
                f"- Win rate {wr_pct} — MAX {max_entries} entr{'y' if max_entries == 1 else 'ies'}, "
                f"R:R >= {min_rr_override} required (below {cfg.retro_severe_winrate:.0f}% threshold)"
            )
            parts.append(
                f"- Scale: {scale_override}x (defensive sizing). Selectivity over quantity — one great trade beats zero."
            )
        elif max_entries is not None:
            parts.append(
                f"- Win rate {wr_pct} — MAX {max_entries} entries, "
                f"R:R >= {min_rr_override} required (below {cfg.retro_moderate_winrate:.0f}% threshold)"
            )
        else:
            parts.append(f"- Win rate {wr_pct} — normal constraints apply")
    else:
        parts.append("- No win rate data available")

    if avoid_lines:
        parts.append("- High-loss patterns to avoid:")
        parts.extend(avoid_lines)

    return {
        "max_entries": max_entries,
        "scale_override": scale_override,
        "min_rr_override": min_rr_override,
        "avoid_actions": avoid_actions,
        "constraint_text": "\n".join(parts),
        "win_rate": win_rate,
    }


def _empty_constraints(reason: str = "") -> dict:
    return {
        "max_entries": None,
        "scale_override": None,
        "min_rr_override": None,
        "avoid_actions": [],
        "constraint_text": f"RETRO CONSTRAINTS\n- Unavailable ({reason})",
        "win_rate": None,
    }
