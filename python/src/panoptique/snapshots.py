from __future__ import annotations

"""Read-only Panoptique snapshot ingestion helpers.

Audit notes for Phase 2 reuse:
- ``weather_pm.polymarket_live`` already contains bounded, no-credential Gamma
  fetch helpers (``_fetch_gamma_json``, ``_fetch_gamma_markets``) and CLOB book
  fetch helpers (``_fetch_clob_json``, ``_fetch_clob_book``), plus robust parsing
  for Gamma's JSON-ish list fields such as ``outcomes`` and ``clobTokenIds``.
- ``weather_pm.polymarket_client`` exposes the higher-level weather fixture/live
  adapter used by existing operator code.  Phase 2 keeps those modules unchanged
  and reuses their fetch paths only at the CLI boundary; normalization here stays
  pure and fixture-testable.
- This module is observation-only: it never imports wallet code and never places
  orders.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlencode

from .artifacts import JsonlArtifactWriter
from .contracts import IngestionHealth, MarketSnapshot, OrderbookSnapshot, SCHEMA_VERSION

JsonDict = dict[str, Any]
_DEFAULT_OUTPUT_DIR = Path("/home/jul/prediction_core/data/panoptique/snapshots")
_GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
_CLOB_BOOK_URL = "https://clob.polymarket.com/book"


@dataclass(frozen=True)
class SnapshotRunResult:
    command: str
    source: str
    status: str
    count: int
    artifact_path: Path
    report_path: Path
    db_status: str
    ingestion_health: IngestionHealth
    errors: list[str]


def _timestamp_id(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _as_float(value: Any, default: float | None = 0.0) -> float | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.lower() in {"null", "none", "n/a"}:
            return default
        try:
            return float(stripped)
        except ValueError:
            return default
    return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    if value is None:
        return default
    return bool(value)


def _jsonish_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.lower() in {"null", "none", "n/a"}:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _normalize_levels(levels: Any) -> list[dict[str, float]]:
    normalized: list[dict[str, float]] = []
    for level in _jsonish_list(levels):
        if not isinstance(level, dict):
            continue
        price = _as_float(level.get("price"), 0.0) or 0.0
        size = _as_float(level.get("size", level.get("quantity")), 0.0) or 0.0
        if price > 0.0 and size > 0.0:
            normalized.append({"price": price, "size": size})
    return normalized


def _market_id(raw: JsonDict) -> str:
    return str(raw.get("id") or raw.get("conditionId") or raw.get("condition_id") or raw.get("slug") or "").strip()


def _yes_index(raw: JsonDict) -> int:
    outcomes = [str(item).strip().lower() for item in _jsonish_list(raw.get("outcomes"))]
    for idx, outcome in enumerate(outcomes):
        if outcome in {"yes", "true"} or outcome.startswith("yes"):
            return idx
    return 0


def _pick_indexed(raw: JsonDict, key: str, index: int) -> Any:
    values = _jsonish_list(raw.get(key))
    return values[index] if index < len(values) else None


def normalize_gamma_market_snapshot(raw: JsonDict, *, observed_at: datetime, source: str) -> MarketSnapshot:
    """Normalize a Gamma/weather_pm market payload into a MarketSnapshot contract."""
    if not isinstance(raw, dict):
        raise TypeError("Gamma market payload must be an object")
    market_id = _market_id(raw)
    if not market_id:
        raise ValueError("Gamma market payload is missing market id")
    yes_idx = _yes_index(raw)
    token_ids = [str(token).strip() for token in _jsonish_list(raw.get("clobTokenIds") or raw.get("clob_token_ids") or raw.get("tokenIds") or raw.get("token_ids")) if str(token).strip()]
    prices = _jsonish_list(raw.get("outcomePrices") or raw.get("outcome_prices"))
    yes_price = _as_float(prices[yes_idx], None) if yes_idx < len(prices) else _as_float(raw.get("yes_price") or raw.get("lastTradePrice") or raw.get("price"), None)
    best_bid = _as_float(raw.get("bestBid", raw.get("best_bid", raw.get("bid"))), None)
    best_ask = _as_float(raw.get("bestAsk", raw.get("best_ask", raw.get("ask"))), None)
    volume = _as_float(raw.get("volumeNum", raw.get("volume", raw.get("volume_usd"))), None)
    liquidity = _as_float(raw.get("liquidityClob", raw.get("liquidity")), None)
    return MarketSnapshot(
        snapshot_id=f"market-{market_id}-{_timestamp_id(observed_at)}",
        market_id=market_id,
        slug=str(raw.get("slug") or market_id),
        question=str(raw.get("question") or raw.get("title") or ""),
        source=source,
        observed_at=observed_at,
        active=_as_bool(raw.get("active"), True),
        closed=_as_bool(raw.get("closed"), False),
        yes_price=yes_price,
        best_bid=best_bid,
        best_ask=best_ask,
        volume=volume,
        liquidity=liquidity,
        token_ids=token_ids,
        raw=dict(raw),
    )


def normalize_clob_orderbook_snapshot(raw: JsonDict, *, market_id: str, token_id: str, observed_at: datetime, source: str) -> OrderbookSnapshot:
    """Normalize a CLOB /book payload into an OrderbookSnapshot contract."""
    if not isinstance(raw, dict):
        raise TypeError("CLOB orderbook payload must be an object")
    return OrderbookSnapshot(
        snapshot_id=f"orderbook-{market_id}-{token_id}-{_timestamp_id(observed_at)}",
        market_id=str(market_id),
        token_id=str(token_id),
        observed_at=observed_at,
        bids=_normalize_levels(raw.get("bids")),
        asks=_normalize_levels(raw.get("asks")),
        raw={**dict(raw), "source": source},
    )


def gamma_markets_request_url(*, limit: int, active: bool = True, closed: bool = False) -> str:
    return f"{_GAMMA_MARKETS_URL}?{urlencode({'limit': max(int(limit), 1), 'active': str(active).lower(), 'closed': str(closed).lower()})}"


def clob_book_request_url(token_id: str) -> str:
    return f"{_CLOB_BOOK_URL}?{urlencode({'token_id': token_id})}"


def _default_market_fetcher(*, limit: int) -> list[JsonDict]:
    from weather_pm import polymarket_live

    return polymarket_live._fetch_gamma_markets(limit=limit, active=True, closed=False)  # noqa: SLF001 - audited Phase 2 fetch reuse


def _default_orderbook_fetcher(token_id: str) -> JsonDict:
    from weather_pm import polymarket_live

    return polymarket_live._fetch_clob_book(token_id)  # noqa: SLF001 - audited Phase 2 fetch reuse


def _health(command: str, source: str, fetched_at: datetime, status: str, detail: str | None, metrics: JsonDict) -> IngestionHealth:
    return IngestionHealth(
        health_id=f"{command}-{source}-{_timestamp_id(fetched_at)}",
        source=source,
        checked_at=fetched_at,
        status=status,
        detail=detail,
        metrics=metrics,
    )


def _write_report(output_dir: Path, *, command: str, source: str, fetched_at: datetime, status: str, count: int, artifact_path: Path, db_status: str, errors: list[str]) -> Path:
    report = render_snapshot_report(
        command=command,
        source=source,
        fetched_at=fetched_at,
        status=status,
        count=count,
        artifact_path=artifact_path,
        db_status=db_status,
        errors=errors,
    )
    path = output_dir / f"{command}-{source}-{_timestamp_id(fetched_at)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return path


def _persist_health(repository: Any | None, health: IngestionHealth) -> None:
    if repository is not None and hasattr(repository, "insert_ingestion_health"):
        repository.insert_ingestion_health(health)


def run_market_snapshot(
    *,
    source: str = "live",
    limit: int,
    output_dir: str | Path = _DEFAULT_OUTPUT_DIR,
    fetched_at: datetime | None = None,
    market_fetcher: Callable[..., Iterable[JsonDict]] | None = None,
    repository: Any | None = None,
    request_url: str | None = None,
) -> SnapshotRunResult:
    if int(limit) < 1:
        raise ValueError("snapshot-markets requires --limit >= 1")
    limit = int(limit)
    fetched_at = fetched_at or datetime.now(UTC)
    output_path = Path(output_dir)
    artifact_path = output_path / f"snapshot-markets-{source}-{_timestamp_id(fetched_at)}.jsonl"
    request_url = request_url or gamma_markets_request_url(limit=limit)
    fetcher = market_fetcher or _default_market_fetcher
    db_status = "skipped_unavailable" if repository is None else "inserted"
    errors: list[str] = []
    rows: list[JsonDict] = []
    snapshots: list[MarketSnapshot] = []
    status = "ok"
    detail: str | None = None
    try:
        raw_markets = list(fetcher(limit=limit))[:limit]
        for raw in raw_markets:
            snapshot = normalize_gamma_market_snapshot(raw, observed_at=fetched_at, source=source)
            snapshots.append(snapshot)
            if repository is not None:
                repository.insert_market_snapshot(snapshot)
    except Exception as exc:  # keep live collection failure auditable
        status = "error"
        detail = str(exc)
        errors.append(str(exc))

    health = _health("snapshot-markets", source, fetched_at, status, detail, {"count": len(snapshots), "limit": limit, "db_status": db_status})
    if status == "ok":
        for snapshot in snapshots:
            rows.append({
                "metadata": {
                    "source": source,
                    "fetched_at": fetched_at.isoformat(),
                    "request_url": request_url,
                    "schema_version": SCHEMA_VERSION,
                    "db_status": db_status,
                },
                "snapshot_type": "market",
                "snapshot": snapshot.to_record(),
                "ingestion_health": health.to_record(),
            })
    else:
        rows.append({
            "metadata": {"source": source, "fetched_at": fetched_at.isoformat(), "request_url": request_url, "schema_version": SCHEMA_VERSION, "db_status": db_status},
            "snapshot_type": "market",
            "snapshot": None,
            "ingestion_health": health.to_record(),
        })
    _persist_health(repository, health)
    JsonlArtifactWriter(artifact_path, source=source, artifact_type="panoptique_snapshot").write_many(rows)
    report_path = _write_report(output_path, command="snapshot-markets", source=source, fetched_at=fetched_at, status=status, count=len(snapshots), artifact_path=artifact_path, db_status=db_status, errors=errors)
    return SnapshotRunResult("snapshot-markets", source, status, len(snapshots), artifact_path, report_path, db_status, health, errors)


def run_orderbook_snapshot(
    *,
    token_id: str,
    market_id: str = "unknown",
    source: str = "live",
    output_dir: str | Path = _DEFAULT_OUTPUT_DIR,
    fetched_at: datetime | None = None,
    orderbook_fetcher: Callable[[str], JsonDict] | None = None,
    repository: Any | None = None,
    request_url: str | None = None,
) -> SnapshotRunResult:
    if not str(token_id).strip():
        raise ValueError("snapshot-orderbook requires --token-id")
    token_id = str(token_id).strip()
    market_id = str(market_id or "unknown")
    fetched_at = fetched_at or datetime.now(UTC)
    output_path = Path(output_dir)
    artifact_path = output_path / f"snapshot-orderbook-{source}-{token_id}-{_timestamp_id(fetched_at)}.jsonl"
    request_url = request_url or clob_book_request_url(token_id)
    fetcher = orderbook_fetcher or _default_orderbook_fetcher
    db_status = "skipped_unavailable" if repository is None else "inserted"
    errors: list[str] = []
    snapshot: OrderbookSnapshot | None = None
    status = "ok"
    detail: str | None = None
    try:
        raw = fetcher(token_id)
        snapshot = normalize_clob_orderbook_snapshot(raw, market_id=market_id, token_id=token_id, observed_at=fetched_at, source=source)
        if repository is not None:
            repository.insert_orderbook_snapshot(snapshot)
    except Exception as exc:
        status = "error"
        detail = str(exc)
        errors.append(str(exc))
    count = 1 if snapshot is not None else 0
    health = _health("snapshot-orderbook", source, fetched_at, status, detail, {"count": count, "db_status": db_status, "token_id": token_id})
    _persist_health(repository, health)
    rows = [{
        "metadata": {"source": source, "fetched_at": fetched_at.isoformat(), "request_url": request_url, "schema_version": SCHEMA_VERSION, "db_status": db_status},
        "snapshot_type": "orderbook",
        "snapshot": snapshot.to_record() if snapshot is not None else None,
        "ingestion_health": health.to_record(),
    }]
    JsonlArtifactWriter(artifact_path, source=source, artifact_type="panoptique_snapshot").write_many(rows)
    report_path = _write_report(output_path, command="snapshot-orderbook", source=source, fetched_at=fetched_at, status=status, count=count, artifact_path=artifact_path, db_status=db_status, errors=errors)
    return SnapshotRunResult("snapshot-orderbook", source, status, count, artifact_path, report_path, db_status, health, errors)


def render_snapshot_report(*, command: str, source: str, fetched_at: datetime, status: str, count: int, artifact_path: Path, db_status: str, errors: list[str]) -> str:
    lines = [
        "# Panoptique Snapshot Run",
        "",
        "Snapshot run read-only observation report; no wallet access and no trading actions.",
        "",
        f"- Command: `{command}`",
        f"- Source: `{source}`",
        f"- Fetched at: `{fetched_at.isoformat()}`",
        f"- Status: `{status}`",
        f"- Normalized snapshots: `{count}`",
        f"- Artifact: `{artifact_path}`",
        f"- DB status: `{db_status}`",
        "- Safety: No real orders were placed.",
    ]
    if errors:
        lines.extend(["", "## Errors"])
        lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines) + "\n"
