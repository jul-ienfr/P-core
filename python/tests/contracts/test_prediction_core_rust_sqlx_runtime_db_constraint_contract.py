from __future__ import annotations

from pathlib import Path


LIB_PATH = Path("rust/crates/pm_storage/src/lib.rs")
RUNTIME_TEST_PATH = Path("rust/crates/pm_storage/src/runtime_integration.rs")


def test_storage_declares_real_postgres_unique_constraint_and_duplicate_insert_test() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    storage = (repo_root / LIB_PATH).read_text()
    runtime_test = (repo_root / RUNTIME_TEST_PATH).read_text()

    assert 'CREATE TABLE IF NOT EXISTS market_events (' in storage or 'CREATE TABLE market_events (' in storage
    assert 'event_id TEXT NOT NULL UNIQUE' in storage or 'event_id TEXT PRIMARY KEY' in storage
    assert 'event.event_id.to_string()' in storage
    assert '"event_id"' in storage

    assert 'sqlx_runtime_rejects_duplicate_market_event_insert_against_real_postgres' in runtime_test
    assert 'execute_market_event(&pool, &market_event).await?;' in runtime_test
    assert 'let duplicate_insert = execute_market_event(&pool, &market_event).await;' in runtime_test
    assert 'assert!(duplicate_insert.is_err())' in runtime_test
    assert 'duplicate key value violates unique constraint' in runtime_test or '23505' in runtime_test
