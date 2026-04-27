from __future__ import annotations

from pathlib import Path


RUNTIME_TEST_PATH = Path("rust/crates/pm_storage/src/runtime_integration.rs")


def test_runtime_integration_declares_real_postgres_transaction_commit_flow_test() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    runtime_test = (repo_root / RUNTIME_TEST_PATH).read_text()

    assert 'sqlx_runtime_commits_multi_table_transaction_against_real_postgres' in runtime_test
    assert 'let mut tx = pool.begin().await?;' in runtime_test
    assert 'execute_market_event(&mut *tx, &market_event).await?;' in runtime_test
    assert 'execute_signal_event(&mut *tx, &signal).await?;' in runtime_test
    assert 'execute_risk_decision(&mut *tx, &decision).await?;' in runtime_test
    assert 'execute_order_intent(&mut *tx, &order_intent).await?;' in runtime_test
    assert 'tx.commit().await?;' in runtime_test
    assert 'SELECT COUNT(*) FROM market_events' in runtime_test
    assert 'SELECT COUNT(*) FROM signal_events' in runtime_test
    assert 'SELECT COUNT(*) FROM risk_decisions' in runtime_test
    assert 'SELECT COUNT(*) FROM order_intents' in runtime_test
    assert 'assert_eq!(market_events, 1);' in runtime_test
    assert 'assert_eq!(signal_events, 1);' in runtime_test
    assert 'assert_eq!(risk_decisions, 1);' in runtime_test
    assert 'assert_eq!(order_intents, 1);' in runtime_test
