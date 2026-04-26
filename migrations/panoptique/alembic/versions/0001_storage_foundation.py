"""Panoptique storage foundation.

Revision ID: 0001_storage_foundation
Revises:
Create Date: 2026-04-26
"""
from __future__ import annotations

from alembic import op

revision = "0001_storage_foundation"
down_revision = None
branch_labels = None
depends_on = None

RELATIONAL_SQL = """
CREATE TABLE IF NOT EXISTS markets (
    market_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL,
    question TEXT NOT NULL,
    source TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    closed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version TEXT NOT NULL DEFAULT '1.0'
);
CREATE TABLE IF NOT EXISTS market_tokens (
    token_id TEXT PRIMARY KEY,
    market_id TEXT NOT NULL REFERENCES markets(market_id),
    outcome TEXT NOT NULL,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS market_resolution_rules (
    rule_id TEXT PRIMARY KEY,
    market_id TEXT NOT NULL REFERENCES markets(market_id),
    rule_text TEXT NOT NULL,
    source_url TEXT,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    config JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS agent_versions (
    agent_version_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    version TEXT NOT NULL,
    code_ref TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    config JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS shadow_bots (
    shadow_bot_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(agent_id),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    paper_only BOOLEAN NOT NULL DEFAULT TRUE,
    config JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS wallets (
    wallet_id TEXT PRIMARY KEY,
    address TEXT NOT NULL UNIQUE,
    label TEXT,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS external_repos (
    repo_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    name TEXT,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS data_sources (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    base_url TEXT,
    config JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS strategy_configs (
    strategy_config_id TEXT PRIMARY KEY,
    agent_id TEXT REFERENCES agents(agent_id),
    name TEXT NOT NULL,
    paper_only BOOLEAN NOT NULL DEFAULT TRUE,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

HYPERTABLE_SQL = """
CREATE TABLE IF NOT EXISTS market_price_snapshots (
    snapshot_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    token_id TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    price DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    PRIMARY KEY (snapshot_id, observed_at)
);
CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    snapshot_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    bids JSONB NOT NULL DEFAULT '[]'::jsonb,
    asks JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    PRIMARY KEY (snapshot_id, observed_at)
);
CREATE TABLE IF NOT EXISTS trade_events (
    trade_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    size DOUBLE PRECISION NOT NULL,
    side TEXT NOT NULL,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    PRIMARY KEY (trade_id, observed_at)
);
CREATE TABLE IF NOT EXISTS shadow_predictions (
    prediction_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    horizon_seconds INTEGER NOT NULL,
    predicted_crowd_direction TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    rationale TEXT NOT NULL,
    features JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    PRIMARY KEY (prediction_id, observed_at)
);
CREATE TABLE IF NOT EXISTS crowd_flow_observations (
    observation_id TEXT NOT NULL,
    prediction_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    window_seconds INTEGER NOT NULL,
    price_delta DOUBLE PRECISION NOT NULL,
    volume_delta DOUBLE PRECISION NOT NULL,
    direction_hit BOOLEAN NOT NULL,
    liquidity_caveat TEXT,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    PRIMARY KEY (observation_id, observed_at)
);
CREATE TABLE IF NOT EXISTS agent_measurements (
    measurement_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value DOUBLE PRECISION,
    window_seconds INTEGER,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (measurement_id, observed_at)
);
CREATE TABLE IF NOT EXISTS weather_forecasts (
    forecast_id TEXT NOT NULL,
    source TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    target_time TIMESTAMPTZ,
    location TEXT,
    forecast JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (forecast_id, observed_at)
);
CREATE TABLE IF NOT EXISTS weather_observations (
    observation_id TEXT NOT NULL,
    source TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    location TEXT,
    observation JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (observation_id, observed_at)
);
CREATE TABLE IF NOT EXISTS ingestion_health (
    health_id TEXT NOT NULL,
    source TEXT NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    PRIMARY KEY (health_id, checked_at)
);
CREATE TABLE IF NOT EXISTS paper_orders (
    paper_order_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    side TEXT NOT NULL,
    price DOUBLE PRECISION,
    size DOUBLE PRECISION,
    status TEXT NOT NULL,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (paper_order_id, observed_at)
);
CREATE TABLE IF NOT EXISTS paper_positions (
    paper_position_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    avg_price DOUBLE PRECISION,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (paper_position_id, observed_at)
);
CREATE TABLE IF NOT EXISTS execution_events (
    execution_event_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    paper_only BOOLEAN NOT NULL DEFAULT TRUE,
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (execution_event_id, observed_at)
);
"""

CREATE_HYPERTABLE_SQL = """
SELECT create_hypertable('market_price_snapshots', 'observed_at', if_not_exists => TRUE);
SELECT create_hypertable('orderbook_snapshots', 'observed_at', if_not_exists => TRUE);
SELECT create_hypertable('trade_events', 'observed_at', if_not_exists => TRUE);
SELECT create_hypertable('shadow_predictions', 'observed_at', if_not_exists => TRUE);
SELECT create_hypertable('crowd_flow_observations', 'observed_at', if_not_exists => TRUE);
SELECT create_hypertable('agent_measurements', 'observed_at', if_not_exists => TRUE);
SELECT create_hypertable('weather_forecasts', 'observed_at', if_not_exists => TRUE);
SELECT create_hypertable('weather_observations', 'observed_at', if_not_exists => TRUE);
SELECT create_hypertable('ingestion_health', 'checked_at', if_not_exists => TRUE);
SELECT create_hypertable('paper_orders', 'observed_at', if_not_exists => TRUE);
SELECT create_hypertable('paper_positions', 'observed_at', if_not_exists => TRUE);
SELECT create_hypertable('execution_events', 'observed_at', if_not_exists => TRUE);
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute(RELATIONAL_SQL)
    op.execute(HYPERTABLE_SQL)
    op.execute(CREATE_HYPERTABLE_SQL)


def downgrade() -> None:
    for table in [
        "execution_events",
        "paper_positions",
        "paper_orders",
        "ingestion_health",
        "weather_observations",
        "weather_forecasts",
        "agent_measurements",
        "crowd_flow_observations",
        "shadow_predictions",
        "trade_events",
        "orderbook_snapshots",
        "market_price_snapshots",
        "strategy_configs",
        "data_sources",
        "external_repos",
        "wallets",
        "shadow_bots",
        "agent_versions",
        "agents",
        "market_resolution_rules",
        "market_tokens",
        "markets",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
