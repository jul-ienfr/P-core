# Polymarket weather account-learning smoke replay

This runbook documents a reproducible, paper-only path from a ranked weather account followlist to learned patterns and shadow paper-order artifacts. It is intended for operator validation and CI smoke coverage, not live trading.

## Safety contract

- The pipeline is read-only after the optional public-trades backfill step.
- All produced artifacts must keep `paper_only: true` and `live_order_allowed: false`.
- Tests use local fixtures only and make no network calls.
- Generated examples should write under `data/polymarket/account-analysis/` for manual runs. Use a temporary directory in tests.
- Shadow paper orders are simulations from historical account behavior plus independent forecast/orderbook fixtures; they are not execution instructions.

## Inputs

Minimum local inputs:

1. `weather_followlist_top10.csv` — top weather wallets with `wallet`, `handle`, `rank`, and optional metadata.
2. `public_account_trades_backfilled.json` — public/backfilled account trades from the followlist.
3. `markets.json` — candidate weather markets with question, city/date, price, and model probability.
4. `orderbooks.json` — market-id keyed best bid/ask/depth snapshot for paper replay.
5. `forecasts.json` — surface-key keyed independent weather forecast features, where keys look like `london|april 25`.
6. `resolutions.json` — resolution metadata/status reference for operator review. The current smoke runner keeps this as an explicit input artifact for provenance; no network resolution lookup is required.

The CI fixture set lives in `python/tests/fixtures/weather_account_learning/`.

## Five-step pipeline

Set a run directory:

```bash
export PYTHONPATH=python/src
export ANALYSIS_DIR=data/polymarket/account-analysis
mkdir -p "$ANALYSIS_DIR"
```

### 1) Select top-10 accounts and obtain public trades

For offline smoke/CI, use a pre-backfilled JSON fixture. For an operator refresh, the read-only public backfill command is:

```bash
python3 -m weather_pm.cli backfill-account-trades \
  --followlist "$ANALYSIS_DIR/weather_followlist_top10.csv" \
  --out-json "$ANALYSIS_DIR/public_account_trades_backfilled.json" \
  --limit-accounts 10 \
  --trades-per-account 100
```

This calls only the public Polymarket data API and writes a local artifact. Do not run it from tests.

### 2) Classify weather trades and account profiles

```bash
python3 -m weather_pm.cli import-account-trades \
  --trades-json "$ANALYSIS_DIR/public_account_trades_backfilled.json" \
  --trades-out "$ANALYSIS_DIR/weather_trades.json" \
  --profiles-out "$ANALYSIS_DIR/account_profiles.json"
```

Expected artifacts:

- `$ANALYSIS_DIR/weather_trades.json`
- `$ANALYSIS_DIR/account_profiles.json`

### 3) Build trade/no-trade examples and shadow profile report

```bash
python3 -m weather_pm.cli shadow-profile-report \
  --weather-trades-json "$ANALYSIS_DIR/weather_trades.json" \
  --markets-json "$ANALYSIS_DIR/markets.json" \
  --dataset-out "$ANALYSIS_DIR/trade_no_trade_dataset.json" \
  --report-out "$ANALYSIS_DIR/shadow_profile_report.json" \
  --accounts-csv "$ANALYSIS_DIR/weather_followlist_top10.csv" \
  --limit-accounts 10 \
  --limit 10
```

Expected checks: at least one `trade` example and at least one `no_trade` example. No-trade rows are important because the replay should learn abstention/pass behavior, not copy trades.

### 4) Extract learned account behavior patterns

```bash
python3 -m weather_pm.cli shadow-patterns-report \
  --dataset-json "$ANALYSIS_DIR/trade_no_trade_dataset.json" \
  --output-json "$ANALYSIS_DIR/learned_patterns.json" \
  --output-md "$ANALYSIS_DIR/learned_patterns.md" \
  --limit 10
```

Expected artifacts:

- `$ANALYSIS_DIR/learned_patterns.json`
- `$ANALYSIS_DIR/learned_patterns.md`

### 5) Replay as paper-only shadow orders

```bash
python3 -m weather_pm.cli shadow-paper-runner \
  --dataset-json "$ANALYSIS_DIR/trade_no_trade_dataset.json" \
  --orderbooks-json "$ANALYSIS_DIR/orderbooks.json" \
  --forecasts-json "$ANALYSIS_DIR/forecasts.json" \
  --run-id weather-account-learning-smoke \
  --output-json "$ANALYSIS_DIR/shadow_paper_orders.json"
```

When fixtures include an account trade with positive independent edge plus available orderbook and forecast features, `summary.paper_orders` should be at least `1`. Skips are expected for no-trade labels, missing features, or missing independent edge.

## Validation

Focused smoke test:

```bash
PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_account_learning_smoke.py -q
```

Syntax check for touched Python test/script files:

```bash
PYTHONPATH=python/src python3 -m py_compile python/tests/test_weather_account_learning_smoke.py
```

Whitespace check:

```bash
git diff --check -- docs/polymarket-weather-account-learning.md python/tests/test_weather_account_learning_smoke.py python/tests/fixtures/weather_account_learning
```

## Fixture replay notes

The checked-in fixture intentionally includes:

- a ranked top-10 style followlist with a traded account and an abstaining account;
- public/backfilled raw trades including weather and non-weather examples;
- London and Paris market surfaces;
- orderbook and forecast features for the traded London surface;
- resolution metadata for provenance and operator review.

This keeps the smoke path deterministic, paper-only, and network-free while covering the full top-10 → patterns → paper replay flow.
