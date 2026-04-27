from __future__ import annotations

import os

import pytest

from panoptique.db import get_database_url, get_sync_database_url, mask_database_url
from panoptique.repositories import PANOPTIQUE_TABLES_SQL


def test_database_url_loader_requires_env_by_default(monkeypatch) -> None:
    monkeypatch.delenv("PANOPTIQUE_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="PANOPTIQUE_DATABASE_URL"):
        get_database_url()


def test_database_url_loader_can_return_default_for_local_dev(monkeypatch) -> None:
    monkeypatch.delenv("PANOPTIQUE_DATABASE_URL", raising=False)
    assert get_database_url(required=False).startswith("postgresql+asyncpg://")


def test_sync_database_url_derives_asyncpg_url(monkeypatch) -> None:
    monkeypatch.setenv("PANOPTIQUE_DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.delenv("PANOPTIQUE_SYNC_DATABASE_URL", raising=False)
    assert get_sync_database_url() == "postgresql+psycopg://u:p@localhost/db"


def test_mask_database_url_hides_password() -> None:
    assert mask_database_url("postgresql://user:secret@localhost/db") == "postgresql://user:***@localhost/db"


def test_table_sql_contains_timescale_core_tables() -> None:
    sql = "\n".join(PANOPTIQUE_TABLES_SQL)
    for name in ["markets", "orderbook_snapshots", "shadow_predictions", "crowd_flow_observations"]:
        assert f"CREATE TABLE IF NOT EXISTS {name}" in sql
