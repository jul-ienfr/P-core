from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "infra" / "analytics" / "clickhouse" / "init" / "001_prediction_core_schema.sql"


def test_clickhouse_schema_defines_final_tables() -> None:
    sql = SCHEMA.read_text()
    for table in [
        "prediction_runs",
        "market_snapshots",
        "orderbook_snapshots",
        "strategy_signals",
        "profile_decisions",
        "paper_orders",
        "paper_positions",
        "paper_pnl_snapshots",
        "execution_events",
        "resolution_events",
        "strategy_metrics",
        "profile_metrics",
        "debug_decisions",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS prediction_core.{table}" in sql


def test_clickhouse_schema_is_profile_strategy_comparable() -> None:
    sql = SCHEMA.read_text()
    for column in [
        "run_id String",
        "strategy_id String",
        "profile_id String",
        "market_id String",
        "observed_at DateTime64",
        "mode String",
        "raw String",
    ]:
        assert column in sql
    assert "ENGINE = MergeTree" in sql
    assert "PARTITION BY toYYYYMM(observed_at)" in sql


def test_clickhouse_schema_keeps_paper_live_separation_flags() -> None:
    sql = SCHEMA.read_text()
    assert "paper_only Bool DEFAULT true" in sql
    assert "live_order_allowed Bool DEFAULT false" in sql
