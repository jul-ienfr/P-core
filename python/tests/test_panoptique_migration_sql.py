from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "panoptique" / "alembic" / "versions" / "0001_storage_foundation.py"
OPTIMIZATION_MIGRATION = ROOT / "migrations" / "panoptique" / "alembic" / "versions" / "0002_storage_optimization.py"


def test_migration_enables_timescaledb_and_hypertables() -> None:
    sql = MIGRATION.read_text()
    assert "CREATE EXTENSION IF NOT EXISTS timescaledb" in sql
    for table in [
        "market_price_snapshots",
        "orderbook_snapshots",
        "trade_events",
        "shadow_predictions",
        "crowd_flow_observations",
        "agent_measurements",
        "weather_forecasts",
        "weather_observations",
        "ingestion_health",
        "paper_orders",
        "paper_positions",
        "execution_events",
    ]:
        assert f"create_hypertable('{table}'" in sql


def test_migration_defines_core_relational_tables() -> None:
    sql = MIGRATION.read_text()
    for table in [
        "markets",
        "market_tokens",
        "market_resolution_rules",
        "agents",
        "agent_versions",
        "shadow_bots",
        "wallets",
        "external_repos",
        "data_sources",
        "strategy_configs",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql


def test_storage_optimization_migration_documents_safe_policies() -> None:
    sql = OPTIMIZATION_MIGRATION.read_text()
    for table in ["market_price_snapshots", "orderbook_snapshots", "trade_events", "ingestion_health"]:
        assert f"add_compression_policy('{table}'" in sql
    for aggregate in [
        "market_price_1m",
        "market_price_5m",
        "market_price_15m",
        "trade_volume_5m",
        "orderbook_liquidity_5m",
        "shadow_prediction_outcomes_15m",
    ]:
        assert f"CREATE MATERIALIZED VIEW IF NOT EXISTS {aggregate}" in sql
    assert "Destructive retention is intentionally not executed" in sql
    assert "add_retention_policy" in sql
