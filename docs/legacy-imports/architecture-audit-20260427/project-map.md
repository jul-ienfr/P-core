# P-core project map

## Canonical root

`/home/jul/P-core` is the canonical standalone repository for PredictionCore / Polymarket work.

Remote: `git@github.com:jul-ienfr/P-core.git`

Do not create a new top-level Polymarket folder to clean up the project. Consolidate here.

## Canonical internal boundaries

```text
P-core/
  contracts/              Shared interchange contracts between engines/cockpit
  python/
    src/
      prediction_core/    Generic reusable prediction-market engine primitives
      weather_pm/         Weather/Polymarket domain strategy layer
      panoptique/         Observation, evidence, shadow-bot and application layer
    tests/                Python tests grouped by the same domains
  rust/                   Target canonical live engine
  docs/
    architecture/         Project map, boundaries, migration status
    polymarket/           Polymarket/weather runbooks, profiles, reverse engineering
    panoptique/           Panoptique-specific docs
    plans/                Implementation plans
  data/
    polymarket/           Generated Polymarket artifacts, organized by type
    panoptique/           Generated Panoptique artifacts
  infra/panoptique/       Panoptique local infrastructure
  migrations/panoptique/  Panoptique DB migrations
  scripts/                Repo scripts
```

## Layer doctrine

### `prediction_core`

Generic engine code that should survive outside météo:

- strategy signal / decision / outcome contracts
- execution costs, fees, slippage, order-book simulation
- paper primitives, sizing, replay, calibration, evaluation
- runtime surfaces that are not weather-specific

### `weather_pm`

Weather and Polymarket-weather specific logic:

- weather market parsing
- station/source routing and resolution checks
- profitable weather-account analysis
- weather shortlist/operator reports
- weather strategy profiles
- weather-specific paper adapters

### `panoptique`

Observation and evidence system layer:

- crowd-flow / evidence / gates
- shadow bots and bookmaker experiments
- storage/export/reporting surfaces
- Panoptique infra and migrations

Panoptique is useful project work and must not be deleted or treated as disposable legacy without an explicit decision.

## Generated Polymarket artifacts

`data/polymarket` should not be a flat junk drawer. Use:

```text
data/polymarket/
  latest/            Stable latest pointers / latest reports
  account-analysis/  Profitable accounts, leaderboards, top-10 patterns
  ledgers/           Paper ledgers and historical paper baskets
  reports/
    operator/        Operator-facing reports
    production/      Production readiness / production reports
  scans/             Orderbook/source/candidate/runtime scans
  archive/           Dated or uncategorized historical artifacts
```

If scripts still write to the old flat `data/polymarket/*.json` shape, either update the writer or move artifacts after generation. Do not mix new generated outputs at root unless it is a temporary compatibility path.

## Polymarket docs

Polymarket/weather docs live under:

```text
docs/polymarket/
  weather-production-baseline.md
  weather-production-runbook.md
  weather-strategy-profiles.md
  generated/
  reverse-engineering/
```

Root `docs/` should keep only cross-domain docs, plans, and non-Polymarket material.

## Duplicate / legacy roots

Known non-canonical roots:

| Path | Status | Rule |
| --- | --- | --- |
| `/home/jul/prediction_core` | duplicate / previous standalone tree | audit only; do not develop here unless promoted explicitly |
| `/home/jul/swarm/subprojects/prediction` | legacy TypeScript/dashboard donor | use as donor/reference/UI legacy, not canonical engine |
| `/home/jul/swarm/prediction_core` | residual tree | audit before use; candidate for archive after verification |
| `/home/jul/P-core/.claude/worktrees/*` | temporary development worktrees | not product structure; clean once merged/obsolete |
| `/tmp/P-core-*`, `/tmp/pcore-*` | temporary worktrees | remove when no longer needed |

## Cleanup rules

1. Keep `/home/jul/P-core` as the one official project folder.
2. Do not move all weather/Panoptique code into `prediction_core`; preserve layer boundaries.
3. Before deleting any duplicate root, verify Git state and whether it contains unmerged files.
4. Prefer archive/quarantine over deletion for old generated artifacts.
5. Keep `.claude/worktrees` out of mental/project structure; remove stale worktrees with `git worktree remove` only when their branch has been merged or explicitly abandoned.
