# Panoptique Strategy

Repo-local doctrine for migrating `prediction_core` toward Panoptique without changing runtime behavior or enabling live trading.

## Thèse centrale

Panoptique treats prediction-market alpha as a measurement problem before it is an execution problem. The system should first observe markets, wallets, bots, event surfaces, and paper decisions; then classify evidence; then only consider execution changes after hard statistical gates are passed.

The immediate opportunity is not assumed to be a proven edge. It is a hypothesis: heterogeneous market participants, latency windows, and domain-specific information may leave measurable, repeatable signals in Polymarket-style markets. Phase 0 records that doctrine while separating verified repo facts from unproven strategic claims.

## Non-objectifs

- No rewrite of the existing weather, paper, calibration, analytics, evaluation, or local-service stack.
- No real-money trading, wallet use, credential handling, or live order placement from this migration plan.
- No large backlog pasted into strategy docs; implementation details remain in the migration plan.
- No claim that bot-following, wallet-following, or weather-market edges are facts until measured.
- No dashboard or TypeScript cockpit reimplementation of Python domain logic in Phase 0.

## Architecture progressive

Panoptique is added around the current system in layers:

1. Doctrine and inventory: stable docs, current-system map, evidence register, and hard gates.
2. Observation: read-only snapshots and durable raw artifacts before new decision logic.
3. Shadow bots: deterministic paper-only archetypes that emit predictions for evaluation.
4. Measurement: compare shadow predictions, crowd flow, prices, volume, and outcomes across resolved samples.
5. Governance: phase gates decide whether later experiments can proceed.

The existing `prediction_core.*` and `weather_pm.*` modules remain the baseline. Panoptique docs and later code should map to existing capabilities before adding new ones.

## Mesure avant capital

Every strategic claim must be either verified locally, plausible but externally supported, a hypothesis requiring measurement, or rejected/unverified. Capital deployment is outside this phase and outside this plan unless a separate future approval explicitly changes that boundary.

Required measurement posture:

- Prefer paper-only samples and resolved-market evidence.
- Preserve raw observations for replay and audit.
- Report uncertainty, sample size, and failure cases.
- Treat negative results as useful evidence that can stop later phases.

## Paper-only boundary

Phase 0 and the migration plan are paper-only/read-only. Any simulated order or shadow decision must state that no real order was placed. Phase 10/live work cannot begin from this document alone and requires separate explicit approval.
