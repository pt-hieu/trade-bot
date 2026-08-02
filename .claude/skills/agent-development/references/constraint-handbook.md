# Constraint Handbook: R:R + Entry Count Flow

How `min_rr` and `max_entries` flow from computation to enforcement.

## Single Source of Truth

`scripts/shared/rules/constraints.py` — all pure constraint logic.
`scripts/agents/strategy_constraints.py` — async wrapper (DB I/O only).

## Constraint Sources

| Source | Produces | File |
|--------|----------|------|
| Goal urgency | min_rr (3.0-4.0), max_picks (2-5) | `constraints.py:calculate_goal_urgency()` |
| Retro override | min_rr_override, max_entries | `agents/tools/retro_constraints.py` |
| Circuit breaker | floor entries at 1, cap R:R at 4.5 | `constraints.py:apply_circuit_breakers()` |
| Entry gate | binary block (CRISIS/LOW_CASH/REALLOCATION) | `shared/rules/entry_gates.py` |
| Regime floor | R:R floor by regime (2.0/3.0/4.5) | `shared/rules/rr_floors.py` |

## Composition Pipeline

```
Goal urgency ──→ compute_directive_constraints()
                         │
                         ▼
                  compose_with_retro()
                  max() for entries (anti-death-spiral)
                  min() for R:R (anti-death-spiral)
                         │
                         ▼
                  apply_circuit_breakers()
                  max(entries, 1)  — always allow 1
                  min(rr, 4.5)    — never demand > 4.5
                         │
                         ▼
                  inject_entry_gate()
                  entries_allowed + reason
                         │
                         ▼
                  PipelineConstraints dict
```

### Anti-Death-Spiral Logic

Goal and retro constraints serve different purposes. Compounding `min()` on both creates permanent paralysis. Instead:
- **Entries:** `max(goal_max, retro_max)` — take the MORE permissive value
- **R:R:** `min(goal_rr, retro_rr)` — take the LOWER bar

Each gate's bar is independently reasonable. The circuit breaker provides absolute safety net.

## Urgency Tiers

| Tier | on_track | days_left | min_rr | max_picks |
|------|----------|-----------|--------|-----------|
| NORMAL | True | any | 3.0 | 5 |
| AWARENESS | False | >15 | 3.0 | 5 |
| ELEVATED | False | 10-15 | 3.5 | 4 |
| HIGH | False | 5-10 | 4.0 | 3 |
| ACCEPTANCE | False | <=5 | 4.0 | 2 |
| DETERMINED | UNREACHABLE override | any | 3.5 | 3 |

**on_track calculation:** `realized >= expected_linear_progress * 0.7`
- 70% threshold: swing trading is lumpy, allows ~30% variance
- Edge cases: elapsed=0 → True, realized<0 → False

## Enforcement Gates

### Gate 1: `picks.py` (Phase 3b)
- Receives `min_rr` and `max_picks` from composed constraints
- Hard filter: `best_rr < min_rr → skip ticker`
- Hard cap: `picks[:max_picks]`

### Gate 2: `recommendation_validator.py` (Phase 6)
- Receives `min_rr` and `max_picks` from composed constraints
- Applies regime floor: `get_rr_floor(regime, min_rr)` — can only RAISE
- Hard filter: `risk_reward < rr_floor → drop`
- Hard cap: BUY count <= max_picks

### Binary Gate: Entry gate (Phase 2)
- `sector_filters.py` converts BUY → WATCH when entries_allowed=False
- Kills BUY signals at source — nothing reaches picks

## Pipeline Execution Order

```
Phase 3a:  compute_pipeline_constraints()   ← single DB fetch
Phase 3b:  picks.py                         ← uses composed min_rr/max_picks
Phase 3d:  strategy_director                ← receives pre-computed constraints
Phase 4:   synthesis                        ← embeds GOAL PROGRESS + ENTRY CRITERIA
Phase 6:   recommendation_validator         ← uses composed min_rr/max_picks
Midday:    midday_guardrails                ← reads persisted constraints from DB
```

## PipelineConstraints TypedDict

```python
class PipelineConstraints(TypedDict, total=False):
    budget_vnd: int
    max_new_entries: int
    min_rr: float
    urgency_tier: str
    goal_gap: int                    # for retro recovery math
    deployable: int
    retro_constraint_text: str | None
    retro_max_entries: int | None
    retro_scale_override: float | None
    retro_min_rr_override: float | None
    entries_allowed: bool
    entries_blocked_reason: str | None
```

## Common Pitfalls

- **Don't read goal urgency directly in enforcement code.** Use the composed constraints from `compute_pipeline_constraints()`. Direct reads bypass retro and circuit breakers.
- **Don't hardcode min_rr/max_picks.** Always pass from the constraints dict. The old hardcoded 3.0/5 in the validator was the root cause of the constraint bypass bug.
- **Regime floor is additive, not replacement.** `get_rr_floor()` takes `max(min_rr, regime_floor)` — it can only raise, never lower. The composed min_rr is the base.
- **Entry gate is parallel, not sequential.** It operates at Phase 2 (sector level), not at the constraint composition level. The constraints dict carries `entries_allowed` for display/midday but the actual BUY suppression happens earlier.
- **LLM STANCE R:R is advisory only.** The LLM-generated "R:R >= 4.0" in the STANCE section is never parsed or enforced. Only the deterministic ENTRY CRITERIA values matter.
