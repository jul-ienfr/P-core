# P-core Strategy Boundaries

## Decision

`prediction_core` is the generic engine. Domain strategies stay outside it.

The repo keeps three first-class layers:

```text
P-core
├── python/src/prediction_core/   # reusable prediction/trading primitives
├── python/src/weather_pm/        # weather/Polymarket domain strategy
└── python/src/panoptique/        # observation, shadow-bot and evidence system
```

This means `weather_pm` and `panoptique` are in the P-core repo, but they should not be folded wholesale into the `prediction_core` Python package.

## Why

`prediction_core` should stay stable and reusable across markets. It should not depend on weather parsing, station/source routing, profitable-account heuristics, Panoptique storage, shadow bots, or crowd-flow semantics.

Domain modules can evolve quickly. The core should only absorb invariants that have become reusable.

## Current strategy blocks

### 1. Weather profitable accounts / winning patterns

Current home: `python/src/weather_pm/`

Representative modules:

- `strategy_extractor.py`
- `strategy_shortlist.py`
- `winning_patterns.py`
- `consensus_tracker.py`
- `archetype_backtest.py`

Purpose:

- infer weather-specific archetypes from profitable accounts;
- detect consensus and repeated city/date/weather patterns;
- produce operator shortlists and action candidates.

Keep in `weather_pm` unless the extracted concept is clearly market-agnostic.

### 2. Weather paper ledger / all-in execution

Current home: `python/src/weather_pm/`

Representative modules:

- `paper_ledger.py`
- `orderbook_simulator.py`
- `production_operator.py`

Purpose:

- simulate strict-limit paper orders;
- account for entry fees, exit fees, slippage and net PnL;
- generate operator actions for the weather production path.

Migration target:

- generic fill simulation, execution costs, paper ledger state transitions and PnL accounting should move into `prediction_core` once stabilized;
- weather-specific candidate loading, source confirmation and operator language should remain in `weather_pm`.

### 3. Panoptique

Current home: `python/src/panoptique/`

Representative modules:

- `shadow_bots.py`
- `crowd_flow.py`
- `bookmaker.py`
- `paper_strategies.py`
- `evidence.py`
- `gates.py`
- `agent_scores.py`

Purpose:

- observe agents/markets/repos;
- model crowd-flow and shadow predictions;
- maintain evidence, gates and experimental bookmaker logic.

Keep Panoptique as a separate system/application layer. Only promote generic scoring, evidence contracts or replay primitives if they prove reusable outside Panoptique.

## What belongs in `prediction_core`

Promote only generic primitives:

- market-neutral strategy contracts: `StrategySignal`, `StrategyDecision`, `StrategyRun`, `StrategyOutcome`;
- order book and AMM execution models;
- fee/slippage/all-in cost models;
- paper ledger lifecycle and PnL accounting;
- risk, sizing and exposure primitives;
- replay/backtest interfaces;
- calibration and evaluation metrics;
- shared artifact contracts.

## What should stay outside `prediction_core`

Keep domain/application logic out:

- weather market parsing;
- station/source routing;
- weather resolution metadata;
- profitable weather account heuristics;
- operator reports specific to weather;
- Panoptique shadow-bot semantics;
- Panoptique crowd-flow and repository observation;
- experimental bookmaker policy until its invariant pieces are proven.

## Interface doctrine

Domain strategies should call the core through narrow contracts:

```python
signals = strategy.produce_signals(context)
decisions = core.evaluate(signals, market_state, risk_state)
sized = core.size(decisions, bankroll_state)
execution = core.simulate_execution(sized, orderbook_state, fee_model)
ledger = core.record_paper_result(execution)
strategy.consume_outcome(ledger)
```

No domain package should reach into private core internals. The core should not import `weather_pm` or `panoptique`.

## Migration order

1. Keep current modules where they are.
2. Add shared contracts in `prediction_core` only when two domains need the same shape.
3. Extract the weather paper ledger's generic cost/PnL math into `prediction_core` first.
4. Adapt `weather_pm.paper_ledger` to call the core primitive while preserving its current CLI/API behavior.
5. Later, extract generic strategy/replay contracts used by both `weather_pm` and `panoptique`.
6. Do not merge Panoptique wholesale into `prediction_core`.

## Rule of thumb

If a module mentions a market domain, source provider, operator workflow, station, account archetype, shadow bot, or Panoptique repository concept, it is not core.

If it can be tested without Polymarket, weather, Panoptique, external APIs, or generated artifacts, it may belong in `prediction_core`.
