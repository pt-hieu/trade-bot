# trade-bot

A multi-agent LLM pipeline that analyses Vietnamese stocks (HOSE / HNX / UPCoM) and produces
swing-trading recommendations. It runs on a schedule, writes every decision to PostgreSQL, and
grades itself after the market closes.

This is a personal research project, published as a reference for anyone building agentic
pipelines over financial data.

> **This is not financial advice.** See [Disclaimer](#disclaimer) before you read anything else.

---

## What it does

Three scheduled runs per trading day:

| Run | Time (UTC) | Time (Vietnam) | Purpose |
|---|---|---|---|
| Daily scan | 22:00 | 05:00, pre-open | News, macro, sector rotation, candidate picks |
| Midday check | 05:00 | 12:00, lunch break | Review open positions against the morning session |
| Close retrospective | 08:00 | 15:00, post-close | Grade the day's calls, update the belief model |

Each run is a pipeline of ~38 PydanticAI agents. Agents specialise: one reads macro, one reads
sector flow, one argues the bull case, one argues the bear case, one criticises the result. A
final synthesis agent produces the recommendation.

The retrospective is the part that matters. Every recommendation is scored against what the
market actually did, and the accuracy record feeds back into the next run's prompts. The system
knows its own hit rate per signal type.

## Architecture

```
GitHub Actions (cron)
  └── pipeline phases (Python, async)
        ├── Phase 0    fetch + batch — one fetcher per data source, no redundant calls
        ├── Phase 1    macro / regime / news agents
        ├── Phase 2    per-ticker analysis (parallel fan-out) + health gate
        ├── Phase 3    trading mode, constraints, pre-computed top picks
        ├── Phase 3.5  advocate reviews → gate filtering
        ├── Phase 4    strategy director → synthesis
        ├── Phase 5    alert registration
        └── Phase 6    write recommendations → PostgreSQL
```

Four design rules shape the whole codebase:

**Inject, don't fetch.** Agents receive their data pre-loaded in the system prompt. Tools are
reserved for genuine follow-up questions. Budget is ≤7K tokens injected per agent. This roughly
halves latency versus a tool-calling-first design, and accuracy goes up — an agent that spends
its reasoning on retrieval has less left for analysis.

**Per-agent tool allowlists with an escape hatch.** No agent sees all 45 broker tools. Each YAML
config declares `allowed_tools`. When an agent hits a real data gap it calls
`unlock_tool(tool_name=...)` to admit one more for the rest of its run. Visible surface caps at
15 tools.

**Python owns arithmetic, the LLM owns judgement.** Structural invariants, position sizing, and
risk-reward maths are deterministic Python in `scripts/shared/rules/`. The LLM decides
EXIT/HOLD, reads sentiment, and resolves conflicting signals. A Python gate never downgrades an
LLM's qualitative verdict — if the verdict is wrong, the prompt is wrong.

**Fail closed.** Missing data maps to the most conservative value, never to a permissive default.

## Layout

| Path | What lives there |
|---|---|
| `scripts/agents/` | Agent implementations; `configs/*.yaml` holds every prompt and model pin |
| `scripts/pipeline/` | Phase orchestration and typed inter-phase contracts |
| `scripts/shared/rules/` | Deterministic trading rules — the single source of truth |
| `scripts/db/migrations/` | Numbered SQL migrations; the only way schema changes |
| `vnstock-api/` | FastAPI service wrapping the `vnstock` market-data library |
| `mcp-server/` | Read-only MCP server exposing trading data to LLM clients |
| `web/` | Dashboard — React 19, TanStack Start, Tailwind 4, Cloudflare Workers |
| `evals/` | Agent evaluation harness (`pydantic-evals`) |
| `tests/` | pytest suite |

## Running it

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and PostgreSQL.

```bash
uv sync

# vnstock prompts interactively to accept its terms on first run. Set this or the
# pipeline blocks on stdin in CI. Accepting means accepting the vnstock licence —
# read THIRD_PARTY_LICENSES.md first.
export ACCEPT_TC="tôi đồng ý"

docker compose up -d          # local PostgreSQL on 127.0.0.1:5432

# Schema: load the baseline, then apply migrations in numeric order.
psql "$DATABASE_URL" -f scripts/db/schema.sql
for f in scripts/db/migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done

# Six migrations are Python, not SQL, and are NOT covered by the loop above or by the
# drift guard. Apply them by hand, in numeric order, with the owner connection:
#   DATABASE_OWNER_URL=... uv run python scripts/db/migrations/<name>.py
# 104 seeds from research/ notes that are not published — skip it on a fresh clone.

cp web/.env.example web/.env  # then fill in your own keys
SWINGY_DRY_RUN=1 uv run python scripts/daily_scan.py
```

`SWINGY_DRY_RUN=1` runs the full pipeline without writing to the database. Start there.
`scripts/daily_scan.py` also takes `--force`, `--check`, and `--mark-holiday`.

There is no migration runner: migrations are applied manually, and the pipeline aborts at
startup if the applied `.sql` set drifts from `scripts/db/migrations/`.

Tests:

```bash
uv run pytest
```

## Configuration

All secrets come from the environment. Nothing is committed.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection (read-only role for pipelines) |
| `DATABASE_OWNER_URL` | Owner role — DDL and migrations only |
| `OPENROUTER_API_KEY` | LLM inference, via OpenRouter |
| `LOGFIRE_TOKEN` | Tracing (optional) |
| `LOGFIRE_ENVIRONMENT` | Tracing environment label (optional) |
| `VNSTOCK_API_URL` | Market-data service endpoint |
| `VNSTOCK_API_KEY` | Market-data service auth — required; the service refuses to serve without it |
| `VNSTOCK_ALLOWED_ORIGINS` | Comma-separated CORS origins for the market-data service, e.g. `https://dashboard.example.com`. Defaults to `http://localhost:3000` — set it or the deployed dashboard's live stream is CORS-blocked |
| `ACCEPT_TC` | `tôi đồng ý` — accepts the vnstock licence. Without it, first run blocks on an interactive prompt |
| `MCP_API_KEY` | Required by `mcp-server/`. It refuses to start without one |
| `MCP_HOST` / `MCP_PORT` | MCP bind address, default `127.0.0.1:8001` |
| `GITHUB_REPO` | `owner/repo` for alert-triggered workflow dispatch |
| `GITHUB_TOKEN` | Token for that dispatch |
| `TELEGRAM_BOT_TOKEN` | Alert delivery (optional) |
| `TELEGRAM_CHAT_ID` | Alert delivery target (optional) |
| `SWINGY_ENV` | `production` enables live writes; anything else stays local |
| `SWINGY_DRY_RUN` | `1` runs the pipeline without writing to the database |

## Licence

This repository's own code is MIT — see `LICENSE`.

**The `vnstock` dependency is not open source.** It is personal-use-only and forbids
redistribution and commercial use. Read `THIRD_PARTY_LICENSES.md` before you run this for
anything other than personal research.

## Disclaimer

This software is a personal research experiment. It is published for its engineering, not its
returns.

- **It is not financial advice, and it is not an offer to buy or sell any security.**
- LLMs hallucinate. This one is pointed at financial data, which does not make it more reliable.
- It was built for one person's risk tolerance, one market, and one account size. None of those
  are yours.
- Past performance of any strategy here says nothing about future results.
- Trading equities can lose you money, including all of it.

Do your own research. If you run this with real money, that decision and every consequence of it
are yours alone. The author accepts no liability. See [LICENSE](LICENSE).
