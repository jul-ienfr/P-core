# Panoptique Shadow Bots

Phase 3 introduces deterministic, paper-only shadow bots. They simulate common retail bot behavior so Panoptique can measure crowd-flow hypotheses before any expensive LLM calls or execution logic exists.

## Safety scope

- Predictions target **crowd behavior, not event truth**.
- Every prediction is paper-only and records `trading_action: none`.
- No wallet credentials are read.
- No real orders are created.
- No LLM calls are made.
- Raw JSONL archives remain mandatory even when repository/DB persistence is available.

## Contract shape

`ShadowContext` contains:

- `market_snapshot`: the normalized market price snapshot.
- `orderbook_snapshot`: optional normalized orderbook snapshot.
- `weather_score`: optional fixture/model probability for weather-style markets.
- `recent_prices`: optional recent prices from snapshots.
- `wallet_signal`: optional future copy-wallet signal.

`ShadowPrediction` rows use stable deterministic IDs:

```txt
shadow-{bot_id}-{market_id}-{observed_at_utc}-v1
```

Each row includes schema version `1.0`, an agent id, predicted crowd direction, confidence, rationale, and feature metadata including `prediction_target: crowd_behavior_not_event_truth`.

## Archetypes v0

### `weather_naive_threshold`

Uses a fixture/model weather score. It emits an expected crowd side when the score crosses common thresholds:

- `>= 0.60`: crowd likely follows Yes/up.
- `<= 0.40`: crowd likely follows No/down.
- between thresholds: flat.
- missing score: `insufficient_data`.

It exists to model simple retail scripts that convert weather probabilities directly into Polymarket sentiment.

### `round_number_price_bot`

Detects salient probability levels around:

```txt
0.50, 0.60, 0.65, 0.70, 0.75, 0.80
```

Near one of these levels, the bot emits an up crowd-flow prediction. Otherwise it emits flat. It exists because retail bots and humans often anchor on round prices and threshold-like levels.

### `edge_8pct_bot`

Computes `weather_score - market_price` and simulates the common “edge > 8%” rule. Default threshold is `0.08`, but it is configurable for tests and later experiments.

- edge above threshold: up.
- edge below negative threshold: down.
- otherwise: flat.
- missing score or price: `insufficient_data`.

### `momentum_naive_bot`

Uses recent price movement from snapshots. If the latest price is meaningfully above the first recent price, it predicts crowd-following up; if meaningfully below, down; otherwise flat.

It exists to capture common trend-following behavior without claiming the trend is correct about the event.

### `copy_wallet_placeholder`

Emits `insufficient_data` unless an explicit wallet signal is supplied by fixture/repository data. It does not access wallets and does not trade. The purpose is to reserve a stable contract surface for later wallet-copy research without introducing credentials or live actions in Phase 3.

## CLI commands

### `shadow-evaluate-fixture`

Reads a JSON fixture containing a market snapshot and optional orderbook/weather/recent-price inputs, writes predictions to JSONL, and persists them through the repository path when SQLite is supplied.

```bash
PYTHONPATH=src python3 -m panoptique.cli shadow-evaluate-fixture \
  --fixture tests/fixtures/panoptique/shadow_context.json \
  --output-dir /home/jul/prediction_core/data/panoptique/shadow_predictions \
  --sqlite-db /tmp/panoptique.sqlite
```

### `shadow-evaluate-db`

Reads recent repository snapshots, evaluates shadow bots, writes `shadow_predictions` rows and JSONL archives. If no real Postgres/repository is available, it produces explicit `db_status=skipped_unavailable` output so the command remains testable and auditable.
