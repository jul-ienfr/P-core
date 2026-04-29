from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Iterable

from .db import get_sync_database_url, mask_database_url

QueryRunner = Callable[[str], list[dict[str, Any]]]

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = ROOT / "migrations" / "panoptique" / "alembic" / "versions"

CREATE_TABLE_RE = re.compile(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)
CREATE_HYPERTABLE_RE = re.compile(r"create_hypertable\(\s*'([^']+)'", re.IGNORECASE)
REVISION_RE = re.compile(r"^revision\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE)

EXTENSION_SQL = "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"
MIGRATIONS_SQL = "SELECT version_num FROM alembic_version ORDER BY version_num"
TABLES_SQL = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
HYPERTABLES_SQL = "SELECT hypertable_name FROM timescaledb_information.hypertables WHERE hypertable_schema = 'public' ORDER BY hypertable_name"


def _migration_sources(migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    return [path.read_text(encoding="utf-8") for path in sorted(migrations_dir.glob("*.py"))]


def expected_tables(migrations_dir: Path = MIGRATIONS_DIR) -> set[str]:
    return {match.group(1) for sql in _migration_sources(migrations_dir) for match in CREATE_TABLE_RE.finditer(sql)}


def expected_hypertables(migrations_dir: Path = MIGRATIONS_DIR) -> set[str]:
    return {match.group(1) for sql in _migration_sources(migrations_dir) for match in CREATE_HYPERTABLE_RE.finditer(sql)}


def expected_latest_migration(migrations_dir: Path = MIGRATIONS_DIR) -> str | None:
    revisions = [match.group(1) for sql in _migration_sources(migrations_dir) if (match := REVISION_RE.search(sql))]
    return revisions[-1] if revisions else None


def timescaledb_is_coded(migrations_dir: Path = MIGRATIONS_DIR) -> bool:
    return any("CREATE EXTENSION IF NOT EXISTS timescaledb" in sql for sql in _migration_sources(migrations_dir))


def _values(rows: Iterable[dict[str, Any]], key: str) -> set[str]:
    return {str(row[key]) for row in rows if row.get(key) is not None}


def _sqlalchemy_query_runner(database_url: str) -> QueryRunner:
    try:
        from sqlalchemy import create_engine, text
    except ImportError as exc:  # pragma: no cover - exercised through diagnostic error path in environments without extra
        raise RuntimeError("SQLAlchemy is required for live PostgreSQL/TimescaleDB diagnostics") from exc

    engine = create_engine(database_url, isolation_level="AUTOCOMMIT")

    def run(query: str) -> list[dict[str, Any]]:
        with engine.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(text(query)).fetchall()]

    return run


def build_timescale_runtime_diagnostic(
    *,
    database_url: str | None = None,
    query_runner: QueryRunner | None = None,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> dict[str, Any]:
    url = database_url or get_sync_database_url(required=False)
    tables_expected = expected_tables(migrations_dir)
    hypertables_expected = expected_hypertables(migrations_dir)
    latest_migration = expected_latest_migration(migrations_dir)
    missing: list[str] = []
    tables_present = {name: False for name in sorted(tables_expected)}
    hypertables_present = {name: False for name in sorted(hypertables_expected)}
    timescaledb_extension: dict[str, Any] = {"coded": timescaledb_is_coded(migrations_dir), "installed": False, "version": None}
    migrations_state: dict[str, Any] = {"latest_expected": latest_migration, "applied": [], "up_to_date": False}
    reachable = False

    try:
        run = query_runner or _sqlalchemy_query_runner(url)
        extension_rows = run(EXTENSION_SQL)
        reachable = True
        if extension_rows:
            timescaledb_extension["installed"] = True
            timescaledb_extension["version"] = extension_rows[0].get("extversion")
        else:
            missing.append("extension:timescaledb")

        try:
            applied = sorted(_values(run(MIGRATIONS_SQL), "version_num"))
        except Exception as exc:
            applied = []
            missing.append(f"migrations:alembic_version:{type(exc).__name__}")
        migrations_state["applied"] = applied
        migrations_state["up_to_date"] = latest_migration in applied if latest_migration else False
        if latest_migration and latest_migration not in applied:
            missing.append(f"migration:{latest_migration}")

        actual_tables = _values(run(TABLES_SQL), "table_name")
        tables_present = {name: name in actual_tables for name in sorted(tables_expected)}
        missing.extend(f"table:{name}" for name, present in tables_present.items() if not present)

        try:
            actual_hypertables = _values(run(HYPERTABLES_SQL), "hypertable_name")
            hypertables_present = {name: name in actual_hypertables for name in sorted(hypertables_expected)}
            missing.extend(f"hypertable:{name}" for name, present in hypertables_present.items() if not present)
        except Exception as exc:
            missing.append(f"hypertables:timescaledb_information:{type(exc).__name__}")
    except Exception as exc:
        missing.append(f"reachable:{type(exc).__name__}:{exc}")

    ok = (
        reachable
        and bool(timescaledb_extension["coded"])
        and bool(timescaledb_extension["installed"])
        and bool(migrations_state["up_to_date"])
        and all(tables_present.values())
        and all(hypertables_present.values())
    )
    return {
        "ok": ok,
        "database_url_redacted": mask_database_url(url),
        "reachable": reachable,
        "timescaledb_extension": timescaledb_extension,
        "migrations_state": migrations_state,
        "tables_present": tables_present,
        "hypertables_present": hypertables_present,
        "missing": sorted(set(missing)),
        "paper_only": True,
        "live_order_allowed": False,
    }
