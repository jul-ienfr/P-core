from __future__ import annotations

from pathlib import Path


STORAGE_PATH = Path("rust/crates/pm_storage/src/lib.rs")


def test_storage_exposes_sql_schema_and_insert_ready_payloads() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    storage = (repo_root / STORAGE_PATH).read_text()

    assert "pub const STORAGE_SQL_SCHEMA" in storage
    assert (
        "CREATE TABLE market_events" in storage
        or "CREATE TABLE IF NOT EXISTS market_events" in storage
    )
    assert (
        "CREATE TABLE signal_events" in storage
        or "CREATE TABLE IF NOT EXISTS signal_events" in storage
    )
    assert (
        "CREATE TABLE risk_decisions" in storage
        or "CREATE TABLE IF NOT EXISTS risk_decisions" in storage
    )
    assert (
        "CREATE TABLE order_intents" in storage
        or "CREATE TABLE IF NOT EXISTS order_intents" in storage
    )
    assert "CREATE TABLE fills" in storage or "CREATE TABLE IF NOT EXISTS fills" in storage
    assert (
        "CREATE TABLE execution_reports" in storage
        or "CREATE TABLE IF NOT EXISTS execution_reports" in storage
    )
    assert "pub struct SqlInsert" in storage
    assert "pub enum SqlValue" in storage
    assert "Text(String)" in storage
    assert "OptF64(Option<f64>)" in storage
    assert "OptI64(Option<i64>)" in storage
    assert "OptText(Option<String>)" in storage
    assert "pub fn market_event_insert(" in storage
    assert "pub fn signal_event_insert(" in storage
    assert "pub fn risk_decision_insert(" in storage
    assert "pub fn order_intent_insert(" in storage
    assert "pub fn fill_insert(" in storage
    assert "pub fn execution_report_insert(" in storage
    assert '"NULL".to_string()' not in storage
