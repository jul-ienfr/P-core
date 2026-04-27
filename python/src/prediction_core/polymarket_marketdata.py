from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


_AUTO_WEBSOCKETS_MODULE = object()


@dataclass(frozen=True)
class MarketDataSnapshot:
    token_id: str
    best_bid: float | None
    best_ask: float | None
    spread: float | None
    bid_depth: float
    ask_depth: float
    sequence: int | None = None
    received_at: str | None = None
    source: str = "clob_ws"
    valid: bool = True
    invalid_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MarketDataCache:
    """Small in-memory CLOB book cache for the future hot-path worker.

    This is deliberately network-free: Gamma/Data discovery and CLOB websocket plumbing
    can feed it, while decision code reads deterministic snapshots from memory.
    """

    def __init__(self, *, snapshot_sink: Callable[[MarketDataSnapshot], None] | None = None) -> None:
        self._snapshots: dict[str, MarketDataSnapshot] = {}
        self.snapshot_sink = snapshot_sink

    def update_book(
        self,
        *,
        token_id: str,
        bids: list[dict[str, Any]],
        asks: list[dict[str, Any]],
        sequence: int | None = None,
        received_at: str | None = None,
        source: str = "clob_ws",
    ) -> MarketDataSnapshot:
        normalized_token = str(token_id).strip()
        if not normalized_token:
            raise ValueError("token_id is required")
        previous = self._snapshots.get(normalized_token)
        if previous is not None and previous.sequence is not None:
            if sequence is None:
                raise ValueError("sequence is required after sequenced snapshot")
            if sequence <= previous.sequence:
                raise ValueError("sequence must be newer than previous snapshot")

        bid_levels = _valid_levels(bids)
        ask_levels = _valid_levels(asks)
        best_bid = max((price for price, _size in bid_levels), default=None)
        best_ask = min((price for price, _size in ask_levels), default=None)
        spread = None if best_bid is None or best_ask is None else round(best_ask - best_bid, 10)
        invalid_reason = None
        if best_bid is not None and best_ask is not None and best_bid > best_ask:
            invalid_reason = "crossed_book"
        snapshot = MarketDataSnapshot(
            token_id=normalized_token,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            bid_depth=sum(size for _price, size in bid_levels),
            ask_depth=sum(size for _price, size in ask_levels),
            sequence=sequence,
            received_at=received_at or _utc_now_iso(),
            source=source,
            valid=invalid_reason is None,
            invalid_reason=invalid_reason,
        )
        self._snapshots[normalized_token] = snapshot
        if self.snapshot_sink is not None:
            self.snapshot_sink(snapshot)
        return snapshot

    def snapshot(self, token_id: str) -> MarketDataSnapshot | None:
        return self._snapshots.get(str(token_id).strip())

    def snapshots(self) -> dict[str, dict[str, Any]]:
        return {token_id: snapshot.to_dict() for token_id, snapshot in self._snapshots.items()}


def replay_clob_ws_events(events: list[dict[str, Any]], *, cache: MarketDataCache | None = None, token_ids: list[str] | None = None) -> dict[str, Any]:
    """Replay captured/simulated CLOB websocket events into a read-only cache.

    This is intentionally deterministic and network-free: it lets us validate the hot-path
    event contract before wiring a real long-running websocket worker.
    """
    target_cache = cache if cache is not None else MarketDataCache()
    stats = _empty_marketdata_stats()
    subscribed_tokens = _normalize_token_set(token_ids)

    for index, event in enumerate(events):
        _apply_clob_ws_event(event, cache=target_cache, stats=stats, index=index, subscribed_tokens=subscribed_tokens)

    return {
        "mode": "paper/read-only clob websocket replay",
        **stats,
        "snapshots": target_cache.snapshots(),
    }


async def open_polymarket_clob_ws_stream(
    url: str,
    subscribe_message: dict[str, Any],
    *,
    websockets_module: Any = _AUTO_WEBSOCKETS_MODULE,
    heartbeat_interval_seconds: float | None = 20.0,
) -> AsyncIterator[dict[str, Any]]:
    """Open Polymarket CLOB websocket and yield decoded JSON object events.

    The dependency is optional so the default code path stays install-light. Tests and callers
    can inject a compatible module exposing ``connect(url)``; production use should install the
    ``websockets`` package.
    """
    if websockets_module is _AUTO_WEBSOCKETS_MODULE:
        try:
            import websockets as resolved_websockets_module
        except ImportError as exc:
            raise RuntimeError("websockets package is required for real CLOB websocket streaming") from exc
        websockets_module = resolved_websockets_module
    if websockets_module is None:
        raise RuntimeError("websockets package is required for real CLOB websocket streaming")

    async with websockets_module.connect(url) as websocket:
        await websocket.send(json.dumps(subscribe_message, separators=(",", ":")))
        if heartbeat_interval_seconds is not None and hasattr(websocket, "ping"):
            await websocket.ping()
        async for message in websocket:
            if isinstance(message, bytes):
                message = message.decode("utf-8")
            payload = json.loads(message) if isinstance(message, str) else message
            if isinstance(payload, dict):
                yield payload


async def run_clob_marketdata_stream(
    *,
    token_ids: list[str],
    stream_factory: Callable[[str, dict[str, Any]], AsyncIterator[dict[str, Any]]] = open_polymarket_clob_ws_stream,
    cache: MarketDataCache | None = None,
    max_events: int | None = None,
    url: str = "wss://clob.polymarket.com/ws/market",
    dry_run: bool = False,
    max_reconnects: int = 0,
    reconnect_backoff_seconds: float = 0.25,
    max_reconnect_backoff_seconds: float = 2.0,
    idle_timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Consume CLOB websocket market events into an in-memory read-only cache.

    The websocket transport is injectable on purpose: tests and dry-run CLI paths can feed
    captured events without network access, while a future real daemon can provide an actual
    websocket-backed async iterator.
    """
    normalized_tokens = [str(token).strip() for token in token_ids if str(token).strip()]
    if not normalized_tokens:
        raise ValueError("token_ids is required")
    if max_events is not None and max_events < 1:
        raise ValueError("max_events must be >= 1")
    if max_reconnects < 0:
        raise ValueError("max_reconnects must be >= 0")
    if reconnect_backoff_seconds < 0:
        raise ValueError("reconnect_backoff_seconds must be >= 0")
    if max_reconnect_backoff_seconds < reconnect_backoff_seconds:
        raise ValueError("max_reconnect_backoff_seconds must be >= reconnect_backoff_seconds")
    if idle_timeout_seconds is not None and idle_timeout_seconds <= 0:
        raise ValueError("idle_timeout_seconds must be positive")

    target_cache = cache if cache is not None else MarketDataCache()
    stats = _empty_marketdata_stats()
    subscribe_message = {"type": "market", "assets_ids": normalized_tokens}
    subscribed_tokens = set(normalized_tokens)

    attempts = 0
    while True:
        try:
            stream = stream_factory(url, subscribe_message)
            while True:
                if max_events is not None and stats["received_events"] >= max_events:
                    break
                try:
                    event = await _next_stream_event(stream, idle_timeout_seconds=idle_timeout_seconds)
                except StopAsyncIteration:
                    break
                if event is None:
                    stats["idle_timeouts"] += 1
                    break
                stats["received_events"] += 1
                _apply_clob_ws_event(event, cache=target_cache, stats=stats, index=stats["received_events"] - 1, subscribed_tokens=subscribed_tokens)
        except json.JSONDecodeError as exc:
            stats["invalid_json_events"] += 1
            stats["invalid_events"] += 1
            stats["errors"].append({"index": stats["received_events"], "error": f"invalid_json: {exc.msg}"})
        except Exception as exc:
            stats["stream_errors"] += 1
            stats["errors"].append({"index": stats["received_events"], "error": f"stream_error: {exc}"})

        if max_events is not None and stats["received_events"] >= max_events:
            break
        if attempts >= max_reconnects:
            break
        attempts += 1
        stats["reconnects"] += 1
        backoff = min(max_reconnect_backoff_seconds, reconnect_backoff_seconds * (2 ** (attempts - 1)))
        if backoff > 0:
            await asyncio.sleep(backoff)

    return {
        "mode": "paper/read-only clob websocket stream",
        "dry_run": dry_run,
        "url": url,
        "token_ids": normalized_tokens,
        **stats,
        "snapshots": target_cache.snapshots(),
    }


def select_hot_path_subscriptions(
    markets: list[dict[str, Any]],
    *,
    min_liquidity: float = 0.0,
    max_markets: int | None = None,
) -> list[dict[str, Any]]:
    subscriptions: list[dict[str, Any]] = []
    selected_markets = 0
    for market in markets:
        if max_markets is not None and selected_markets >= max_markets:
            break
        if market.get("closed") is True:
            continue
        liquidity = _coerce_float(market.get("liquidity") or market.get("liquidityNum") or 0.0)
        if liquidity < min_liquidity:
            continue
        market_id = market.get("id") or market.get("market_id")
        token_ids = _coerce_token_ids(market.get("clobTokenIds") or market.get("clob_token_ids"))
        if not isinstance(market_id, str) or not market_id.strip() or not token_ids:
            continue
        selected_markets += 1
        for index, token_id in enumerate(token_ids):
            subscriptions.append({"market_id": market_id.strip(), "token_id": token_id, "outcome_index": index})
    return subscriptions


def build_marketdata_worker_plan(*, discovery_interval_seconds: int = 60, max_hot_markets: int = 50) -> dict[str, Any]:
    if discovery_interval_seconds < 1:
        raise ValueError("discovery_interval_seconds must be >= 1")
    if max_hot_markets < 1:
        raise ValueError("max_hot_markets must be >= 1")
    return {
        "mode": "paper/read-only marketdata scaffold",
        "discovery_interval_seconds": discovery_interval_seconds,
        "max_hot_markets": max_hot_markets,
        "workers": {
            "discovery_worker": {
                "api": "Gamma API",
                "hot_path": False,
                "role": "refresh market metadata, rules, resolutionSource, and clobTokenIds into a local cache",
            },
            "marketdata_worker": {
                "api": "CLOB WebSocket",
                "hot_path": True,
                "role": "maintain best bid/ask, spread, depth, and sequence in memory for subscribed token ids",
            },
            "decision_worker": {
                "api": "local cache",
                "hot_path": True,
                "role": "score edge from cached marketdata and cached external signals without blocking on Gamma/Data",
            },
            "execution_worker": {
                "api": "CLOB REST",
                "hot_path": True,
                "role": "future authenticated order placement/cancel path; disabled in this scaffold",
            },
            "analytics_worker": {
                "api": "Data API",
                "hot_path": False,
                "role": "batch historical trades, wallets, and post-trade analytics outside the live decision loop",
            },
        },
    }


async def dry_run_jsonl_stream_factory(url: str, subscribe_message: dict[str, Any], *, path: str) -> AsyncIterator[dict[str, Any]]:
    """Yield websocket-like events from JSONL; ignores url/subscription except for API parity."""
    del url, subscribe_message
    with open(path, encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                raise ValueError(f"line {line_number} must be a JSON object")
            yield payload


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def _next_stream_event(stream: AsyncIterator[dict[str, Any]], *, idle_timeout_seconds: float | None) -> dict[str, Any] | None:
    if idle_timeout_seconds is None:
        return await anext(stream)
    try:
        return await asyncio.wait_for(anext(stream), timeout=idle_timeout_seconds)
    except TimeoutError:
        return None


def _empty_marketdata_stats() -> dict[str, Any]:
    return {
        "received_events": 0,
        "processed_events": 0,
        "ignored_events": 0,
        "unsubscribed_events": 0,
        "invalid_events": 0,
        "invalid_json_events": 0,
        "sequence_rejected_events": 0,
        "stale_events": 0,
        "idle_timeouts": 0,
        "stream_errors": 0,
        "reconnects": 0,
        "errors": [],
    }


def _apply_clob_ws_event(
    event: dict[str, Any],
    *,
    cache: MarketDataCache,
    stats: dict[str, Any],
    index: int,
    subscribed_tokens: set[str] | None = None,
) -> None:
    event_type = event.get("event_type") or event.get("type")
    if event_type not in {"book", "price_change"}:
        stats["ignored_events"] += 1
        return

    token_id = str(event.get("asset_id") or event.get("token_id") or event.get("token") or "").strip()
    if subscribed_tokens is not None and token_id not in subscribed_tokens:
        stats["ignored_events"] += 1
        stats["unsubscribed_events"] += 1
        return
    if event_type == "price_change" and (not isinstance(event.get("bids"), list) or not isinstance(event.get("asks"), list)):
        stats["ignored_events"] += 1
        stats["invalid_events"] += 1
        stats["errors"].append({"index": index, "error": "price_change requires complete bids and asks lists"})
        return
    try:
        cache.update_book(
            token_id=token_id,
            bids=_coerce_levels(event.get("bids")),
            asks=_coerce_levels(event.get("asks")),
            sequence=_coerce_sequence(event.get("sequence") or event.get("seq")),
            received_at=str(event.get("timestamp") or event.get("received_at") or "").strip() or None,
            source=f"clob_ws:{event_type}",
        )
    except ValueError as exc:
        stats["invalid_events"] += 1
        if "sequence must be newer" in str(exc) or "sequence is required" in str(exc):
            stats["sequence_rejected_events"] += 1
            stats["stale_events"] += 1
        stats["errors"].append({"index": index, "error": str(exc)})
        return
    stats["processed_events"] += 1


def _valid_levels(levels: list[dict[str, Any]]) -> list[tuple[float, float]]:
    valid: list[tuple[float, float]] = []
    for level in levels:
        price = _coerce_float(level.get("price"))
        size = _coerce_float(level.get("size"))
        if price <= 0 or price >= 1 or size <= 0:
            continue
        valid.append((price, size))
    return valid


def _coerce_levels(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [level for level in value if isinstance(level, dict)]
    return []


def _coerce_sequence(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_token_set(token_ids: list[str] | None) -> set[str] | None:
    if token_ids is None:
        return None
    return {str(token).strip() for token in token_ids if str(token).strip()}


def _coerce_token_ids(value: Any) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            import json

            try:
                value = json.loads(stripped)
            except json.JSONDecodeError:
                return []
        elif stripped:
            value = [stripped]
    if not isinstance(value, list):
        return []
    return [str(token).strip() for token in value if str(token).strip()]
