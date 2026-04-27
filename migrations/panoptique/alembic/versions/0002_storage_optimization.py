"""Panoptique storage optimization policies.

Revision ID: 0002_storage_optimization
Revises: 0001_storage_foundation
Create Date: 2026-04-26
"""
from __future__ import annotations

from alembic import op

revision = "0002_storage_optimization"
down_revision = "0001_storage_foundation"
branch_labels = None
depends_on = None

HIGH_VOLUME_HYPERTABLES = [
    "market_price_snapshots",
    "orderbook_snapshots",
    "trade_events",
    "ingestion_health",
]

COMPRESSION_SQL = """
ALTER TABLE market_price_snapshots SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'market_id,token_id',
    timescaledb.compress_orderby = 'observed_at DESC'
);
ALTER TABLE orderbook_snapshots SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'market_id,token_id',
    timescaledb.compress_orderby = 'observed_at DESC'
);
ALTER TABLE trade_events SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'market_id,token_id',
    timescaledb.compress_orderby = 'observed_at DESC'
);
ALTER TABLE ingestion_health SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'source,status',
    timescaledb.compress_orderby = 'checked_at DESC'
);
SELECT add_compression_policy('market_price_snapshots', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_compression_policy('orderbook_snapshots', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_compression_policy('trade_events', INTERVAL '14 days', if_not_exists => TRUE);
SELECT add_compression_policy('ingestion_health', INTERVAL '30 days', if_not_exists => TRUE);
"""

CONTINUOUS_AGGREGATE_SQL = """
CREATE MATERIALIZED VIEW IF NOT EXISTS market_price_1m
WITH (timescaledb.continuous) AS
SELECT market_id, token_id, time_bucket('1 minute', observed_at) AS bucket,
       avg(price) AS avg_price, min(price) AS min_price, max(price) AS max_price,
       sum(volume) AS volume_sum, count(*) AS sample_count
FROM market_price_snapshots
GROUP BY market_id, token_id, bucket
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS market_price_5m
WITH (timescaledb.continuous) AS
SELECT market_id, token_id, time_bucket('5 minutes', observed_at) AS bucket,
       avg(price) AS avg_price, min(price) AS min_price, max(price) AS max_price,
       sum(volume) AS volume_sum, count(*) AS sample_count
FROM market_price_snapshots
GROUP BY market_id, token_id, bucket
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS market_price_15m
WITH (timescaledb.continuous) AS
SELECT market_id, token_id, time_bucket('15 minutes', observed_at) AS bucket,
       avg(price) AS avg_price, min(price) AS min_price, max(price) AS max_price,
       sum(volume) AS volume_sum, count(*) AS sample_count
FROM market_price_snapshots
GROUP BY market_id, token_id, bucket
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS trade_volume_5m
WITH (timescaledb.continuous) AS
SELECT market_id, token_id, time_bucket('5 minutes', observed_at) AS bucket,
       sum(size) AS traded_size, sum(size * price) AS notional, count(*) AS trade_count
FROM trade_events
GROUP BY market_id, token_id, bucket
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS orderbook_liquidity_5m
WITH (timescaledb.continuous) AS
SELECT market_id, token_id, time_bucket('5 minutes', observed_at) AS bucket,
       avg(NULLIF((asks->0->>'price')::double precision - (bids->0->>'price')::double precision, NULL)) AS avg_top_spread,
       avg(jsonb_array_length(bids) + jsonb_array_length(asks)) AS avg_depth_levels,
       count(*) AS sample_count
FROM orderbook_snapshots
GROUP BY market_id, token_id, bucket
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS shadow_prediction_outcomes_15m AS
SELECT sp.agent_id, sp.market_id, time_bucket('15 minutes', cfo.observed_at) AS bucket,
       avg(CASE WHEN cfo.direction_hit THEN 1.0 ELSE 0.0 END) AS direction_hit_rate,
       avg(cfo.price_delta) AS avg_price_delta,
       sum(cfo.volume_delta) AS volume_delta_sum,
       count(*) AS matched_count
FROM crowd_flow_observations cfo
JOIN shadow_predictions sp ON sp.prediction_id = cfo.prediction_id
GROUP BY sp.agent_id, sp.market_id, bucket
WITH NO DATA;
"""

CONTINUOUS_AGGREGATE_POLICY_SQL = """
SELECT add_continuous_aggregate_policy('market_price_1m', start_offset => INTERVAL '7 days', end_offset => INTERVAL '1 minute', schedule_interval => INTERVAL '1 minute', if_not_exists => TRUE);
SELECT add_continuous_aggregate_policy('market_price_5m', start_offset => INTERVAL '30 days', end_offset => INTERVAL '5 minutes', schedule_interval => INTERVAL '5 minutes', if_not_exists => TRUE);
SELECT add_continuous_aggregate_policy('market_price_15m', start_offset => INTERVAL '90 days', end_offset => INTERVAL '15 minutes', schedule_interval => INTERVAL '15 minutes', if_not_exists => TRUE);
SELECT add_continuous_aggregate_policy('trade_volume_5m', start_offset => INTERVAL '30 days', end_offset => INTERVAL '5 minutes', schedule_interval => INTERVAL '5 minutes', if_not_exists => TRUE);
SELECT add_continuous_aggregate_policy('orderbook_liquidity_5m', start_offset => INTERVAL '30 days', end_offset => INTERVAL '5 minutes', schedule_interval => INTERVAL '5 minutes', if_not_exists => TRUE);
"""

RETENTION_POLICY_SQL_DOCUMENTED_ONLY = """
-- Destructive retention is intentionally not executed by this migration.
-- Raw JSONL/Parquet audit archives under data/panoptique remain canonical replay material.
-- After documented audit coverage and restore smoke tests, an operator may apply bounded
-- policies manually, for example:
-- SELECT add_retention_policy('orderbook_snapshots', INTERVAL '180 days', if_not_exists => TRUE);
-- SELECT add_retention_policy('trade_events', INTERVAL '365 days', if_not_exists => TRUE);
"""

CONTINUOUS_AGGREGATES = [
    "market_price_1m",
    "market_price_5m",
    "market_price_15m",
    "trade_volume_5m",
    "orderbook_liquidity_5m",
]

ALL_MATERIALIZED_VIEWS = [
    "shadow_prediction_outcomes_15m",
    "orderbook_liquidity_5m",
    "trade_volume_5m",
    "market_price_15m",
    "market_price_5m",
    "market_price_1m",
]


def upgrade() -> None:
    op.execute(COMPRESSION_SQL)
    op.execute(CONTINUOUS_AGGREGATE_SQL)
    op.execute(CONTINUOUS_AGGREGATE_POLICY_SQL)
    op.execute(RETENTION_POLICY_SQL_DOCUMENTED_ONLY)


def downgrade() -> None:
    for view in CONTINUOUS_AGGREGATES:
        op.execute(f"SELECT remove_continuous_aggregate_policy('{view}', if_exists => TRUE)")
    for table in HIGH_VOLUME_HYPERTABLES:
        op.execute(f"SELECT remove_compression_policy('{table}', if_exists => TRUE)")
    for view in ALL_MATERIALIZED_VIEWS:
        op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {view} CASCADE")
    for table in HIGH_VOLUME_HYPERTABLES:
        op.execute(f"ALTER TABLE IF EXISTS {table} SET (timescaledb.compress = false)")
