from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from panoptique.contracts import MarketSnapshot
from panoptique.repositories import PanoptiqueRepository, connect_sqlite_memory
from panoptique.snapshots import (
    SnapshotRunResult,
    normalize_gamma_market_snapshot,
    normalize_clob_orderbook_snapshot,
    render_snapshot_report,
    run_market_snapshot,
    run_orderbook_snapshot,
)
from panoptique.artifacts import read_jsonl


OBSERVED_AT = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)


def gamma_market_payload() -> dict:
    return {
        "id": "123",
        "slug": "nyc-rain-apr-26",
        "question": "Will it rain in NYC on April 26?",
        "active": True,
        "closed": False,
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.42", "0.58"]',
        "bestBid": "0.41",
        "bestAsk": "0.43",
        "volumeNum": "12345.67",
        "liquidity": "800.5",
        "clobTokenIds": '["yes-token", "no-token"]',
        "endDate": "2026-04-27T00:00:00Z",
    }


def clob_book_payload() -> dict:
    return {
        "market": "0xcondition",
        "asset_id": "yes-token",
        "bids": [{"price": "0.40", "size": "100"}, {"price": "0", "size": "1"}],
        "asks": [{"price": "0.44", "size": "120"}],
        "hash": "book-hash",
    }


def test_normalize_gamma_market_snapshot_from_fixture_payload() -> None:
    snapshot = normalize_gamma_market_snapshot(gamma_market_payload(), observed_at=OBSERVED_AT, source="fixture")

    assert isinstance(snapshot, MarketSnapshot)
    assert snapshot.snapshot_id == "market-123-20260426T120000Z"
    assert snapshot.market_id == "123"
    assert snapshot.slug == "nyc-rain-apr-26"
    assert snapshot.yes_price == 0.42
    assert snapshot.best_bid == 0.41
    assert snapshot.best_ask == 0.43
    assert snapshot.volume == 12345.67
    assert snapshot.liquidity == 800.5
    assert snapshot.token_ids == ["yes-token", "no-token"]
    assert snapshot.raw["id"] == "123"


def test_normalize_clob_orderbook_snapshot_from_fixture_payload() -> None:
    snapshot = normalize_clob_orderbook_snapshot(
        clob_book_payload(), market_id="123", token_id="yes-token", observed_at=OBSERVED_AT, source="fixture"
    )

    assert snapshot.snapshot_id == "orderbook-123-yes-token-20260426T120000Z"
    assert snapshot.market_id == "123"
    assert snapshot.token_id == "yes-token"
    assert snapshot.bids == [{"price": 0.4, "size": 100.0}]
    assert snapshot.asks == [{"price": 0.44, "size": 120.0}]
    assert snapshot.raw["hash"] == "book-hash"


def test_repository_persists_market_snapshot_and_ingestion_health() -> None:
    conn = connect_sqlite_memory()
    repo = PanoptiqueRepository(conn)
    repo.create_schema()
    market_snapshot = normalize_gamma_market_snapshot(gamma_market_payload(), observed_at=OBSERVED_AT, source="fixture")

    repo.insert_market_snapshot(market_snapshot)
    from panoptique.contracts import IngestionHealth

    repo.insert_ingestion_health(
        IngestionHealth(
            health_id="health-1",
            source="fixture",
            checked_at=OBSERVED_AT,
            status="ok",
            metrics={"db_status": "inserted"},
        )
    )

    rows = repo.list_market_snapshots("123")
    assert rows[0]["snapshot_id"] == market_snapshot.snapshot_id
    assert rows[0]["token_ids"] == ["yes-token", "no-token"]
    assert repo.list_ingestion_health(source="fixture")[0]["status"] == "ok"


def test_snapshot_market_run_writes_raw_artifacts_report_and_db_status(tmp_path: Path) -> None:
    conn = connect_sqlite_memory()
    repo = PanoptiqueRepository(conn)
    repo.create_schema()

    def fetch_markets(*, limit: int):
        assert limit == 1
        return [gamma_market_payload()]

    result = run_market_snapshot(
        source="live",
        limit=1,
        output_dir=tmp_path,
        fetched_at=OBSERVED_AT,
        market_fetcher=fetch_markets,
        repository=repo,
        request_url="https://gamma-api.polymarket.com/markets?limit=1&active=true&closed=false",
    )

    assert isinstance(result, SnapshotRunResult)
    assert result.status == "ok"
    assert result.db_status == "inserted"
    assert result.artifact_path.exists()
    rows = list(read_jsonl(result.artifact_path))
    assert rows[0]["metadata"]["source"] == "live"
    assert rows[0]["metadata"]["request_url"].startswith("https://gamma-api.polymarket.com/markets")
    assert rows[0]["metadata"]["db_status"] == "inserted"
    assert rows[0]["snapshot"]["market_id"] == "123"
    assert "Snapshot run" in result.report_path.read_text(encoding="utf-8")
    assert repo.list_market_snapshots("123")


def test_snapshot_run_without_db_records_explicit_skipped_status(tmp_path: Path) -> None:
    def fetch_markets(*, limit: int):
        return [gamma_market_payload()]

    result = run_market_snapshot(
        source="live",
        limit=1,
        output_dir=tmp_path,
        fetched_at=OBSERVED_AT,
        market_fetcher=fetch_markets,
        repository=None,
        request_url="https://gamma-api.polymarket.com/markets?limit=1",
    )

    assert result.db_status == "skipped_unavailable"
    row = next(read_jsonl(result.artifact_path))
    assert row["metadata"]["db_status"] == "skipped_unavailable"
    assert row["ingestion_health"]["status"] == "ok"
    assert row["ingestion_health"]["metrics"]["db_status"] == "skipped_unavailable"


def test_snapshot_run_network_failure_writes_error_artifact_and_health(tmp_path: Path) -> None:
    def failing_fetcher(*, limit: int):
        raise RuntimeError("network unavailable")

    result = run_market_snapshot(
        source="live",
        limit=2,
        output_dir=tmp_path,
        fetched_at=OBSERVED_AT,
        market_fetcher=failing_fetcher,
        repository=None,
        request_url="https://gamma-api.polymarket.com/markets?limit=2",
    )

    assert result.status == "error"
    assert result.count == 0
    row = next(read_jsonl(result.artifact_path))
    assert row["ingestion_health"]["status"] == "error"
    assert "network unavailable" in row["ingestion_health"]["detail"]


def test_orderbook_run_writes_artifact_and_repository_row(tmp_path: Path) -> None:
    conn = connect_sqlite_memory()
    repo = PanoptiqueRepository(conn)
    repo.create_schema()

    def fetch_book(token_id: str):
        assert token_id == "yes-token"
        return clob_book_payload()

    result = run_orderbook_snapshot(
        token_id="yes-token",
        market_id="123",
        source="live",
        output_dir=tmp_path,
        fetched_at=OBSERVED_AT,
        orderbook_fetcher=fetch_book,
        repository=repo,
        request_url="https://clob.polymarket.com/book?token_id=yes-token",
    )

    assert result.status == "ok"
    assert repo.list_orderbook_snapshots("123")[0]["token_id"] == "yes-token"
    row = next(read_jsonl(result.artifact_path))
    assert row["snapshot"]["bids"][0]["price"] == 0.4
    assert row["metadata"]["request_url"].endswith("yes-token")


def test_render_snapshot_report_is_compact_and_operator_facing() -> None:
    report = render_snapshot_report(
        command="snapshot-markets",
        source="live",
        fetched_at=OBSERVED_AT,
        status="ok",
        count=1,
        artifact_path=Path("/tmp/snapshots.jsonl"),
        db_status="skipped_unavailable",
        errors=[],
    )

    assert "# Panoptique Snapshot Run" in report
    assert "snapshot-markets" in report
    assert "read-only observation" in report
    assert "skipped_unavailable" in report
    assert "No real orders" in report
