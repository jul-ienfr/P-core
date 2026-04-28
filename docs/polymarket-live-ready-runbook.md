# Polymarket Live-Ready Operator Runbook

This runbook documents the controlled path for running the Polymarket weather runtime in `paper` and `dry_run` modes, plus the read-only `polymarket-live-preflight` check. The safe default is always `paper`; `live` is not exposed by `polymarket-runtime-cycle` and is rejected by argparse.

Hard guardrails:

- Do not commit private keys, secrets, wallet material, generated audit logs, or idempotency stores.
- Do not use market orders. The live-ready path is limit-order only.
- Do not bypass risk limits, idempotency, or audit logging.
- Do not run unbounded live market-data or execution rehearsals.
- Treat `live` as unavailable in `polymarket-runtime-cycle`: it is not a valid argparse choice, and credentials/operator approval do not expose it.

## Mode definitions

### `paper`

`paper` is the default mode. It evaluates market data and model probabilities, then emits paper intents only. It does not require execution credentials, an idempotency store, or an audit log. No order executor is used.

Expected behavior:

- `execution_enabled` is `false`.
- Signals are recorded as `paper_intents`.
- `orders_submitted` is empty.
- No authenticated CLOB REST path is used.

### `dry_run`

`dry_run` uses the same runtime execution route as the future live path, but with `DryRunPolymarketExecutor`. It exercises order construction, risk gates, idempotency, and audit logging without submitting real orders.

Expected behavior:

- `execution_enabled` is `true`.
- Risk limits and risk state are required.
- `--idempotency-jsonl` and `--audit-jsonl` are required.
- Accepted orders receive `dry-run:<idempotency_key>` exchange order ids.
- No real network order-placement call is made.

### `live`

`live` is the authenticated CLOB REST executor seam, but real Polymarket CLOB REST submission is not wired in the current CLI. It is not exposed by `polymarket-runtime-cycle`; use `polymarket-live-preflight` for read-only readiness checks and `dry_run` for simulated execution.

Expected behavior:

- `polymarket-runtime-cycle --help` lists `--execution-mode {paper,dry_run}` only.
- `polymarket-runtime-cycle --execution-mode live` is rejected by argparse as an invalid choice before runtime execution.
- The runtime-cycle command does not construct a live executor or attempt live submission.
- `polymarket-live-preflight` is read-only: it checks environment readiness without constructing an executor, submitting orders, or canceling orders.
- Preflight returns `ready=false`, `live_submission_wired=false`, and `live_submission_unavailable` until real submission is implemented.
- Required environment variable names may be checked by preflight, but their presence does not enable live submission.

## Required environment variables for `live`

These names are checked by the read-only preflight when credential presence needs to be verified. They do not enable `--execution-mode live` while submission remains unavailable. This document intentionally does not include values.

- `POLYMARKET_PRIVATE_KEY`
- `POLYMARKET_FUNDER_ADDRESS`
- `POLYMARKET_CHAIN_ID`

Do not print these values in shells, logs, tickets, screenshots, test fixtures, or committed files.

## CLI examples

Run all examples from the repository root unless noted otherwise:

```bash
cd /home/jul/P-core
```

### Inspect the read-only runtime scaffold

```bash
python/scripts/prediction-core polymarket-runtime-plan
```

### Paper runtime cycle, safe default

```bash
python/scripts/prediction-core polymarket-runtime-cycle \
  --markets-json data/polymarket/operator/markets.json \
  --probabilities-json data/polymarket/operator/probabilities.json \
  --dry-run-events-jsonl data/polymarket/operator/clob-events.jsonl \
  --max-events 100 \
  --min-liquidity 0 \
  --min-edge 0.02 \
  --paper-notional-usdc 5 \
  --execution-mode paper
```

### Dry-run execution rehearsal with audit and idempotency

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p data/polymarket/operator/runs/${RUN_ID}

python/scripts/prediction-core polymarket-runtime-cycle \
  --markets-json data/polymarket/operator/markets.json \
  --probabilities-json data/polymarket/operator/probabilities.json \
  --dry-run-events-jsonl data/polymarket/operator/clob-events.jsonl \
  --max-events 100 \
  --min-liquidity 0 \
  --min-edge 0.02 \
  --paper-notional-usdc 5 \
  --execution-mode dry_run \
  --idempotency-jsonl data/polymarket/operator/runs/${RUN_ID}/idempotency.jsonl \
  --audit-jsonl data/polymarket/operator/runs/${RUN_ID}/execution-audit.jsonl \
  --max-order-notional-usdc 10 \
  --max-total-exposure-usdc 100 \
  --max-daily-loss-usdc 25 \
  --max-spread 0.05 \
  --total-exposure-usdc 0 \
  --daily-realized-pnl-usdc 0
```

### Read-only live preflight

Use this only after credentials are injected by the approved secret manager or local operator environment. Do not paste secret values into the command. This command is read-only: it does not construct a live executor, submit orders, or cancel orders. In the current state it remains not ready because live submission is unavailable.

```bash
python/scripts/prediction-core polymarket-live-preflight
```

Do not use `polymarket-runtime-cycle --execution-mode live` for preflight; `live` is not an exposed runtime-cycle mode and argparse rejects it before runtime execution.

### Bounded CLOB market-data stream only

Dry-run replay without network:

```bash
python/scripts/prediction-core marketdata-stream \
  --token-id example-yes-token \
  --dry-run-events-jsonl data/polymarket/operator/clob-events.jsonl \
  --max-events 100
```

Bounded live websocket read-only stream:

```bash
python/scripts/prediction-core marketdata-stream \
  --token-id example-yes-token \
  --live \
  --max-events 100
```

## Risk limits

Every `dry_run` execution rehearsal requires explicit risk limits. `live` is not an exposed runtime-cycle mode, so argparse rejects it before these runtime limits are evaluated:

- `--max-order-notional-usdc`: maximum notional for one order. The run blocks an order when `order.notional_usdc` is greater than this cap.
- `--max-total-exposure-usdc`: maximum total exposure after the proposed order. The run blocks an order when `current total exposure + order notional` exceeds this cap.
- `--max-daily-loss-usdc`: maximum allowed daily loss. The run blocks an order when current daily realized PnL is at or below `-abs(max_daily_loss_usdc)`.
- `--max-spread`: maximum allowed bid/ask spread for the market snapshot. Missing spread also blocks the order.
- `--total-exposure-usdc`: current exposure supplied by the operator or reconciliation system for this run.
- `--daily-realized-pnl-usdc`: current realized PnL supplied by the operator or reconciliation system for this run.

Initial conservative caps for dry-run rehearsals:

```text
--paper-notional-usdc 5
--max-order-notional-usdc 10
--max-total-exposure-usdc 100
--max-daily-loss-usdc 25
--max-spread 0.05
--total-exposure-usdc 0
--daily-realized-pnl-usdc 0
```

If any risk input is unknown, stop and run `paper` only.

## Idempotency and audit paths

Use a unique run directory per operator run:

```text
data/polymarket/operator/runs/<UTC_RUN_ID>/idempotency.jsonl
data/polymarket/operator/runs/<UTC_RUN_ID>/execution-audit.jsonl
```

Operational rules:

- Never reuse an idempotency store for a different strategy configuration, market universe, or operator approval window.
- Do reuse the same idempotency store only when intentionally retrying the same interrupted run; duplicate keys should be skipped.
- Keep the audit log append-only.
- Preserve both files for post-run reconciliation.
- Do not commit these runtime JSONL files.

Audit events currently include decision-seen, blocked, submitted, and failed execution events. The idempotency key is derived from market id, token id, side, limit price, and notional.

## Storage launch gate

Complete this storage gate before any operator approval to move beyond read-only preflight. These checks materialize the production storage prerequisites but do not provision cloud services or enable live orders:

- [ ] Run `prediction-core storage-readiness --section all --pretty` and review every section.
- [ ] Run `prediction-core storage-health` and confirm configured dependencies are not degraded for the intended launch mode.
- [ ] Confirm `summary.ready_for_live` is true only after Postgres, configured Redis/NATS/S3, ClickHouse expectations, and Grafana provisioning are reviewed.
- [ ] Confirm latest backup exists, checksum verifies, and a disposable restore drill is current.
- [ ] Confirm monitoring/alerting rules in `docs/storage-monitoring-alerting.md` are reviewed and owned.
- [ ] Confirm staging validation in `docs/storage-staging-validation-checklist.md` is complete.
- [ ] Confirm storage secrets are injected by the approved secrets manager and never printed.
- [ ] Run `polymarket-live-preflight` as read-only and archive the redacted output.
- [ ] Stop if any storage gate is failed, stale, or manually waived without written operator approval.

## Pre-live checklist

Complete these items before any operator approval to move beyond read-only preflight. In the current CLI, `--execution-mode live` remains guarded and must not be treated as executable unless every storage and runtime gate is satisfied:

- [ ] Confirm the working tree contains only intended changes and no secrets.
- [ ] Confirm latest relevant tests passed in a non-live environment.
- [ ] Run a `paper` cycle with the same markets, probabilities, edge threshold, notional, and event bound.
- [ ] Run a `dry_run` cycle with the exact intended risk limits and review output.
- [ ] Confirm dry-run `orders_submitted` matches the intended order count and no unexpected signals appear.
- [ ] Confirm dry-run audit log contains `execution_decision_seen` and expected submitted or blocked events.
- [ ] Confirm dry-run idempotency store contains the expected keys.
- [ ] Confirm current exposure and realized PnL inputs are sourced from the latest reconciliation.
- [ ] Run `polymarket-live-preflight` and confirm it is read-only and reports `ready=false` with `live_submission_wired=false` while live submission is unavailable.
- [ ] Confirm `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_FUNDER_ADDRESS`, and `POLYMARKET_CHAIN_ID` are present in the execution environment without printing their values, if checking credential presence.
- [ ] Confirm operator has manually approved market ids, token ids, outcomes, limit prices, and notional caps.
- [ ] Confirm the run is bounded with `--max-events`.
- [ ] Confirm rollback owner and communication channel are available.

## Rollback checklist

If anything is unexpected during preflight or dry-run rehearsal, stay in or return to read-only operation:

- [ ] Stop the active CLI process.
- [ ] Re-run with `--execution-mode paper` only, or stop runtime cycles entirely.
- [ ] Remove live credential variables from the shell/session if they were loaded for preflight.
- [ ] Preserve the run directory, audit log, idempotency store, stdout/stderr capture, and operator notes.
- [ ] Do not delete or edit audit JSONL lines.
- [ ] Record the last observed order ids from runtime output and audit logs.
- [ ] Use the approved exchange UI/API process to inspect and, if needed, cancel outstanding orders manually if any orders were created outside this CLI.
- [ ] Do not attempt `live` again unless it is explicitly exposed by the CLI after real submission is implemented, post-run reconciliation is complete, and a new approval is recorded.
- [ ] If orderbook estimates regress after enabling the optional Rust path, unset `PREDICTION_CORE_RUST_ORDERBOOK` or set it to `0`, then rerun the Python fallback checks documented in `python/README.md`.

## Post-run reconciliation checklist

After every `dry_run` rehearsal. If a `live` runtime-cycle attempt was made, preserve the argparse invalid-choice output for audit:

- [ ] Save runtime stdout/stderr with the run directory.
- [ ] Count `execution_decision_seen`, `execution_order_submitted`, `execution_order_blocked`, and `execution_order_failed` audit events.
- [ ] Compare `orders_submitted` in runtime output with audit `execution_order_submitted` rows.
- [ ] Compare idempotency keys in `idempotency.jsonl` with submitted or failed attempts.
- [ ] For `dry_run`, confirm every submitted order id starts with `dry-run:`.
- [ ] For any future implemented `live` path, fetch exchange-side open/recent orders using the approved authenticated process and compare with local submitted order ids.
- [ ] Identify missing exchange orders, unexpected exchange orders, duplicate idempotency keys, and risk-blocked attempts.
- [ ] Update current total exposure and daily realized PnL before any future run.
- [ ] Archive the run directory outside git.
- [ ] Document outcome, issues, rollback actions, and next approval decision.

## Smoke validation

Validation for this runbook:

```bash
cd /home/jul/P-core
git diff --check -- docs/polymarket-live-ready-runbook.md
PATH="/home/jul/P-core/python/.venv/bin:$PATH" python/scripts/prediction-core polymarket-live-preflight
PATH="/home/jul/P-core/python/.venv/bin:$PATH" python/scripts/prediction-core polymarket-runtime-cycle --help
```
