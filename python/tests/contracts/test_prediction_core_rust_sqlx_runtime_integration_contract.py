from __future__ import annotations

from pathlib import Path


STORAGE_PATH = Path("rust/crates/pm_storage/src/lib.rs")
RUNTIME_TEST_PATH = Path("rust/crates/pm_storage/src/runtime_integration.rs")
MANIFEST_PATH = Path("rust/crates/pm_storage/Cargo.toml")


def test_storage_declares_real_postgres_runtime_integration_test() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    storage = (repo_root / STORAGE_PATH).read_text()
    runtime_test = (repo_root / RUNTIME_TEST_PATH).read_text()
    manifest = (repo_root / MANIFEST_PATH).read_text()

    assert 'mod runtime_integration;' in storage
    assert '[dev-dependencies]' in manifest
    assert 'tokio = { version = "1", features = ["macros", "rt-multi-thread"] }' in manifest
    assert '#[tokio::test]' in runtime_test
    assert 'DATABASE_URL' in runtime_test
    assert 'PgPoolOptions::new()' in runtime_test
    assert 'apply_schema(&pool).await?' in runtime_test
    assert 'execute_market_event(&pool, &market_event).await?' in runtime_test
    assert 'execute_signal_event(&pool, &signal).await?' in runtime_test
    assert 'execute_risk_decision(&pool, &decision).await?' in runtime_test
    assert 'execute_order_intent(&pool, &order_intent).await?' in runtime_test
    assert 'execute_fill(&pool, &fill).await?' in runtime_test
    assert 'execute_execution_report(&pool, &report).await?' in runtime_test
    assert 'SELECT COUNT(*) FROM market_events' in runtime_test
    assert 'SELECT COUNT(*) FROM signal_events' in runtime_test
    assert 'SELECT COUNT(*) FROM risk_decisions' in runtime_test
    assert 'SELECT COUNT(*) FROM order_intents' in runtime_test
    assert 'SELECT COUNT(*) FROM fills' in runtime_test
    assert 'SELECT COUNT(*) FROM execution_reports' in runtime_test
