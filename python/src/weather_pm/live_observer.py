"""One-shot weather live-observer runner.

The runner is intentionally conservative and paper-only.  Fixture mode exercises
snapshot/storage without network I/O.  Live mode is bounded to public read-only
Polymarket data and only writes paper-only observation rows when the collection
master switch is explicitly active.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import time
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from panoptique.live_observer_storage import LiveObserverStorageResult, write_live_observer_rows
from weather_pm.live_observer_config import LiveObserverConfig
from weather_pm.live_observer_snapshots import (
    CompactMarketSnapshot,
    FollowedAccountTradeTrigger,
    ForecastSourceSnapshot,
    WeatherBinSurfaceSnapshot,
)
from weather_pm.market_parser import parse_market_question
from weather_pm.polymarket_client import list_weather_markets as _list_weather_markets

_DATA_API_BASE_URL = "https://data-api.polymarket.com"
_DEFAULT_DATA_API_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class LiveObserverRunSummary:
    scenario: str
    source: str
    dry_run: bool
    collection_enabled: bool
    collection_active: bool
    paper_only: bool
    live_order_allowed: bool
    snapshots: Mapping[str, int]
    storage_results: Mapping[str, Mapping[str, Any]]
    errors: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "source": self.source,
            "dry_run": self.dry_run,
            "collection_enabled": self.collection_enabled,
            "collection_active": self.collection_active,
            "paper_only": self.paper_only,
            "live_order_allowed": self.live_order_allowed,
            "snapshots": dict(self.snapshots),
            "storage_results": {name: dict(result) for name, result in self.storage_results.items()},
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class LiveObserverFastCollectorSummary:
    """Summary for the non-reporting fast/event-trigger observer loop."""

    scenario: str
    source: str
    dry_run: bool
    mode: str
    report_delivery: str
    poll_interval_seconds: int
    iterations: int
    paper_only: bool
    live_order_allowed: bool
    snapshots_total: Mapping[str, int]
    runs: Sequence[Mapping[str, Any]]
    errors: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "source": self.source,
            "dry_run": self.dry_run,
            "mode": self.mode,
            "report_delivery": self.report_delivery,
            "poll_interval_seconds": self.poll_interval_seconds,
            "iterations": self.iterations,
            "paper_only": self.paper_only,
            "live_order_allowed": self.live_order_allowed,
            "snapshots_total": dict(self.snapshots_total),
            "runs": [dict(run) for run in self.runs],
            "errors": list(self.errors),
        }


def list_weather_markets(*, source: str, limit: int) -> list[dict[str, Any]]:
    """Read-only market adapter kept patchable for observer tests."""

    return _list_weather_markets(source=source, limit=limit)


def list_followed_account_trades(
    *,
    accounts: Sequence[str],
    limit: int,
    after_timestamp: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch public, read-only Polymarket account trades for followed accounts.

    Uses the unauthenticated data-api trade feed.  This returns observation
    events only; it never signs, places, cancels, or prepares live orders.
    """

    if not accounts or limit <= 0:
        return []
    rows: list[dict[str, Any]] = []
    seen_accounts = [str(account).strip() for account in accounts if str(account).strip()]
    for account in seen_accounts:
        params: dict[str, Any] = {"limit": max(int(limit), 1)}
        if account.startswith("0x"):
            params["user"] = account
        else:
            params["userName"] = account
        if after_timestamp is not None:
            params["after"] = int(after_timestamp)
        try:
            payload = _fetch_data_api_json("/trades", params=params)
        except RuntimeError:
            continue
        if not isinstance(payload, list):
            continue
        for item in payload:
            if isinstance(item, dict):
                rows.append(item)
        if len(rows) >= limit:
            break
    return rows[:limit]


def _fetch_data_api_json(path: str, *, params: Mapping[str, Any]) -> Any:
    query = urlencode({key: value for key, value in params.items() if value is not None}, doseq=True)
    url = f"{_DATA_API_BASE_URL}{path}"
    if query:
        url = f"{url}?{query}"
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "weather-pm/0.1"},
    )
    try:
        with urlopen(request, timeout=_DEFAULT_DATA_API_TIMEOUT_SECONDS) as response:
            payload = response.read().decode("utf-8")
    except Exception as exc:  # pragma: no cover - network failures are summarized by caller
        raise RuntimeError(f"Polymarket data-api request failed for {url}: {exc}") from exc
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise RuntimeError(f"Polymarket data-api returned invalid JSON for {url}") from exc


def run_live_observer_fast_collector(
    config: LiveObserverConfig,
    *,
    source: str = "live",
    dry_run: bool = False,
    max_iterations: int = 1,
    poll_interval_seconds: int | None = None,
) -> LiveObserverFastCollectorSummary:
    """Run the fast/event-trigger collector without producing operator reports.

    This loop is for frequent blind-spot capture only.  Routine human reports stay
    with the slower cron/reporting path, so this function never writes report or
    manifest artifacts by itself.
    """

    if max_iterations < 1:
        raise ValueError("max_iterations must be >= 1")
    interval = config.active.trade_trigger_poll_interval_seconds if poll_interval_seconds is None else poll_interval_seconds
    runs: list[Mapping[str, Any]] = []
    snapshots_total: dict[str, int] = {}
    errors: list[dict[str, str]] = []
    for index in range(max_iterations):
        run = run_live_observer_once(config, source=source, dry_run=dry_run).to_dict()
        runs.append(run)
        for stream_name, count in (run.get("snapshots") or {}).items():
            snapshots_total[stream_name] = snapshots_total.get(stream_name, 0) + int(count)
        errors.extend(run.get("errors") or [])
        if index + 1 < max_iterations and interval > 0:
            time.sleep(interval)
    return LiveObserverFastCollectorSummary(
        scenario=config.active_scenario,
        source=source,
        dry_run=dry_run,
        mode="fast_collector",
        report_delivery="none",
        poll_interval_seconds=interval,
        iterations=max_iterations,
        paper_only=config.safety.paper_only,
        live_order_allowed=config.safety.live_order_allowed,
        snapshots_total=snapshots_total,
        runs=runs,
        errors=errors,
    )


def run_live_observer_once(
    config: LiveObserverConfig,
    *,
    source: str = "fixture",
    dry_run: bool = False,
) -> LiveObserverRunSummary:
    """Run one bounded, paper-only live-observer collection pass."""

    errors: list[dict[str, str]] = []
    if source not in {"fixture", "live"}:
        raise ValueError("source must be 'fixture' or 'live'")

    if not config.live_collection_active and not (source == "fixture" and dry_run):
        return _summary(
            config,
            source=source,
            dry_run=dry_run,
            errors=[_error("collection_disabled", "collection master switch is off; no collection attempted")],
        )

    rows_by_stream = _live_rows(config, source=source) if source == "live" else _fixture_rows(config)
    snapshots = {name: len(rows) for name, rows in rows_by_stream.items() if rows}
    storage_results: dict[str, Mapping[str, Any]] = {}
    for stream_name, rows in rows_by_stream.items():
        if not rows:
            continue
        try:
            if dry_run or not config.storage.enabled:
                storage_results[stream_name] = _dry_run_storage_result(
                    stream_name,
                    len(rows),
                    dry_run=dry_run or not config.storage.enabled,
                )
            else:
                result = write_live_observer_rows(
                    config,
                    backend=config.storage.primary,
                    stream_name=stream_name,
                    rows=rows,
                )
                storage_results[stream_name] = result.to_dict()
        except Exception as exc:  # pragma: no cover - defensive summary path
            errors.append(_error("storage_error", f"{stream_name}: {exc}"))
            storage_results[stream_name] = _dry_run_storage_result(stream_name, 0, dry_run=True, status="error")

    return _summary(
        config,
        source=source,
        dry_run=dry_run,
        snapshots=snapshots,
        storage_results=storage_results,
        errors=errors,
    )


def _summary(
    config: LiveObserverConfig,
    *,
    source: str,
    dry_run: bool,
    snapshots: Mapping[str, int] | None = None,
    storage_results: Mapping[str, Mapping[str, Any]] | None = None,
    errors: list[dict[str, str]] | None = None,
) -> LiveObserverRunSummary:
    return LiveObserverRunSummary(
        scenario=config.active_scenario,
        source=source,
        dry_run=dry_run,
        collection_enabled=config.collection.enabled,
        collection_active=config.live_collection_active,
        paper_only=config.safety.paper_only,
        live_order_allowed=config.safety.live_order_allowed,
        snapshots=snapshots or {},
        storage_results=storage_results or {},
        errors=errors or [],
    )


def _live_rows(config: LiveObserverConfig, *, source: str) -> dict[str, list[Any]]:
    observed_at = datetime.now(UTC)
    rows: dict[str, list[Any]] = {}
    if _stream_enabled(config, "market_snapshots"):
        markets = list_weather_markets(source=source, limit=config.active.market_limit)
        compact_rows = _market_snapshot_rows(markets, observed_at=observed_at, source=source)
        if compact_rows:
            rows["compact_market_snapshot"] = compact_rows
    if _stream_enabled(config, "account_trades"):
        accounts = _enabled_followed_accounts(config)[: config.active.followed_account_limit]
        if accounts:
            triggers = _followed_account_trade_rows(
                list_followed_account_trades(accounts=accounts, limit=config.active.followed_account_limit),
                observed_at=observed_at,
            )
            if triggers:
                rows["followed_account_trade_trigger"] = triggers
    return rows


def _market_snapshot_rows(markets: Sequence[Mapping[str, Any]], *, observed_at: datetime, source: str) -> list[CompactMarketSnapshot]:
    rows: list[CompactMarketSnapshot] = []
    for market in markets:
        question = str(market.get("question") or "").strip()
        if not question:
            continue
        try:
            structure = parse_market_question(question)
        except ValueError:
            continue
        market_id = str(market.get("id") or market.get("market_id") or market.get("condition_id") or "").strip()
        if not market_id:
            continue
        rows.append(
            CompactMarketSnapshot(
                observed_at=_parse_datetime(market.get("observed_at")) or observed_at,
                market_id=market_id,
                event_id=str(market.get("event_id") or market.get("eventId") or market.get("event_slug") or ""),
                slug=str(market.get("slug") or market_id),
                question=question,
                city=structure.city,
                metric=_metric_name(structure.measurement_kind, structure.unit),
                target_date=structure.date_local or "unknown",
                best_bid=_optional_float(market.get("best_bid") or market.get("bestBid")),
                best_ask=_optional_float(market.get("best_ask") or market.get("bestAsk")),
                last_trade_price=_optional_float(market.get("last_trade_price") or market.get("lastTradePrice") or market.get("yes_price")),
                volume=_optional_float(market.get("volume") or market.get("volume_usd") or market.get("volumeNum")),
                liquidity=_optional_float(market.get("liquidity") or market.get("liquidityClob")),
                open_interest=_optional_float(market.get("open_interest") or market.get("openInterest")),
                active=_optional_bool(market.get("active")),
                closed=_optional_bool(market.get("closed")),
                metadata={"source": "live_gamma_public" if source == "live" else source},
            )
        )
    return rows


def _followed_account_trade_rows(trades: Sequence[Mapping[str, Any]], *, observed_at: datetime) -> list[FollowedAccountTradeTrigger]:
    rows: list[FollowedAccountTradeTrigger] = []
    seen: set[str] = set()
    for trade in trades:
        title = str(trade.get("title") or trade.get("question") or trade.get("market") or "")
        slug = str(trade.get("slug") or trade.get("eventSlug") or trade.get("event_slug") or "")
        if title and not _looks_like_weather_trade(title, slug):
            continue
        account = str(
            trade.get("account")
            or trade.get("handle")
            or trade.get("userName")
            or trade.get("name")
            or trade.get("wallet")
            or trade.get("proxyWallet")
            or ""
        ).strip()
        wallet = str(trade.get("proxyWallet") or trade.get("wallet") or "").strip()
        market_id = str(
            trade.get("market_id")
            or trade.get("marketId")
            or trade.get("condition_id")
            or trade.get("conditionId")
            or ""
        ).strip()
        tx_hash = str(trade.get("transaction_hash") or trade.get("transactionHash") or trade.get("tx_hash") or "").strip()
        if not (account and market_id and tx_hash):
            continue
        dedupe_key = f"{tx_hash}:{market_id}:{wallet or account}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        rows.append(
            FollowedAccountTradeTrigger(
                observed_at=_parse_datetime(trade.get("observed_at") or trade.get("timestamp")) or observed_at,
                account=account,
                profile_id=str(trade.get("profile_id") or _profile_id_for_account(account)),
                transaction_hash=tx_hash,
                market_id=market_id,
                event_id=str(trade.get("event_id") or trade.get("eventId") or trade.get("eventSlug"))
                if trade.get("event_id") or trade.get("eventId") or trade.get("eventSlug")
                else None,
                side=str(trade.get("side") or trade.get("outcome") or "unknown").lower(),
                price=float(trade.get("price") or 0.0),
                size=float(trade.get("size") or trade.get("shares") or 0.0),
                paper_decision=str(trade.get("paper_decision") or "capture_rich_snapshot"),
                metadata={
                    "source": "polymarket_public_trades",
                    "dedupe_key": dedupe_key,
                    "wallet": wallet or None,
                    "title": title or None,
                    "slug": slug or None,
                },
            )
        )
    return rows


def _looks_like_weather_trade(title: str, slug: str = "") -> bool:
    text = f"{title} {slug}".lower()
    tokens = ("weather", "temperature", "highest temperature", "lowest temperature", "degrees", "fahrenheit", "celsius")
    if any(token in text for token in tokens):
        return True
    try:
        parse_market_question(title)
    except ValueError:
        return False
    return True


def _fixture_rows(config: LiveObserverConfig) -> dict[str, list[Any]]:
    observed_at = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    rows: dict[str, list[Any]] = {}
    if _stream_enabled(config, "market_snapshots"):
        rows["compact_market_snapshot"] = [
            CompactMarketSnapshot(
                observed_at=observed_at,
                market_id="fixture-weather-market-1",
                event_id="fixture-weather-event-1",
                slug="fixture-nyc-high-temp-2026-01-02",
                question="Will NYC high temperature exceed 50F on Jan 2, 2026?",
                city="New York",
                metric="high_temperature_f",
                target_date="2026-01-02",
                best_bid=0.48,
                best_ask=0.52,
                last_trade_price=0.50,
                volume=1000.0,
                liquidity=500.0,
                active=True,
                closed=False,
                metadata={"source": "fixture"},
            )
        ]
    if _stream_enabled(config, "bin_surfaces"):
        rows["weather_bin_surface_snapshot"] = [
            WeatherBinSurfaceSnapshot(
                observed_at=observed_at,
                market_id="fixture-weather-market-1",
                event_id="fixture-weather-event-1",
                city="New York",
                metric="high_temperature_f",
                target_date="2026-01-02",
                bins=[{"label": "over_50f", "probability": 0.5}],
                source_market_ids=["fixture-weather-market-1"],
                surface_version="fixture-v1",
            )
        ]
    if _stream_enabled(config, "forecasts"):
        rows["forecast_source_snapshot"] = [
            ForecastSourceSnapshot(
                observed_at=observed_at,
                source="fixture_forecast",
                city="New York",
                metric="high_temperature_f",
                target_date="2026-01-02",
                forecast_value=51.0,
                forecast_units="F",
                issued_at=observed_at,
                source_uri="fixture://weather/nyc/high/2026-01-02",
            )
        ]
    if _stream_enabled(config, "account_trades"):
        rows["followed_account_trade_trigger"] = [
            FollowedAccountTradeTrigger(
                observed_at=observed_at,
                account="ColdMath",
                profile_id="shadow_coldmath_v0",
                transaction_hash="fixture-tx-1",
                market_id="fixture-weather-market-1",
                side="yes",
                price=0.50,
                size=10.0,
            )
        ]
    return rows


def _enabled_followed_accounts(config: LiveObserverConfig) -> list[str]:
    return [name for name, toggle in config.followed_accounts.items() if toggle.enabled]


def _profile_id_for_account(account: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in account).strip("_") or "account"
    return f"shadow_{safe}_v0"


def _metric_name(measurement_kind: str, unit: str) -> str:
    prefix = {"high": "high_temperature", "low": "low_temperature", "current": "current_temperature"}.get(measurement_kind, "temperature")
    return f"{prefix}_{unit.lower()}"


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return bool(value)


def _dry_run_storage_result(stream_name: str, row_count: int, *, dry_run: bool, status: str = "dry_run") -> dict[str, Any]:
    return LiveObserverStorageResult(
        backend="dry_run",
        requested_backend="dry_run",
        status=status,
        path_or_uri=None,
        row_count=row_count,
        paper_only=True,
        dry_run=dry_run,
        stream_name=stream_name,
        created_at=datetime.now(UTC),
        message="no rows persisted",
    ).to_dict()


def _stream_enabled(config: LiveObserverConfig, name: str) -> bool:
    toggle = config.streams.get(name)
    return True if toggle is None else bool(toggle.enabled)


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}
