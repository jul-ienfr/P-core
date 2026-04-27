# Multi-Strategy Prediction Core Implementation Plan

> **For Hermes:** Use `phase-plan-executor` to execute this plan phase-by-phase. Use TDD. Do not enable real-money trading.

**Goal:** Turn Prediction Core into a standardized multi-strategy research/paper engine where weather, Panoptique, and future strategies emit comparable signals into shared measurement, bookmaker, and paper-execution layers.

**Architecture:** Add a small `prediction_core.strategies` layer with shared contracts, registry, adapters, measurement helpers, and paper-decision bridge. Existing weather and Panoptique code remains source-of-truth; adapters normalize outputs rather than duplicating strategy math.

**Tech Stack:** Python 3.x under `/home/jul/prediction_core/python`, existing `prediction_core.*`, existing `weather_pm.*`, existing `panoptique.*`, pytest. TypeScript dashboard integration is intentionally deferred unless Phase 5 is explicitly added later.

**Concurrency:** 1
**Parallel Mode:** serial
**Validation Mode:** standard
**Max Retries Per Task:** 1
**Resume:** true
**Commit Mode:** none

---

## Contexte vérifié

Verified live on 2026-04-26:

- Panoptique scaffold exists under `/home/jul/prediction_core/python/src/panoptique/` with contracts, snapshots, shadow bots, crowd-flow, measurement, bookmaker, paper strategies, evidence, summary, exports, and gates.
- Current Panoptique targeted test state: `PYTHONPATH=src python3 -m pytest tests/test_panoptique_*.py -q` → `83 passed`.
- Current Panoptique summary: `current_gate_status=not_enough_data`, `shadow_prediction_count=0`, `matched_observation_count=0`, `readiness_state=empty`, `recommendation=null`.
- Existing weather workflow lives in `prediction_core/orchestrator.py` and weather-specific modules under `weather_pm/`.
- Existing entry/risk gate logic exists in `prediction_core/decision/entry_policy.py`.
- Existing paper execution simulation exists in `prediction_core/paper/simulation.py`.
- Existing Panoptique paper strategy logic exists in `panoptique/paper_strategies.py` and is explicitly paper-only.
- There is no generic `prediction_core.strategies` package yet.

---

## Non-goals / guardrails

- No live trading.
- No wallet access.
- No Polymarket credential handling.
- No LLM polling loop.
- No rewrite of weather or Panoptique internals.
- No dashboard changes in this plan unless a later explicit phase is added.
- Strategies emit signals; only shared policy/execution layers can turn signals into paper decisions.
- Every strategy must declare a mode: `research_only`, `paper_only`, or `live_allowed`; this plan only allows `research_only` and `paper_only`.

---

## Phase 0 — Strategy contracts and package skeleton

**Goal:** Create the shared strategy interface and tests without touching existing runtime behavior.

**Progress:** 100%

### Tasks

- [x] Create `python/src/prediction_core/strategies/__init__.py` exporting the public strategy contracts.
- [x] Create `python/src/prediction_core/strategies/contracts.py` with dataclasses/enums for `StrategyMode`, `StrategyTarget`, `StrategySide`, `StrategySignal`, `StrategyRunRequest`, `StrategyRunResult`, and `StrategyDescriptor`.
- [x] Add `python/tests/test_strategy_contracts.py` covering JSON serialization, probability bounds, confidence bounds, expected_move bounds, mode safety, and `trading_action="none"` invariants.
- [x] Run `PYTHONPATH=src python3 -m pytest tests/test_strategy_contracts.py -q` from `/home/jul/prediction_core/python`.

### Acceptance criteria

- Contracts serialize to dict/JSON-friendly payloads.
- Invalid probabilities/confidences raise clear errors.
- `live_allowed` is representable but not default.
- A signal always carries `strategy_id`, `market_id`, `target`, `mode`, timestamp, features, risks, and source metadata.

### Phase Status

- [x] Phase 0 complete

---

## Phase 1 — Strategy registry and config gating

**Goal:** Add a registry that can enable/disable strategies and run only approved research/paper strategies.

**Progress:** 100%

### Tasks

- [x] Create `python/src/prediction_core/strategies/registry.py` with `StrategyProtocol`, `RegisteredStrategy`, `StrategyRegistry`, and duplicate-ID protection.
- [x] Create `python/src/prediction_core/strategies/config.py` with minimal config dataclasses: `StrategyConfig`, `StrategyRegistryConfig`, default disabled behavior, and safety validation rejecting live mode unless explicitly allowed by caller.
- [x] Add `python/tests/test_strategy_registry.py` covering registration, duplicate rejection, enabled filtering, disabled strategy skip, and live-mode rejection by default.
- [x] Run `PYTHONPATH=src python3 -m pytest tests/test_strategy_contracts.py tests/test_strategy_registry.py -q`.

### Acceptance criteria

- Registry can run one strategy or all enabled strategies.
- Disabled strategies produce no signals.
- Live-mode strategies are blocked by default.
- Failures in one strategy are captured in `StrategyRunResult.errors`, not allowed to crash the full run.

### Phase Status

- [x] Phase 1 complete

---

## Phase 2 — Weather baseline adapter

**Goal:** Wrap the current weather/event-forecasting path as a standard strategy signal without duplicating weather math.

**Progress:** 100%

### Tasks

- [x] Create `python/src/prediction_core/strategies/weather_baseline.py` with a pure adapter from existing weather score/decision dictionaries into `StrategySignal`.
- [x] Add `WeatherBaselineStrategy` implementing the registry protocol using supplied payloads/fixtures first, not live network by default.
- [x] Add `python/tests/test_strategy_weather_baseline.py` using fixture dictionaries for a weather market score and a skip case.
- [x] Run `PYTHONPATH=src python3 -m pytest tests/test_strategy_contracts.py tests/test_strategy_registry.py tests/test_strategy_weather_baseline.py -q`.

### Acceptance criteria

- Weather signal target is `event_outcome_forecasting`.
- Mode defaults to `paper_only` or stricter.
- Adapter preserves market ID, probability, confidence, edge metadata, execution caveats, and source references.
- No live network call is required for tests.

### Phase Status

- [x] Phase 2 complete

---

## Phase 3 — Panoptique shadow-flow adapter

**Goal:** Wrap Panoptique crowd-flow/shadow outputs as standard strategy signals.

**Progress:** 100%

### Tasks

- [x] Create `python/src/prediction_core/strategies/panoptique_shadow_flow.py` with adapters from `panoptique` shadow/crowd-flow records into `StrategySignal`.
- [x] Add `PanoptiqueShadowFlowStrategy` implementing the registry protocol from supplied records/fixtures first, not DB-required by default.
- [x] Add `python/tests/test_strategy_panoptique_shadow_flow.py` covering `not_enough_data`, `up/down/unknown` crowd directions, confidence propagation, and paper/research-only invariants.
- [x] Run `PYTHONPATH=src python3 -m pytest tests/test_strategy_contracts.py tests/test_strategy_registry.py tests/test_strategy_panoptique_shadow_flow.py -q`.

### Acceptance criteria

- Panoptique signal target is `crowd_movement_forecasting`.
- `not_enough_data` becomes a valid no-action/skip-compatible signal, not optimism.
- Signal features include archetype, window, expected move, observed/matched count when available.
- No DB connection is required for unit tests.

### Phase Status

- [x] Phase 3 complete

---

## Phase 4 — Shared measurement projection

**Goal:** Provide common reporting/measurement projection across strategies while keeping metric targets separate.

**Progress:** 100%

### Tasks

- [x] Create `python/src/prediction_core/strategies/measurement.py` with `StrategyMetricSnapshot` and helpers to group signals by `strategy_id`, `target`, `mode`, and gate status.
- [x] Reuse existing `prediction_core.evaluation` helpers where applicable; do not duplicate Brier implementation.
- [x] Add `python/tests/test_strategy_measurement.py` covering separation of event forecasting vs crowd-flow forecasting vs execution-edge metadata.
- [x] Run `PYTHONPATH=src python3 -m pytest tests/test_strategy_contracts.py tests/test_strategy_measurement.py -q`.

### Acceptance criteria

- Metrics never combine event and crowd-flow targets into one score.
- Small/no sample state returns `not_enough_data`.
- Output is dashboard/read-model friendly.

### Phase Status

- [x] Phase 4 complete

---

## Phase 5 — Bookmaker bridge for standard strategy signals

**Goal:** Let the existing Panoptique bookmaker consume standardized strategy signals where appropriate.

**Progress:** 100%

### Tasks

- [x] Create `python/src/prediction_core/strategies/bookmaker_bridge.py` converting compatible `StrategySignal` objects into `panoptique.bookmaker.BookmakerInput`.
- [x] Add safety rules: only probability-bearing signals can be converted; unknown/skip signals are excluded with reason metadata.
- [x] Add `python/tests/test_strategy_bookmaker_bridge.py` covering weighted average, incompatible target exclusion, and research/paper-only output invariants.
- [x] Run `PYTHONPATH=src python3 -m pytest tests/test_strategy_bookmaker_bridge.py tests/test_panoptique_bookmaker.py -q`.

### Acceptance criteria

- Bookmaker output remains `research_only=True`, `paper_only=True`, `trading_action="none"`.
- Incompatible signals do not silently affect probability.
- Conversion preserves strategy IDs and metric target metadata.

### Phase Status

- [x] Phase 5 complete

---

## Phase 6 — Paper decision bridge

**Goal:** Convert strategy signals into shared paper-only entry decisions through existing policy/cost layers.

**Progress:** 100%

### Tasks

- [x] Create `python/src/prediction_core/strategies/paper_bridge.py` that maps `StrategySignal` plus market/execution context into `prediction_core.decision.EntryDecision` or an explicit skip.
- [x] Require `paper_only` or stricter mode; reject `live_allowed` in this bridge for now.
- [x] Use existing `evaluate_entry` from `prediction_core.decision.entry_policy` instead of creating new sizing/risk math.
- [x] Add `python/tests/test_strategy_paper_bridge.py` covering valid paper decision, skip on low confidence, skip on wide spread, skip on non-probability crowd-flow signal, and live-mode rejection.
- [x] Run `PYTHONPATH=src python3 -m pytest tests/test_strategy_paper_bridge.py tests/test_entry_policy.py -q` if `tests/test_entry_policy.py` exists; otherwise run the new test plus relevant decision tests discovered in repo.

### Acceptance criteria

- Strategies do not execute orders.
- Bridge returns paper decisions only.
- Existing entry policy remains the risk gate.
- Skip includes clear `blocked_by` reasons.

### Phase Status

- [x] Phase 6 complete

---

## Phase 7 — CLI/report smoke surface

**Goal:** Add a minimal operator-facing smoke command/report that shows enabled strategies and generated fixture-based signals.

**Progress:** 100%

### Tasks

- [x] Add or extend a safe CLI entry under `prediction_core.strategies.cli` or existing CLI conventions with `strategy-smoke --fixture`.
- [x] The smoke command should run registry with weather and Panoptique fixture adapters only, then print JSON summary.
- [x] Add `python/tests/test_strategy_cli.py` using subprocess/module invocation or direct main-call helper.
- [x] Run `PYTHONPATH=src python3 -m pytest tests/test_strategy_*.py -q`.

### Acceptance criteria

- Smoke command requires no credentials, no DB, no live network.
- Output lists strategy IDs, modes, targets, signal counts, and errors.
- Output contains no trading recommendation.

### Phase Status

- [x] Phase 7 complete

---

## Final validation

**Progress:** 100%

### Tasks

- [x] Run `PYTHONPATH=src python3 -m pytest tests/test_strategy_*.py -q` from `/home/jul/prediction_core/python`.
- [x] Run `PYTHONPATH=src python3 -m pytest tests/test_panoptique_*.py -q` to ensure Panoptique remains intact.
- [x] Update this plan's Global Status based on checked tasks.

### Acceptance criteria

- All strategy tests pass.
- Existing Panoptique targeted tests still pass.
- Plan accurately reflects completion status.
- No live trading or wallet functionality added.

### Phase Status

- [x] Final validation complete

---

## Global Status

**Overall Progress:** 100%

- [x] Plan complete
