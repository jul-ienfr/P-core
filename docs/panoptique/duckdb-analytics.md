# Panoptique DuckDB analytics examples

DuckDB is for offline analytics over exported artifacts. It is never the live database and never the source of truth.

## Export inputs

Create approved, secret-redacted exports with the Panoptique CLI:

```bash
cd /home/jul/prediction_core/python
PYTHONPATH=src python3 -m panoptique.cli export-parquet \
  --table shadow_predictions \
  --from 2026-04-26T00:00:00Z \
  --to 2026-04-27T00:00:00Z \
  --output-dir /home/jul/prediction_core/data/panoptique/exports \
  --sqlite-db /path/to/local-fixture.sqlite

PYTHONPATH=src python3 -m panoptique.cli export-parquet \
  --table crowd_flow_observations \
  --from 2026-04-26T00:00:00Z \
  --to 2026-04-27T00:00:00Z \
  --output-dir /home/jul/prediction_core/data/panoptique/exports \
  --sqlite-db /path/to/local-fixture.sqlite
```

In production, use an equivalent read-only PostgreSQL export connection. Do not export `wallets`, credentials, or live execution data.

## Read Parquet exports

```sql
INSTALL parquet;
LOAD parquet;

SELECT *
FROM read_parquet('/home/jul/prediction_core/data/panoptique/exports/shadow_predictions_*.parquet')
LIMIT 10;
```

If a minimal development environment lacks a Parquet engine, tests may produce a `.parquet`-named JSONL fallback with a manifest format of `jsonl-parquet-fallback`. Install `pyarrow` for true Parquet files before DuckDB analysis.

## Shadow prediction hit-rate by agent

```sql
WITH predictions AS (
  SELECT prediction_id, market_id, agent_id, observed_at, confidence, predicted_crowd_direction
  FROM read_parquet('/home/jul/prediction_core/data/panoptique/exports/shadow_predictions_*.parquet')
),
observations AS (
  SELECT prediction_id, market_id, observed_at, direction_hit, price_delta, volume_delta
  FROM read_parquet('/home/jul/prediction_core/data/panoptique/exports/crowd_flow_observations_*.parquet')
)
SELECT
  p.agent_id,
  count(*) AS matched_predictions,
  avg(CASE WHEN o.direction_hit THEN 1.0 ELSE 0.0 END) AS hit_rate,
  avg(p.confidence) AS avg_confidence,
  avg(o.price_delta) AS avg_price_delta,
  sum(o.volume_delta) AS total_volume_delta
FROM predictions p
JOIN observations o USING (prediction_id, market_id)
GROUP BY p.agent_id
ORDER BY matched_predictions DESC;
```

## Confidence buckets

```sql
SELECT
  floor(confidence * 10) / 10.0 AS confidence_bucket,
  count(*) AS predictions
FROM read_parquet('/home/jul/prediction_core/data/panoptique/exports/shadow_predictions_*.parquet')
GROUP BY confidence_bucket
ORDER BY confidence_bucket;
```

## Paper-only caveat

These queries support research measurement only. They do not place orders, do not imply live edge, and do not change the Phase 10 approval gate.
