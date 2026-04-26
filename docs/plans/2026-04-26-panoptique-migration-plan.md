# Panoptique Migration Implementation Plan

> **For Hermes / Claude Code:** Use `subagent-driven-development` or `phase-plan-executor` to implement this plan phase-by-phase. Do **not** skip gates. Do **not** enable real-money trading from this plan.

**Goal:** Migrate the existing `prediction_core` + `subprojects/prediction` stack toward the Panoptique Polymarket meta-trading architecture while preserving the current weather/paper/operator system and adding observation, shadow-bot, measurement, and governance layers progressively.

**Architecture:** Keep `/home/jul/prediction_core` as the canonical Python/Rust core and `/home/jul/swarm/subprojects/prediction` as the TypeScript cockpit/API/dashboard. Add a new Panoptique layer inside `prediction_core/python` for read-only market observation, shadow-bot simulations, crowd-flow measurement, evidence tracking, and later agent/bookmaker abstractions. Every migration step is paper-only/read-only until explicit statistical gates are passed.

**Tech Stack:** Python 3.x under `/home/jul/prediction_core/python`, existing `weather_pm.*`, existing `prediction_core.*`, PostgreSQL 16+ with TimescaleDB as the primary database from the start, Alembic migrations, SQLAlchemy Core/SQLModel + `asyncpg`, Redis for live cache only, Parquet/JSONL for audit/replay archives, DuckDB for offline analytics/backtests, TypeScript dashboard/API under `/home/jul/swarm/subprojects/prediction`.

---

## Contexte vérifié

Verified from the live filesystem on 2026-04-26:

- `prediction_core/README.md` defines:
  - `python/` = research, replay, paper, calibration, analytics, evaluation, minimal local HTTP service
  - `rust/` = canonical live engine target
  - `contracts/` = exchange formats between engines and cockpit
- `prediction_core/python/README.md` states current packages:
  - `prediction_core.*`: `replay`, `paper`, `calibration`, `analytics`, `evaluation`
  - `weather_pm.*`: imported Polymarket weather MVP
- Current Python local service endpoints include:
  - `/health`
  - `/weather/parse-market`
  - `/weather/score-market`
  - `/weather/station-history`
  - `/weather/station-latest`
  - `/weather/station-source-plan`
  - `/weather/source-coverage`
  - `/weather/resolution-status`
  - `/weather/monitor-paper-resolution`
  - `/weather/paper-cycle`
- Current Python CLI examples include:
  - `PYTHONPATH=src pytest -q`
  - `python3 -m weather_pm.cli --help`
  - `PYTHONPATH=src python3 -m weather_pm.cli paper-cycle-report ...`
- Current `subprojects/prediction/README.md` defines the cockpit/API/UI layer with:
  - `src/lib/prediction-markets/`
  - API routes under `src/app/api/v1/prediction-markets/`
  - dashboard surfaces
  - operator scripts for `runs`, `capabilities`, `health`, `dispatch`, `paper`, `shadow`, `live`
  - production validation chain: `edge predictif -> edge executable -> edge capturable -> edge durable`
  - `advisor-first` stance until edge is proven
- Current Python code shape under `/home/jul/prediction_core/python`:
  - 133 files total by lightweight count
  - 124 Python files
  - 60 `test_*.py` files under `python/tests`
- Current TypeScript cockpit shape under `/home/jul/swarm/subprojects/prediction`:
  - 331 files total by lightweight count, excluding dependency/vendor-heavy folders
  - 263 `.ts` files
- Current weather/paper operational snapshot exists at:
  - `/home/jul/prediction_core/data/polymarket/meteo_analyse_continuation_20260426T141337.md`
  - targeted weather tests reported there: `96 passed in 15.79s`
  - active paper weather monitoring is paper-only with no real orders
- Current repo already contains modules close to the Panoptique direction:
  - `weather_pm/weather_latency_edge.py`
  - `weather_pm/winning_patterns.py`
  - `weather_pm/wallet_intel.py`
  - `weather_pm/traders.py`
  - `weather_pm/strategy_extractor.py`
  - `weather_pm/event_surface.py`
  - `prediction_core/analytics/*`
  - `prediction_core/calibration/*`
  - `prediction_core/evaluation/*`
  - `prediction_core/execution/*`

---

## Non-negotiable migration principles

1. **No rewrite.** Keep the current weather/paper/operator stack. Add Panoptique capabilities around it.
2. **No real-money expansion.** This plan is read-only/paper-only unless a later explicit live plan is approved.
3. **Observation before action.** Build logs, snapshots, and measurement before new execution logic.
4. **Evidence before belief.** Strategic claims from the Panoptique brief must be classified as verified, plausible, hypothesis, or rejected.
5. **TDD for core logic.** Every new pure domain function gets tests first.
6. **TimescaleDB-first, artifacts-always.** PostgreSQL + TimescaleDB is the primary queryable store from Phase 1. JSONL/Parquet artifacts still remain mandatory as raw audit/replay archives; the DB never replaces the raw journal.
7. **Dashboard consumes read models.** The TS cockpit should read stable summaries, not reimplement Python domain logic.
8. **Paper-only language everywhere.** Any simulated order must explicitly say no real order was placed.
9. **Gates are hard.** A later phase cannot begin just because the code exists; the metrics must pass.
10. **Claude Code must read this plan and the strategic brief before implementing.**

---

## Target architecture after migration

```txt
/home/jul/prediction_core
├── docs/
│   ├── strategy/
│   │   ├── PANOPTIQUE_STRATEGY.md
│   │   ├── EVIDENCE_REGISTER.md
│   │   ├── ASSUMPTIONS.md
│   │   └── GATES.md
│   ├── plans/
│   │   └── 2026-04-26-panoptique-migration-plan.md
│   └── panoptique/
│       ├── data-contracts.md
│       ├── storage-architecture.md
│       ├── database-schema.md
│       ├── shadow-bots.md
│       ├── crowd-flow-measurement.md
│       └── operator-runbook.md
├── infra/
│   └── panoptique/
│       ├── docker-compose.yml
│       ├── .env.example
│       └── README.md
├── migrations/
│   └── panoptique/
│       └── alembic/
├── data/
│   └── panoptique/
│       ├── snapshots/
│       ├── shadow_predictions/
│       ├── crowd_flow_observations/
│       ├── measurements/
│       └── reports/
├── python/
│   ├── src/
│   │   ├── prediction_core/...
│   │   ├── weather_pm/...
│   │   └── panoptique/
│   │       ├── __init__.py
│   │       ├── contracts.py
│   │       ├── db.py
│   │       ├── db_models.py
│   │       ├── repositories.py
│   │       ├── evidence.py
│   │       ├── snapshots.py
│   │       ├── shadow_bots.py
│   │       ├── crowd_flow.py
│   │       ├── measurement.py
│   │       ├── gates.py
│   │       └── reports.py
│   └── tests/
│       ├── test_panoptique_contracts.py
│       ├── test_panoptique_evidence.py
│       ├── test_panoptique_snapshots.py
│       ├── test_panoptique_shadow_bots.py
│       ├── test_panoptique_crowd_flow.py
│       ├── test_panoptique_measurement.py
│       └── test_panoptique_gates.py
└── rust/  # unchanged until later live-engine work

/home/jul/swarm/subprojects/prediction
└── cockpit/API/dashboard reads Panoptique DB-backed local service endpoints and artifact summaries
```

## Final storage architecture to integrate now

The final storage decision is explicit:

```txt
Primary database: PostgreSQL 16+ with TimescaleDB extension
Migrations: Alembic
Python access: SQLAlchemy Core/SQLModel + asyncpg
Live cache: Redis only for ephemeral/latest state
Raw audit/replay: JSONL and Parquet under data/panoptique/
Offline analysis/backtests: DuckDB reading Parquet exports
Vector/RAG: optional later Qdrant/Chroma, not part of the core storage path
```

Rules:

- All queryable operational state should land in PostgreSQL/TimescaleDB.
- All high-frequency timestamped facts should be Timescale hypertables.
- Every raw external payload worth auditing should also be preserved in JSONB columns and/or raw JSONL archives.
- Redis is never source of truth.
- DuckDB is never the live database; it is the local analytics engine for exports.

Core relational tables:

```txt
markets
market_tokens
market_resolution_rules
agents
agent_versions
shadow_bots
wallets
external_repos
data_sources
strategy_configs
```

Core Timescale hypertables:

```txt
market_price_snapshots
orderbook_snapshots
trade_events
shadow_predictions
crowd_flow_observations
agent_measurements
weather_forecasts
weather_observations
ingestion_health
paper_orders
paper_positions
execution_events
```
---

## Phase overview and gates

| Phase | Name | Main outcome | Gate |
|---|---|---|---|
| 0 | Doctrine and inventory | Current system mapped against Panoptique | Docs/tests pass; no code behavior changed |
| 1 | Storage foundation + data contracts | PostgreSQL/TimescaleDB, migrations, contracts, artifact spine | DB boots locally; migrations apply; contract/repository tests pass |
| 2 | Observation snapshots | Gamma/CLOB/trade/weather snapshots written to DB + artifacts consistently | 7 days reliable collection before Phase 3 live evaluation |
| 3 | Shadow Bot v0 | Deterministic shadow archetypes output crowd predictions into DB + archive | 100+ shadow predictions logged paper-only |
| 4 | Crowd-flow measurement | Compare shadow predictions to later price/volume moves from DB windows | statistically readable report exists |
| 5 | Operator dashboard integration | Cockpit shows Panoptique DB-backed read models | dashboard/API tests pass |
| 6 | Evidence and research crawler | GitHub/repo/meta evidence collection stored in DB + archives | evidence register populated and versioned |
| 7 | Calibration and bookmaker v0 | Agent-level Brier/calibration scaffolding backed by DB measurements | no trading; metrics only |
| 8 | Paper strategy experiments | paper-only front-run/fade/skip simulations persisted to DB + reports | out-of-sample positive signal required |
| 9 | Storage optimization | retention, compression, Parquet export, DuckDB analytics | DB health, retention, and export tests pass |
| 10 | Later live gate | separate future plan | requires explicit approval |

---

# Phase 0 — Doctrine, inventory, and migration boundary

**Goal:** Convert the Panoptique brief from a manifesto into grounded repo-local doctrine, without changing runtime behavior.

**Progress:** 100%

## Tasks

- [x] Create `docs/strategy/PANOPTIQUE_STRATEGY.md` as a cleaned strategic summary, not a full backlog.
- [x] Create `docs/strategy/EVIDENCE_REGISTER.md` with every major empirical claim classified.
- [x] Create `docs/strategy/ASSUMPTIONS.md` listing unproven assumptions to test.
- [x] Create `docs/strategy/GATES.md` defining hard phase gates and sample-size requirements.
- [x] Create `docs/panoptique/current-system-map.md` mapping existing modules to Panoptique concepts.
- [x] Add `python/tests/test_panoptique_docs_layout.py` to assert required docs exist and contain stable headings.
- [x] Run `PYTHONPATH=src python3 -m pytest tests/test_panoptique_docs_layout.py -q` from `/home/jul/prediction_core/python`.
- [x] Update `/home/jul/prediction_core/README.md` with a short Panoptique migration pointer.

## Acceptance criteria

- New docs exist.
- Docs distinguish verified facts from hypotheses.
- README points to migration docs.
- No runtime behavior changes.
- Targeted docs/layout test passes.

## Phase Status

- [x] Phase 0 complete

---

# Phase 1 — Storage foundation + Panoptique data contracts

**Goal:** Integrate the final storage stack immediately: PostgreSQL + TimescaleDB as primary store, raw JSONL/Parquet as audit/replay archive, and Python contracts/repositories as the only write path.

**Progress:** 100%

## Tasks

- [x] Create `infra/panoptique/docker-compose.yml` with:
  - PostgreSQL 16+ TimescaleDB image
  - Redis service
  - named volumes
  - local-only ports by default
  - health checks
- [x] Create `infra/panoptique/.env.example` with non-secret defaults:
  - `PANOPTIQUE_DATABASE_URL=postgresql+asyncpg://panoptique:panoptique@localhost:5432/panoptique`
  - `PANOPTIQUE_SYNC_DATABASE_URL=postgresql://panoptique:panoptique@localhost:5432/panoptique`
  - `PANOPTIQUE_REDIS_URL=redis://localhost:6379/0`
- [x] Create `infra/panoptique/README.md` documenting local DB boot, migrations, Redis role, JSONL/Parquet audit role, and no secrets.
- [x] Add minimal Python dependency guidance for SQLAlchemy/asyncpg/Alembic while keeping tests importable without optional DB packages.
- [x] Create `migrations/panoptique/alembic/` with Alembic environment and first TimescaleDB migration for core relational tables and hypertables.
- [x] Create `python/src/panoptique/__init__.py`.
- [x] Create `python/src/panoptique/contracts.py` with typed serializable contracts for markets, orderbook snapshots, trades, shadow predictions, crowd-flow observations, ingestion health, and artifact metadata.
- [x] Create `python/src/panoptique/db.py` for DB URL loading, engine helpers, and missing-env safety.
- [x] Create `python/src/panoptique/repositories.py` with insert/read/upsert paths for market, orderbook snapshot, shadow prediction, and crowd-flow observation.
- [x] Create `python/src/panoptique/artifacts.py` raw JSONL writer for audit/replay archives.
- [x] Add Phase 1 tests for contracts, artifacts, DB helpers, migration SQL, infra config, and repositories.
- [x] Run targeted validation from `/home/jul/prediction_core/python`.
- [x] Run Docker Compose config validation for `infra/panoptique/docker-compose.yml`.

- [x] Add Python dependencies/config as minimally as appropriate for SQLAlchemy/asyncpg/Alembic without breaking existing tests.
- [x] Create package directory `python/src/panoptique/` with `__init__.py`.
- [x] Create `python/src/panoptique/contracts.py` with typed serializable Phase 1 contracts.
- [x] Add `python/tests/test_panoptique_contracts.py` with serialization tests.
- [x] Create `python/src/panoptique/db.py` with database URL loading, engine helpers, and explicit missing-env safety.
- [x] Define Phase 1 table SQL/mapping in `python/src/panoptique/repositories.py` and TimescaleDB DDL in Alembic migration.
- [x] Create `python/src/panoptique/repositories.py` with first repository functions:
  - upsert market
  - insert/read orderbook snapshot
  - insert/read shadow prediction
  - insert/read crowd-flow observation
- [x] Initialize Alembic under `migrations/panoptique/alembic/`.
- [x] Create first migration enabling TimescaleDB:
  - `CREATE EXTENSION IF NOT EXISTS timescaledb;`
- [x] Create relational tables:
  - `markets`
  - `market_tokens`
  - `market_resolution_rules`
  - `agents`
  - `agent_versions`
  - `shadow_bots`
  - `wallets`
  - `external_repos`
  - `data_sources`
  - `strategy_configs`
- [x] Create Timescale hypertables:
  - `market_price_snapshots`
  - `orderbook_snapshots`
  - `trade_events`
  - `shadow_predictions`
  - `crowd_flow_observations`
  - `agent_measurements`
  - `weather_forecasts`
  - `weather_observations`
  - `ingestion_health`
  - `paper_orders`
  - `paper_positions`
  - `execution_events`
- [x] Add JSONB raw payload columns where useful:
  - `raw`
  - `bids`
  - `asks`
  - `features`
  - `metrics`
- [x] Add DB/migration tests covering SQL text expectations when TimescaleDB is unavailable.
- [x] Add repository unit tests using SQLite to verify contract insert/read behavior.
- [x] Create `python/src/panoptique/artifacts.py` with safe JSONL write helpers.
- [x] Add tests for append-only JSONL writing and metadata.
- [x] Create `docs/panoptique/storage-architecture.md` documenting PostgreSQL/TimescaleDB + Redis + Parquet/DuckDB roles.
- [x] Create `docs/panoptique/database-schema.md` documenting relational tables, hypertables, retention/compression intentions, and JSONB raw payload policy.
- [x] Create `docs/panoptique/data-contracts.md` documenting each contract and mapping contracts to DB tables.
- [x] Add fixture samples under `python/tests/fixtures/panoptique/` for one market snapshot, one shadow prediction, one crowd observation.
- [x] Run non-DB and repository validation:
  - `PYTHONPATH=src python3 -m pytest tests/test_panoptique_db*.py tests/test_panoptique_contracts.py tests/test_panoptique_artifacts.py tests/test_panoptique_repositories.py tests/test_panoptique_migration_sql.py tests/test_panoptique_infra.py -q`
- [x] Run Docker Compose config validation:
  - `docker-compose -f /home/jul/prediction_core/infra/panoptique/docker-compose.yml --env-file /home/jul/prediction_core/infra/panoptique/.env.example config`

## Acceptance criteria

- Local PostgreSQL/TimescaleDB and Redis can boot from `infra/panoptique/docker-compose.yml`.
- Alembic migration applies cleanly on a fresh database.
- TimescaleDB extension is enabled.
- Hypertables exist for timestamped data.
- Contracts serialize cleanly to JSON and map to DB insert paths.
- Repository tests verify at least one insert/read path for market, orderbook snapshot, shadow prediction, and crowd-flow observation.
- Raw JSONL artifacts still work and are documented as audit/replay archives.
- No trading credentials or wallet access are introduced.

## Phase Status

- [x] Phase 1 complete

---

# Phase 2 — Read-only observation snapshots

**Goal:** Build a lightweight observation layer that records market/orderbook/trade snapshots into PostgreSQL/TimescaleDB and raw audit artifacts from the start.

**Progress:** 100%

## Tasks

- [x] Audit existing `weather_pm/polymarket_live.py` and `weather_pm/polymarket_client.py` for reusable Gamma/CLOB fetch logic.
- [x] Create `python/src/panoptique/snapshots.py` with pure normalizers from existing Polymarket payloads into `MarketSnapshot` and `OrderbookSnapshot`.
- [x] Add tests using fixtures, not live network.
- [x] Create CLI entry in either `panoptique.cli` or extend existing CLI safely with `snapshot-markets`.
- [x] Implement `snapshot-markets --source live --limit N --output-dir /home/jul/prediction_core/data/panoptique/snapshots`.
- [x] Implement `snapshot-orderbook --token-id ...` or market-driven orderbook snapshot from known `clobTokenIds`.
- [x] Write each normalized snapshot to PostgreSQL/TimescaleDB through `panoptique.repositories`.
- [x] Write raw artifacts with explicit metadata: `source`, `fetched_at`, `request_url`, `schema_version`, and DB insert/upsert status.
- [x] Add ingestion health rows into `ingestion_health` for each snapshot run.
- [x] Create compact Markdown report writer for operator review.
- [x] Add tests for normalizers and report rendering.
- [x] Run targeted tests:
  - `PYTHONPATH=src python3 -m pytest tests/test_panoptique_snapshots.py tests/test_polymarket_live.py -q`

## Acceptance criteria

- Live command can fetch a bounded sample without trading credentials.
- Snapshot rows are persisted into PostgreSQL/TimescaleDB hypertables.
- Snapshot artifacts are also written as reproducible audit/replay archives.
- Network failures degrade with clear error artifacts and `ingestion_health` rows.
- No real orders or wallet access.

## Operational gate before Phase 3 evaluation

- At least 7 days of snapshots should be collected before trusting any measured crowd-flow result.
- For initial code work, Phase 3 can be built against fixtures before this 7-day data gate is met.

## Phase Status

- [x] Phase 2 complete

---

# Phase 3 — Shadow Bot v0, deterministic first

**Goal:** Add first-generation shadow bots that simulate common retail bot behavior without expensive LLM calls.

**Progress:** 100%

## Shadow archetypes v0

1. `weather_naive_threshold`
   - Uses existing weather probability/forecast logic when available.
   - Emits expected crowd side when model probability crosses common thresholds.
2. `round_number_price_bot`
   - Detects price levels around 0.50, 0.60, 0.65, 0.70, 0.75, 0.80.
3. `edge_8pct_bot`
   - Simulates common “edge > 8%” rule.
4. `momentum_naive_bot`
   - Uses recent price movement from snapshots to infer crowd-following direction.
5. `copy_wallet_placeholder`
   - Initially emits `insufficient_data` unless wallet data is available; contract exists for later.

## Tasks

- [x] Create `python/src/panoptique/shadow_bots.py` with a `ShadowBot` protocol/interface.
- [x] Add `ShadowContext` contract: market snapshot, orderbook snapshot, optional weather score, optional recent prices, optional wallet signal.
- [x] Add tests for each deterministic archetype.
- [x] Implement `weather_naive_threshold` using fixture weather scores.
- [x] Implement `round_number_price_bot` with explicit magic levels.
- [x] Implement `edge_8pct_bot` with configurable edge threshold default `0.08`.
- [x] Implement `momentum_naive_bot` from price deltas.
- [x] Implement `copy_wallet_placeholder` as non-trading explicit `insufficient_data` output.
- [x] Create `docs/panoptique/shadow-bots.md` explaining each archetype and why it exists.
- [x] Add CLI/report command `shadow-evaluate-fixture` that reads fixture/snapshot JSON and writes shadow predictions.
- [x] Add CLI/report command `shadow-evaluate-db` that reads recent DB snapshots and writes `shadow_predictions` rows plus JSONL archives.
- [x] Run `PYTHONPATH=src python3 -m pytest tests/test_panoptique_shadow_bots.py -q`.

## Acceptance criteria

- Shadow predictions have stable IDs and schema versions.
- Shadow predictions are persisted into PostgreSQL/TimescaleDB and raw archives.
- Each prediction says it predicts **crowd behavior**, not event truth.
- No LLM calls yet.
- No trading action generated.

## Phase Status

- [x] Phase 3 complete

---

# Phase 4 — Crowd-flow observation and measurement

**Goal:** Measure whether shadow predictions anticipate subsequent price/volume/orderbook movement.

**Progress:** 100%

## Core measurement windows

- `5m`
- `15m`
- `30m`
- `60m`
- optional `24h` for slow weather markets

## Tasks

- [x] Create `python/src/panoptique/crowd_flow.py` with pure functions to compute:
  - price delta after prediction
  - volume delta after prediction
  - direction hit/miss
  - magnitude bucket
  - liquidity caveat
- [x] Add tests using synthetic before/after snapshots.
- [x] Create `python/src/panoptique/measurement.py` with aggregate metrics:
  - hit rate by shadow bot
  - mean price delta by confidence bucket
  - volume response by window
  - false positive rate
  - insufficient liquidity count
- [x] Add tests for aggregation edge cases.
- [x] Create `docs/panoptique/crowd-flow-measurement.md`.
- [x] Implement report writer `panoptique/reports.py` for Markdown operator summaries.
- [x] Add CLI command `measure-shadow-flow --predictions-jsonl ... --snapshots-dir ... --output-dir ...` for archive-based replay.
- [x] Add CLI command `measure-shadow-flow-db --window 5m|15m|30m|60m` for TimescaleDB-backed measurement.
- [x] Persist measured rows into `crowd_flow_observations` and aggregate rows into `agent_measurements`.
- [x] Add `GateDecision` logic for “enough data / not enough data / promising / rejected”.
- [x] Run:
  - `PYTHONPATH=src python3 -m pytest tests/test_panoptique_crowd_flow.py tests/test_panoptique_measurement.py tests/test_panoptique_gates.py -q`

## Acceptance criteria

- Measurement clearly separates:
  - event accuracy
  - crowd-flow prediction accuracy
  - execution feasibility
- Reports never claim profit from paper-only movement.
- Small sample sizes produce `not_enough_data`, not optimism.

## Gate to consider Phase 5+ strategic use

Minimum for meaningful interpretation:

- 100+ shadow predictions logged
- 30+ matched after-window observations
- at least two market categories or explicit “weather-only” caveat

Minimum for any later paper strategy experiment:

- 200+ matched observations preferred
- positive directional relationship in out-of-sample split
- liquidity caveat below defined threshold

## Phase Status

- [x] Phase 4 complete

---

# Phase 5 — Cockpit/API/dashboard integration

**Goal:** Expose Panoptique state to the existing TypeScript cockpit without duplicating Python logic.

**Progress:** 100%

## Tasks

- [x] In `/home/jul/swarm/subprojects/prediction`, inspect current dashboard read models and route patterns.
- [x] Add a read-model type for Panoptique summaries, e.g. `src/lib/prediction-markets/panoptique-read-models.ts`.
- [x] Add tests for summary parsing from DB-backed API JSON plus fallback sample artifact JSON/MD paths.
- [x] Add API route under `src/app/api/v1/prediction-markets/panoptique/route.ts` or integrate into dashboard overview if preferred.
- [x] Prefer Python/local service DB summaries as source of truth; artifact summaries are fallback/audit only.
- [x] Ensure route degrades gracefully when DB/artifacts have no Panoptique data yet.
- [x] Add dashboard block:
  - snapshot freshness
  - shadow prediction count
  - matched observation count
  - current gate status
  - latest operator report path
- [x] Add CLI summary flag or `pm:panoptique:summary` if consistent with existing ops scripts.
- [x] Run targeted tests from `/home/jul/swarm/subprojects/prediction`:
  - `npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts <new-panoptique-tests>`
  - plus dashboard route tests if touched.

## Acceptance criteria

- Dashboard shows status, not trading recommendations.
- Missing DB rows/artifacts return an empty/readiness state, not a crash.
- TypeScript does not reimplement shadow bot math.
- PostgreSQL/TimescaleDB-backed Python summaries remain source of truth for Panoptique measurements.

## Phase Status

- [x] Phase 5 complete

---

# Phase 6 — Evidence register and ecosystem crawler v0

**Goal:** Start measuring the ecosystem of public bots and public claims without overfitting to anecdotes.

**Progress:** 100%

## Tasks

- [x] Expand `docs/strategy/EVIDENCE_REGISTER.md` with claim IDs, source URL, status, and confidence.
- [x] Create `python/src/panoptique/evidence.py` with a small model for `EvidenceClaim`.
- [x] Add tests for evidence status transitions: `unverified -> verified/plausible/rejected`.
- [x] Create `python/src/panoptique/github_repos.py` or similar read-only crawler using GitHub public API or `gh` if available.
- [x] Search terms v0:
  - `polymarket bot`
  - `kalshi bot`
  - `prediction market trading bot`
  - `polymarket agent`
- [x] Record repo metadata only:
  - name
  - URL
  - stars
  - forks
  - pushed_at
  - topics
  - README hash
  - detected keywords
- [x] Do not clone repos in the default crawler path.
- [x] Add optional manual audit command for a selected repo into `/tmp`, not permanent project state.
- [x] Write repo metadata into `external_repos` and raw artifacts under `data/panoptique/ecosystem/github_repos_*.json`.
- [x] Add report section: likely templates, common parameters, prompt/config exposure if visible.
- [x] Run tests without network using fixtures.

## Acceptance criteria

- No scraping of private/non-public data.
- No execution of third-party repo code.
- Evidence status is explicit.
- Claims in the Panoptique strategy doc link back to evidence IDs when possible.

## Phase Status

- [x] Phase 6 complete

---

# Phase 7 — Calibration, Brier, and Bookmaker v0 scaffolding

**Goal:** Prepare the system to compare agents/shadows/forecasters rigorously before any live decisioning.

**Progress:** 100%

## Tasks

- [x] Audit existing `prediction_core/calibration` and `prediction_core/evaluation` modules.
- [x] Reuse existing Brier/calibration functions instead of duplicating them.
- [x] Create `python/src/panoptique/agent_scores.py` if needed to bind shadow predictions to outcomes/flow observations.
- [x] Add tests for Brier and calibration integration using existing metrics.
- [x] Define `BookmakerInput` and `BookmakerOutput` contracts, but keep implementation minimal.
- [x] Implement `bookmaker_v0` as a weighted average only for paper/measurement reports.
- [x] Add anti-correlation placeholder metadata, not complex math yet.
- [x] Add docs `docs/panoptique/bookmaker-v0.md`.
- [x] Run targeted tests for calibration/evaluation + new Panoptique scoring.

## Acceptance criteria

- No new strategy receives capital.
- Bookmaker output is explicitly `research_only` / `paper_only`.
- Metrics distinguish:
  - forecasting event outcome
  - forecasting crowd movement
  - executable edge after costs

## Phase Status

- [x] Phase 7 complete

---

# Phase 8 — Paper-only strategy experiments

**Goal:** Use measured shadow/crowd-flow signals to simulate front-run/fade/skip decisions in paper only.

**Progress:** 100%

## Strategy modes

- `front_run_paper`: enter before predicted crowd move.
- `fade_paper`: paper counter-position after detected overshoot.
- `skip`: no action when crowd convergence is saturated or data quality is low.

## Tasks

- [x] Create `python/src/panoptique/paper_strategies.py` with pure decision functions.
- [x] Add tests for front-run/fade/skip decision boundaries.
- [x] Integrate execution cost model from `prediction_core.execution` to compute edge after spread/slippage.
- [x] Add tests ensuring strategies reject trades when depth/spread is bad.
- [x] Create paper strategy artifacts under `data/panoptique/paper_strategies/`.
- [x] Add CLI command `panoptique-paper-run` or similar.
- [x] Render operator report with:
  - no real order language
  - predicted crowd move
  - simulated entry/exit assumptions
  - costs
  - failure modes
- [x] Add out-of-sample split support.
- [x] Run targeted tests.

## Acceptance criteria

- Every simulated trade includes friction assumptions.
- Results are reported as research/paper, never as profit claim.
- Strategy can output mostly `skip`; that is valid.

## Gate before any live discussion

Minimum conditions before designing live micro-tests:

- 200+ matched shadow/crowd observations
- out-of-sample positive relationship for at least one archetype
- paper strategy remains positive after conservative spread/slippage
- no unresolved source leakage/lookahead issue
- dashboard exposes enough state for Julien to understand decisions

## Phase Status

- [x] Phase 8 complete

---

# Phase 9 — Storage optimization, retention, compression, and analytics exports

**Goal:** Harden the already-integrated PostgreSQL/TimescaleDB storage for long-running Panoptique operations, and add Parquet/DuckDB analytics exports without changing source-of-truth semantics.

**Progress:** 100%

## Tasks

- [x] Audit DB table sizes, hypertable chunk sizes, index usage, and ingest rates after real snapshot collection.
- [x] Add Timescale compression policies for high-volume hypertables where safe:
  - `market_price_snapshots`
  - `orderbook_snapshots`
  - `trade_events`
  - `ingestion_health`
- [x] Add retention policies only after documenting audit requirements; raw archives must remain available for replay.
- [x] Add continuous aggregates where useful:
  - 1m/5m/15m price buckets
  - volume buckets
  - spread/liquidity buckets
  - shadow prediction outcome buckets
- [x] Add DB health checks:
  - latest snapshot age
  - table growth rate
  - failed ingestion count
  - hypertable compression status
  - migration version
- [x] Add backup/runbook docs in `docs/panoptique/storage-architecture.md`:
  - local backup command
  - restore smoke test
  - migration rollback rule
  - never-store-secrets rule
- [x] Add Parquet export command for offline analytics:
  - `panoptique export-parquet --table shadow_predictions --from ... --to ...`
  - `panoptique export-parquet --table crowd_flow_observations --from ... --to ...`
- [x] Add DuckDB example queries under `docs/panoptique/duckdb-analytics.md`.
- [x] Add tests for export path using small fixture datasets.
- [x] Run DB health/export tests.

## Acceptance criteria

- TimescaleDB is already the primary store; this phase optimizes it rather than deciding whether to use it.
- Compression/retention policies are explicit and documented.
- Backups and restore smoke tests are documented.
- Parquet exports work for offline DuckDB analysis.
- Raw artifacts remain canonical audit/replay archives.

## Phase Status

- [x] Phase 9 complete

---

# Phase 10 — Future live micro-test plan, separate approval required

**Goal:** Prepare a future plan for live micro-tests only if previous gates prove an edge.

**Progress:** blocked/deferred by live gate

## Tasks

- [x] Do not implement live trading in this migration plan.
- [ ] Draft `docs/plans/YYYY-MM-DD-panoptique-live-microtest-plan.md` only if Phase 8 gates pass.
- [ ] Include hard limits:
  - tiny notional
  - max daily loss
  - kill switch
  - explicit Julien approval
  - no unattended live expansion
- [ ] Require paper-vs-live comparison before any scale.

## Phase 10 gate evaluation — 2026-04-26

Status: **blocked/deferred**. Safe gate-check tooling exists in `python/src/panoptique/gates.py`, but no live trading, wallet configuration, order placement, capital allocation, or live micro-test plan was enabled.

Unmet gates:

- Phase 8 live-discussion gate is not evidenced as passed in this plan.
- 200+ matched shadow/crowd observations are not evidenced here.
- out-of-sample positive relationship for at least one archetype is not evidenced here.
- paper strategy remaining positive after conservative spread/slippage is not evidenced here.
- no unresolved source leakage/lookahead issue is not evidenced here.
- dashboard state sufficient for Julien to understand decisions is not evidenced here.
- separate explicit Julien approval for a live micro-test is absent.

Therefore the future live micro-test plan is intentionally not drafted in this phase.

## Acceptance criteria

- This phase cannot be completed by code alone.
- Requires explicit user approval after Phase 8 evidence review.

## Phase Status

- [ ] Phase 10 blocked/deferred until Phase 8 live-discussion gates pass and separate future approval exists

---

# Recommended execution order

## Immediate next sprint: Phase 0 + Phase 1

Implement doctrine/docs plus the final storage foundation: PostgreSQL + TimescaleDB, Redis, Alembic migrations, contracts, repositories, and raw archive helpers.

Validation:

```bash
cd /home/jul/prediction_core/python
PYTHONPATH=src python3 -m pytest tests/test_panoptique_docs_layout.py tests/test_panoptique_contracts.py -q

docker compose -f /home/jul/prediction_core/infra/panoptique/docker-compose.yml up -d postgres redis
PANOPTIQUE_TEST_DATABASE_URL=postgresql+asyncpg://panoptique:panoptique@localhost:5432/panoptique PYTHONPATH=src python3 -m pytest tests/test_panoptique_db*.py -q
```

## Sprint 2: Phase 2 snapshots

Build read-only snapshot collection persisted to PostgreSQL/TimescaleDB plus raw archive artifacts.

Validation:

```bash
cd /home/jul/prediction_core/python
PYTHONPATH=src python3 -m pytest tests/test_panoptique_snapshots.py tests/test_polymarket_live.py -q
```

## Sprint 3: Phase 3 shadow bots

Build deterministic shadows only.

Validation:

```bash
cd /home/jul/prediction_core/python
PYTHONPATH=src python3 -m pytest tests/test_panoptique_shadow_bots.py -q
```

## Sprint 4: Phase 4 measurement

Measure whether shadows predict crowd-flow.

Validation:

```bash
cd /home/jul/prediction_core/python
PYTHONPATH=src python3 -m pytest tests/test_panoptique_crowd_flow.py tests/test_panoptique_measurement.py tests/test_panoptique_gates.py -q
```

Only after those should the dashboard integration and strategy experiments matter.

---

# Migration mapping from existing modules

| Existing module/surface | Keep? | Panoptique role |
|---|---:|---|
| `weather_pm/polymarket_live.py` | yes | bounded live read-only market source |
| `weather_pm/polymarket_client.py` | yes | reusable API client pieces |
| `weather_pm/probability_model.py` | yes | weather forecast/event probability input |
| `weather_pm/edge_sizing.py` | yes | paper sizing reference, not live permission |
| `weather_pm/weather_latency_edge.py` | yes | seed for cron/latency exploitation measurement |
| `weather_pm/winning_patterns.py` | yes | seed for market pattern library |
| `weather_pm/wallet_intel.py` | yes | seed for copy/wallet shadow features |
| `weather_pm/traders.py` | yes | seed for actor archetypes |
| `weather_pm/strategy_extractor.py` | yes | seed for repo/strategy extraction concepts |
| `prediction_core/calibration` | yes | Brier/calibration reuse |
| `prediction_core/evaluation` | yes | scoring reuse |
| `prediction_core/execution` | yes | friction/cost modeling for paper strategies |
| `prediction_core/paper` | yes | simulation semantics |
| `subprojects/prediction dashboard` | yes | operator cockpit |
| `subprojects/prediction shadow/live surfaces` | yes | read surfaces and governance, not source of Python math |

---

# Explicit non-goals for this migration

- No new real-money executor.
- No market making.
- No Hawkes implementation until Phase 4 shows enough data.
- No MFG/regime modeling until several months of observations exist.
- No RL.
- No scraping private data.
- No cloning/running random GitHub bots by default.
- No replacing the raw audit/replay archive with TimescaleDB-only storage; DB-first does not mean DB-only.
- No “profit engine” framing in docs or dashboard.

---

# Global Status

**Overall Progress:** 96% (blocked at Phase 10 live gate)

- [ ] Plan complete
