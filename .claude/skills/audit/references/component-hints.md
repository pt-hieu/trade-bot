# Component Hints

Starting points for auditable components. **These are hints, not truth** — the codebase changes. Always grep to confirm current shape and consumers.

## Quick Lookup

| Component | Aliases | DB Table | Key File |
|-----------|---------|----------|----------|
| market_level | regime, market_regime | `market_regimes` | `agents/market_level.py` |
| macro_metrics | macro | `macro_metrics`, `macro_events` | `agents/macro.py` |
| sector_analysis | sector, sector_ensemble | In-memory → `agent_beliefs` | `agents/sector.py` |
| beliefs | agent_beliefs | `agent_beliefs` | `pipeline/phase_beliefs.py` |
| positions_ensemble | positions, position_alerts | `position_ensemble_votes` | `agents/positions_ensemble.py` |
| advocate_reviews | advocate, bull_bear | `advocate_reviews` | `agents/advocate_reviewer.py` |
| strategy_director | strategy, directive | `strategy_directives` | `agents/strategy_director.py` |
| synthesis | brief, narrative | Filesystem only | `agents/synthesis.py` |
| trading_mode | mode | `daily_records.trading_mode` | `agents/trading_mode.py` |
| calibration_overlay | calibration, entry_gap | `calibration_insights` | `shared/calibration_overlay.py` |
| trailing_stops | stops | `trailing_stops` | `pipeline/trailing_stops.py` |
| foreign_flow | flow | `foreign_flows` | `agents/foreign_flow.py` |
| recommendations | recs | `daily_recommendations` | `pipeline/recommendation_builder.py` |
| enrichment | company_profiles, ticker_data | `company_profiles` (read) | `pipeline/enrichment_loader.py` |
| macro_trends | trends | In-memory | `pipeline/macro_trends.py` |

## Data Flow Patterns

Components pass data downstream via 3 mechanisms — grep for these to find consumers:

1. **Prompt injection** — `context_blocks*.py` formatters → text string → agent prompt. Search: `format_*_block`, `format_ticker_briefing`, `regime_context`, `InjectedContext`
2. **In-memory args** — Phase result dicts/dataclasses. Search: `Phase1Result`, `Phase2Result`, `PipelineContext`
3. **DB read-back** — Cross-pipeline (retro reads morning recs). Search: `shared/neon/*.py` query functions

## Key Context Formatters

These files transform component output into agent-consumable text:
- `pipeline/context_blocks.py` — regime, articles, company profiles
- `pipeline/context_blocks_ticker.py` — per-ticker briefings (flow, insider, RS, beliefs, macro transmission)
- `pipeline/context_blocks_macro.py` — macro signal → ticker impact mapping
- `pipeline/context_blocks_commodity.py` — commodity prices
- `pipeline/context_blocks_economy.py` — VN economy snapshot
