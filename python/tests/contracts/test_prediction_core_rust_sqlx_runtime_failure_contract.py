from __future__ import annotations

from pathlib import Path


RUNTIME_TEST_PATH = Path("rust/crates/pm_storage/src/runtime_integration.rs")


def test_storage_declares_real_postgres_failure_path_runtime_test() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    runtime_test = (repo_root / RUNTIME_TEST_PATH).read_text()

    assert '#[tokio::test]' in runtime_test
    assert 'sqlx_runtime_allows_repeated_schema_apply_against_real_postgres' in runtime_test
    assert 'apply_schema(&pool).await?' in runtime_test
    assert 'let second_apply = apply_schema(&pool).await;' in runtime_test
    assert 'assert!(second_apply.is_ok())' in runtime_test
    assert 'SELECT COUNT(*) FROM market_events' in runtime_test
    assert 'SELECT COUNT(*) FROM execution_reports' in runtime_test


def test_storage_declares_real_postgres_insert_after_repeated_schema_apply_runtime_test() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    runtime_test = (repo_root / RUNTIME_TEST_PATH).read_text()

    assert '#[tokio::test]' in runtime_test
    assert 'sqlx_runtime_preserves_insertability_after_repeated_schema_apply_against_real_postgres' in runtime_test
    assert 'apply_schema(&pool).await?;' in runtime_test
    assert 'execute_market_event(&pool, &market_event).await?;' in runtime_test
    assert 'SELECT market_id FROM market_events WHERE event_id = $1 LIMIT 1' in runtime_test
    assert 'assert_eq!(market_events, 1);' in runtime_test
