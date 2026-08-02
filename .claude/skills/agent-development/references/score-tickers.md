# Ad-hoc Scoring (no full pipeline run)

`scripts/eval/score_tickers.py` SCORES tickers without invoking the full daily-scan pipeline. It does NOT fit weights and is NOT a backtest — naming follows the `weight_correlation_audit.py` discipline (SWI-177).

## Two modes

### Replay

```
uv run python scripts/eval/score_tickers.py \
    --mode replay \
    --tickers VHM,VIC,FPT \
    [--scan-date YYYY-MM-DD] \
    [--weights-file path.yaml]
```

Reads historical `pre_gate_candidates` rows and rescores under current (or hypothetical) weights. READ-ONLY against the audit table. Hypothetical-weights output rows are tagged `[HYPOTHETICAL]`; the script never writes back.

`--weights-file` must be a full alternate `scoring.yaml` (12 keys, Σw=1, valid SemVer) — `load_scoring_config(path=...)` validates it.

### Fresh

```
uv run python scripts/eval/score_tickers.py \
    --mode fresh \
    --tickers VHM,VIC,FPT \
    [--scan-date YYYY-MM-DD]
```

Fetches live technicals (`get_batch_ticker_data_async`) + foreign-flow (`get_daily_flow_batch`), reuses `agents.picks_audit.build_score_inputs` for ScoreInputs assembly (single derivation path), and calls `compute_score(..., sim_populated=False)`. No simulation/strategy/belief; neutral defaults for those features.

## Purity invariant

Orchestration lives in `scripts/eval/`. `scripts/shared/rules/scoring/` stays pure-Python per the `check_no_async_in_scoring.py` pre-commit guard. `compute_score` accepts an explicit `config: ScoringConfig` to bypass the module-level cache when comparing weight vectors.
