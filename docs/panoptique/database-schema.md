# Panoptique database schema

## Relational tables

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

## Timescale hypertables

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

The first migration enables `CREATE EXTENSION IF NOT EXISTS timescaledb` and calls `create_hypertable` for timestamped tables.

## Raw payload policy

Tables include JSONB columns such as `raw`, `bids`, `asks`, `features`, and `metrics` to retain external payload context. Raw external payloads should also be journaled to JSONL/Parquet audit/replay archives.

## Retention/compression intentions

Retention and Timescale compression policies are deferred to the storage optimization phase after collection volume is measurable.
