from __future__ import annotations

from panoptique.cli import build_parser
from panoptique.timescale_diagnostic import (
    EXTENSION_SQL,
    HYPERTABLES_SQL,
    MIGRATIONS_SQL,
    TABLES_SQL,
    build_timescale_runtime_diagnostic,
    expected_hypertables,
    expected_latest_migration,
    expected_tables,
    timescaledb_is_coded,
)


def test_migration_parser_discovers_timescale_contract() -> None:
    assert timescaledb_is_coded() is True
    assert expected_latest_migration() == "0003_operational_state"
    assert {"markets", "prediction_runs", "execution_audit_events"}.issubset(expected_tables())
    assert {"market_price_snapshots", "execution_audit_events"}.issubset(expected_hypertables())


def test_timescale_diagnostic_reports_ok_with_fake_catalog() -> None:
    tables = expected_tables()
    hypertables = expected_hypertables()

    def run(query: str):
        if query == EXTENSION_SQL:
            return [{"extversion": "2.15.3"}]
        if query == MIGRATIONS_SQL:
            return [{"version_num": "0003_operational_state"}]
        if query == TABLES_SQL:
            return [{"table_name": table} for table in sorted(tables)]
        if query == HYPERTABLES_SQL:
            return [{"hypertable_name": table} for table in sorted(hypertables)]
        raise AssertionError(query)

    result = build_timescale_runtime_diagnostic(
        database_url="postgresql+psycopg://user:secret@localhost/panoptique",
        query_runner=run,
    )

    assert result["ok"] is True
    assert result["database_url_redacted"] == "postgresql+psycopg://user:***@localhost/panoptique"
    assert result["reachable"] is True
    assert result["timescaledb_extension"] == {"coded": True, "installed": True, "version": "2.15.3"}
    assert result["migrations_state"]["up_to_date"] is True
    assert result["missing"] == []
    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False


def test_timescale_diagnostic_reports_missing_catalog_items() -> None:
    def run(query: str):
        if query == EXTENSION_SQL:
            return []
        if query == MIGRATIONS_SQL:
            return [{"version_num": "0001_storage_foundation"}]
        if query == TABLES_SQL:
            return [{"table_name": "markets"}]
        if query == HYPERTABLES_SQL:
            return []
        raise AssertionError(query)

    result = build_timescale_runtime_diagnostic(
        database_url="postgresql+psycopg://user:secret@localhost/panoptique",
        query_runner=run,
    )

    assert result["ok"] is False
    assert result["reachable"] is True
    assert result["timescaledb_extension"]["coded"] is True
    assert result["timescaledb_extension"]["installed"] is False
    assert result["migrations_state"]["latest_expected"] == "0003_operational_state"
    assert "extension:timescaledb" in result["missing"]
    assert "migration:0003_operational_state" in result["missing"]
    assert "table:prediction_runs" in result["missing"]
    assert "hypertable:execution_audit_events" in result["missing"]


def test_panoptique_parser_accepts_timescale_diagnostic_command() -> None:
    args = build_parser().parse_args(["timescale-diagnostic", "--database-url", "postgresql://u:p@localhost/db"])
    assert args.command == "timescale-diagnostic"
    assert args.database_url == "postgresql://u:p@localhost/db"
