# scripts/hooks/ — pre-commit + pre-push lint surface

Local AST-based hooks registered in `.pre-commit-config.yaml`.

## Silent-hang / failover stack (SWI-306)

| Hook | Scope | Catches |
|------|-------|---------|
| `check_provider_timeouts.py` | `scripts/agents/*.py` | `_get_provider(timeout=N)` ≥ 120s without `# HOOK-ALLOW: long-timeout rationale=...`; `agent.run()` not inside `asyncio.wait_for` or `run_agent_with_total_timeout` |
| `check_provider_kwarg_passed.py` | `scripts/`, `tests/` | `emit_silent_provider_hang_span(...)` calls missing the required `provider=` kwarg |
| `check_outer_wall_helper.py` | `scripts/agents/*.py` | `asyncio.wait_for(..., timeout=<literal>)` and `run_agent_with_total_timeout(..., total_timeout_s=<literal>)` not derived from `OUTER_FALLBACK_STACK_WALL_S` / `OUTER_DISABLE_FALLBACK_WALL_S` |
| `check_swallow_pattern.py` | `scripts/agents/`, `scripts/pipeline/` | bare `except Exception` after a `wait_for` / `run_agent_with_total_timeout` without a typed `TimeoutError` (or `except* HopTimeout`) sibling clause |

### Suppression markers

Each hook honours one suppression comment placed on or within 3 lines above
the violating call site:

| Hook | Marker |
|------|--------|
| `check_provider_timeouts.py` (long-timeout) | `# HOOK-ALLOW: long-timeout rationale=...` |
| `check_provider_timeouts.py` (unguarded-agent-run) | `# HOOK-ALLOW: unguarded-agent-run rationale=...` |
| `check_outer_wall_helper.py` | `# HOOK-ALLOW: outer-wall-helper rationale=...` |
| `check_swallow_pattern.py` | `# HOOK-ALLOW: silent-swallow rationale=...` |

Always quote the SWI-306 follow-up in the rationale so the suppression
expires when the underlying issue is closed.

## Why each guard exists

* **Producer wire severance** (`check_provider_kwarg_passed.py`) — between
  2026-03 and 2026-05 every emit-site dropped the suspected provider slug
  into `**extra: Any`. The session-side dynamic exclude list never saw
  it, so OpenRouter kept routing through the same bad backend across 15
  consecutive incidents. Forcing `provider=` makes the silence audible.
* **Wall-equality starvation** (`check_outer_wall_helper.py`) — the
  2026-05-10 silent-hang cascade root-caused to
  `per_attempt_wall_s` matching `PRIMARY_HOP_WALL_S` (literal `180` at the time; tightened to `75` in SWI-318). The
  outer `asyncio.wait_for` cancelled at the exact instant the inner hop
  wall fired, starving `RetryModel` and `FallbackModel`. Deriving outer
  walls from the per-hop budget keeps the failover stack alive.
* **Generic-Exception swallow** (`check_swallow_pattern.py`) — bare
  `except Exception` after a guarded `await wait_for(...)` catches both
  `TimeoutError` AND `HopTimeout`, defeating the typed-exception fix
  that lets emit-sites extract provider context.
