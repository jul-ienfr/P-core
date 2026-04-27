from __future__ import annotations

from pathlib import Path


RUNTIME_TEST_PATH = Path("rust/crates/pm_storage/src/runtime_integration.rs")


def test_runtime_integration_declares_real_postgres_transaction_rollback_test() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    runtime_test = (repo_root / RUNTIME_TEST_PATH).read_text()

    assert 'sqlx_runtime_rolls_back_transaction_against_real_postgres' in runtime_test
    assert 'let mut tx = pool.begin().await?;' in runtime_test
    assert 'execute_market_event(&mut *tx, &market_event).await?;' in runtime_test
    assert 'execute_signal_event(&mut *tx, &signal).await?;' in runtime_test
    assert 'tx.rollback().await?;' in runtime_test
    assert 'SELECT COUNT(*) FROM market_events' in runtime_test
    assert 'SELECT COUNT(*) FROM signal_events' in runtime_test
    assert 'assert_eq!(market_events, 0);' in runtime_test
    assert 'assert_eq!(signal_events, 0);' in runtime_test
