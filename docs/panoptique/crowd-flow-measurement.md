# Crowd-flow measurement

Phase 4 measures whether deterministic shadow predictions anticipate later market microstructure movement. It remains paper-only/read-only: no wallet credentials, no real orders, and no trading actions are generated.

## Measurement target

Crowd-flow measurement is intentionally narrower than event forecasting:

- **Event accuracy:** not measured here. Whether the market ultimately resolves Yes/No is a later calibration/evaluation concern.
- **Crowd-flow prediction accuracy:** measured here by comparing a shadow prediction direction to later price, volume, and orderbook/snapshot movement.
- **Execution feasibility:** not simulated as executable PnL. Phase 4 records only liquidity caveats such as insufficient or unknown liquidity.

Reports must never infer monetary returns from paper-only price movement.

## Core windows

Supported after-prediction windows:

- `5m`
- `15m`
- `30m`
- `60m`
- optional archive-only `24h` for slow weather markets

## Observation row

For each matched prediction and after-window snapshot, `panoptique.crowd_flow` computes:

- price delta after prediction
- volume delta after prediction
- direction hit/miss
- magnitude bucket: `flat`, `small`, `medium`, `large`
- liquidity caveat: `insufficient_liquidity`, `unknown_liquidity`, or none

Rows are written as `CrowdFlowObservation` contracts into `crowd_flow_observations` when a repository/DB is available and always to JSONL artifacts for replay/audit.

## Aggregate metrics

`panoptique.measurement` aggregates observations into:

- hit rate by shadow bot
- mean price delta by confidence bucket
- mean volume response by window
- false positive rate
- insufficient liquidity count

Aggregate rows are persisted to `agent_measurements` where the repository is available. If DB/repository access is unavailable, commands emit explicit `skipped_unavailable` artifacts and reports instead of failing silently.

## GateDecision

Small samples must not produce optimistic interpretation. The gate status is one of:

- `not_enough_data`: fewer than 100 shadow predictions, fewer than 30 matched after-window observations, or missing category evidence.
- `enough_data`: minimum interpretation sample exists, possibly with a weather-only caveat.
- `promising`: later paper-strategy preconditions are met: 200+ matched observations preferred, positive out-of-sample directional relationship, and liquidity caveat rate below threshold.
- `rejected`: enough data exists but directional relationship is negative or weak enough to reject.

Minimum meaningful interpretation requires 100+ shadow predictions, 30+ matched observations, and at least two categories or an explicit weather-only caveat.

## CLI

Archive replay:

```bash
PYTHONPATH=src python3 -m panoptique.cli measure-shadow-flow \
  --predictions-jsonl /path/to/predictions.jsonl \
  --snapshots-dir /path/to/snapshots \
  --output-dir /home/jul/prediction_core/data/panoptique/measurements \
  --window 15m
```

DB/repository-backed replay:

```bash
PYTHONPATH=src python3 -m panoptique.cli measure-shadow-flow-db \
  --window 5m \
  --output-dir /home/jul/prediction_core/data/panoptique/measurements
```

Without a configured repository/DB, the DB command writes an explicit skipped report/artifact with `skipped_unavailable` and a `not_enough_data` gate decision.
