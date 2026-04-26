from __future__ import annotations

from datetime import datetime
import json
import sqlite3
from typing import Any, Iterable

from .contracts import CrowdFlowObservation, IngestionHealth, Market, MarketSnapshot, OrderbookSnapshot, ShadowPrediction

PANOPTIQUE_TABLES_SQL = [
    """
    CREATE TABLE IF NOT EXISTS markets (
        market_id TEXT PRIMARY KEY,
        slug TEXT NOT NULL,
        question TEXT NOT NULL,
        source TEXT NOT NULL,
        active BOOLEAN NOT NULL,
        closed BOOLEAN NOT NULL,
        created_at TEXT,
        raw JSONB NOT NULL,
        schema_version TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS orderbook_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        market_id TEXT NOT NULL,
        token_id TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        bids JSONB NOT NULL,
        asks JSONB NOT NULL,
        raw JSONB NOT NULL,
        schema_version TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS market_price_snapshots (
        snapshot_id TEXT PRIMARY KEY,
        market_id TEXT NOT NULL,
        slug TEXT NOT NULL,
        question TEXT NOT NULL,
        source TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        active BOOLEAN NOT NULL,
        closed BOOLEAN NOT NULL,
        yes_price REAL,
        best_bid REAL,
        best_ask REAL,
        volume REAL,
        liquidity REAL,
        token_ids JSONB NOT NULL,
        raw JSONB NOT NULL,
        schema_version TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS shadow_predictions (
        prediction_id TEXT PRIMARY KEY,
        market_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        horizon_seconds INTEGER NOT NULL,
        predicted_crowd_direction TEXT NOT NULL,
        confidence REAL NOT NULL,
        rationale TEXT NOT NULL,
        features JSONB NOT NULL,
        schema_version TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crowd_flow_observations (
        observation_id TEXT PRIMARY KEY,
        prediction_id TEXT NOT NULL,
        market_id TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        window_seconds INTEGER NOT NULL,
        price_delta REAL NOT NULL,
        volume_delta REAL NOT NULL,
        direction_hit BOOLEAN NOT NULL,
        liquidity_caveat TEXT,
        metrics JSONB NOT NULL,
        schema_version TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ingestion_health (
        health_id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        checked_at TEXT NOT NULL,
        status TEXT NOT NULL,
        detail TEXT,
        metrics JSONB NOT NULL,
        schema_version TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS external_repos (
        repo_id TEXT PRIMARY KEY,
        url TEXT NOT NULL,
        name TEXT,
        raw JSONB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_measurements (
        measurement_id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        metric_value REAL,
        window_seconds INTEGER,
        metrics JSONB NOT NULL,
        schema_version TEXT NOT NULL
    )
    """,
]

_JSON_COLUMNS = {"raw", "bids", "asks", "features", "metrics", "token_ids"}
_BOOL_COLUMNS = {"active", "closed", "direction_hit"}


def connect_sqlite_memory() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _sqlite_sql(sql: str) -> str:
    return sql.replace("JSONB", "TEXT").replace("BOOLEAN", "INTEGER")


def _adapt_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    if isinstance(value, bool):
        return int(value)
    return value


def _decode_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    decoded: dict[str, Any] = {}
    for key in row.keys():
        value = row[key]
        if key in _JSON_COLUMNS and isinstance(value, str):
            decoded[key] = json.loads(value)
        elif key in _BOOL_COLUMNS and value in (0, 1):
            decoded[key] = bool(value)
        else:
            decoded[key] = value
    return decoded


def _decode_rows(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row for row in (_decode_row(row) for row in rows) if row is not None]


class PanoptiqueRepository:
    """Repository write path for Panoptique contracts.

    This implementation is sqlite3-compatible for tests. The same contract records
    map directly to Postgres JSONB tables created by the Alembic migration.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_schema(self) -> None:
        for sql in PANOPTIQUE_TABLES_SQL:
            self.conn.execute(_sqlite_sql(sql))
        self.conn.commit()

    def _insert_or_replace(self, table: str, record: dict[str, Any]) -> None:
        columns = list(record)
        placeholders = ", ".join("?" for _ in columns)
        names = ", ".join(columns)
        values = [_adapt_value(record[col]) for col in columns]
        self.conn.execute(f"INSERT OR REPLACE INTO {table} ({names}) VALUES ({placeholders})", values)
        self.conn.commit()

    def upsert_market(self, market: Market) -> None:
        self._insert_or_replace("markets", market.to_record())

    def get_market(self, market_id: str) -> dict[str, Any] | None:
        return _decode_row(self.conn.execute("SELECT * FROM markets WHERE market_id = ?", (market_id,)).fetchone())

    def insert_orderbook_snapshot(self, snapshot: OrderbookSnapshot) -> None:
        self._insert_or_replace("orderbook_snapshots", snapshot.to_record())

    def insert_market_snapshot(self, snapshot: MarketSnapshot) -> None:
        self._insert_or_replace("market_price_snapshots", snapshot.to_record())

    def list_market_snapshots(self, market_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM market_price_snapshots WHERE market_id = ? ORDER BY observed_at, snapshot_id",
            (market_id,),
        ).fetchall()
        return _decode_rows(rows)

    def insert_ingestion_health(self, health: IngestionHealth) -> None:
        self._insert_or_replace("ingestion_health", health.to_record())

    def list_ingestion_health(self, source: str | None = None) -> list[dict[str, Any]]:
        if source is None:
            rows = self.conn.execute("SELECT * FROM ingestion_health ORDER BY checked_at, health_id").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM ingestion_health WHERE source = ? ORDER BY checked_at, health_id",
                (source,),
            ).fetchall()
        return _decode_rows(rows)

    def list_orderbook_snapshots(self, market_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM orderbook_snapshots WHERE market_id = ? ORDER BY observed_at, snapshot_id",
            (market_id,),
        ).fetchall()
        return _decode_rows(rows)

    def insert_shadow_prediction(self, prediction: ShadowPrediction) -> None:
        self._insert_or_replace("shadow_predictions", prediction.to_record())

    def list_shadow_predictions(self, market_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM shadow_predictions WHERE market_id = ? ORDER BY observed_at, prediction_id",
            (market_id,),
        ).fetchall()
        return _decode_rows(rows)

    def insert_crowd_flow_observation(self, observation: CrowdFlowObservation) -> None:
        self._insert_or_replace("crowd_flow_observations", observation.to_record())

    def list_crowd_flow_observations(self, market_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM crowd_flow_observations WHERE market_id = ? ORDER BY observed_at, observation_id",
            (market_id,),
        ).fetchall()
        return _decode_rows(rows)

    def upsert_external_repo(self, repo: Any) -> None:
        record = repo.to_external_repo_record() if hasattr(repo, "to_external_repo_record") else repo
        self._insert_or_replace("external_repos", record)

    def list_external_repos(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM external_repos ORDER BY name, repo_id").fetchall()
        return _decode_rows(rows)

    def insert_agent_measurement(self, record: dict[str, Any]) -> None:
        self._insert_or_replace("agent_measurements", record)

    def insert_agent_measurements_from_summary(self, summary: Any) -> None:
        from datetime import UTC, datetime
        from .contracts import SCHEMA_VERSION

        observed_at = datetime.now(UTC).isoformat()
        for agent_id, hit_rate in getattr(summary, "hit_rate_by_agent", {}).items():
            self.insert_agent_measurement(
                {
                    "measurement_id": f"agent-measurement-{agent_id}-hit_rate-{observed_at}",
                    "agent_id": agent_id,
                    "observed_at": observed_at,
                    "metric_name": "hit_rate",
                    "metric_value": float(hit_rate),
                    "window_seconds": None,
                    "metrics": {
                        "measurement_target": "crowd_flow_prediction_accuracy",
                        "event_accuracy": "not_measured",
                        "execution_feasibility": "liquidity_caveat_only",
                        "summary": summary.to_dict() if hasattr(summary, "to_dict") else {},
                    },
                    "schema_version": SCHEMA_VERSION,
                }
            )

    def list_agent_measurements(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        if agent_id is None:
            rows = self.conn.execute("SELECT * FROM agent_measurements ORDER BY observed_at, measurement_id").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM agent_measurements WHERE agent_id = ? ORDER BY observed_at, measurement_id",
                (agent_id,),
            ).fetchall()
        return _decode_rows(rows)
