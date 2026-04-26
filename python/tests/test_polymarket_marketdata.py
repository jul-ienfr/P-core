import pytest

from prediction_core.polymarket_marketdata import (
    MarketDataCache,
    MarketDataSnapshot,
    build_marketdata_worker_plan,
    open_polymarket_clob_ws_stream,
    replay_clob_ws_events,
    run_clob_marketdata_stream,
    select_hot_path_subscriptions,
)


class FakeWebSocket:
    def __init__(self, events):
        self.events = events
        self.sent_messages = []

    async def send(self, message):
        self.sent_messages.append(message)

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for event in self.events:
            yield event


class FakeWebSocketContext:
    def __init__(self, websocket):
        self.websocket = websocket
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self.websocket

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True
        return False


class FakeWebSocketsModule:
    def __init__(self, websocket):
        self.websocket = websocket
        self.calls = []

    def connect(self, url):
        self.calls.append(url)
        return FakeWebSocketContext(self.websocket)


def test_marketdata_cache_computes_best_prices_defensively_from_unsorted_book():
    cache = MarketDataCache()

    snapshot = cache.update_book(
        token_id="yes-token",
        bids=[{"price": "0.41", "size": "10"}, {"price": "0.45", "size": "2"}],
        asks=[{"price": "0.52", "size": "4"}, {"price": "0.49", "size": "3"}],
        sequence=7,
    )

    assert isinstance(snapshot, MarketDataSnapshot)
    assert snapshot.token_id == "yes-token"
    assert snapshot.best_bid == 0.45
    assert snapshot.best_ask == 0.49
    assert snapshot.spread == 0.04
    assert snapshot.sequence == 7
    assert cache.snapshot("yes-token") == snapshot


def test_marketdata_cache_ignores_malformed_levels_without_poisoning_book():
    cache = MarketDataCache()

    snapshot = cache.update_book(
        token_id="no-token",
        bids=[{"price": "bad", "size": "10"}, {"price": "0.21", "size": "0"}, {"price": "0.2", "size": "5"}],
        asks=[{"price": "0.25", "size": "0"}, {"price": "0.24", "size": "6"}],
    )

    assert snapshot.best_bid == 0.2
    assert snapshot.best_ask == 0.24
    assert snapshot.bid_depth == 5.0
    assert snapshot.ask_depth == 6.0


def test_select_hot_path_subscriptions_only_keeps_tradeable_token_ids():
    markets = [
        {"id": "m1", "clobTokenIds": ["yes-1", "no-1"], "liquidity": 1000, "closed": False},
        {"id": "m2", "clobTokenIds": ["yes-2", "no-2"], "liquidity": 10, "closed": False},
        {"id": "m3", "clobTokenIds": [], "liquidity": 9999, "closed": False},
        {"id": "m4", "clobTokenIds": ["yes-4", "no-4"], "liquidity": 9999, "closed": True},
    ]

    subscriptions = select_hot_path_subscriptions(markets, min_liquidity=100)

    assert subscriptions == [
        {"market_id": "m1", "token_id": "yes-1", "outcome_index": 0},
        {"market_id": "m1", "token_id": "no-1", "outcome_index": 1},
    ]


def test_worker_plan_separates_gamma_data_and_clob_roles():
    plan = build_marketdata_worker_plan(discovery_interval_seconds=60, max_hot_markets=25)

    assert plan["workers"]["discovery_worker"]["api"] == "Gamma API"
    assert plan["workers"]["discovery_worker"]["hot_path"] is False
    assert plan["workers"]["analytics_worker"]["api"] == "Data API"
    assert plan["workers"]["analytics_worker"]["hot_path"] is False
    assert plan["workers"]["marketdata_worker"]["api"] == "CLOB WebSocket"
    assert plan["workers"]["marketdata_worker"]["hot_path"] is True
    assert plan["workers"]["decision_worker"]["api"] == "local cache"
    assert plan["workers"]["decision_worker"]["hot_path"] is True
    assert plan["discovery_interval_seconds"] == 60
    assert plan["max_hot_markets"] == 25


def test_replay_clob_ws_events_updates_cache_from_market_events_only():
    cache = MarketDataCache()

    summary = replay_clob_ws_events(
        [
            {"event_type": "subscribed", "asset_id": "ignored", "sequence": 1},
            {
                "event_type": "book",
                "asset_id": "yes-token",
                "bids": [{"price": "0.44", "size": "5"}],
                "asks": [{"price": "0.48", "size": "3"}],
                "sequence": 2,
            },
            {
                "type": "price_change",
                "token_id": "yes-token",
                "bids": [{"price": "0.46", "size": "8"}, {"price": "0.45", "size": "2"}],
                "asks": [{"price": "0.51", "size": "1"}, {"price": "0.49", "size": "4"}],
                "sequence": 3,
            },
        ],
        cache=cache,
    )

    assert summary["processed_events"] == 2
    assert summary["ignored_events"] == 1
    assert summary["snapshots"]["yes-token"]["best_bid"] == 0.46
    assert summary["snapshots"]["yes-token"]["best_ask"] == 0.49
    assert summary["snapshots"]["yes-token"]["sequence"] == 3
    assert cache.snapshot("yes-token").spread == 0.03


def test_replay_clob_ws_events_reports_bad_book_events_without_stopping_replay():
    summary = replay_clob_ws_events(
        [
            {"event_type": "book", "asset_id": "", "bids": [], "asks": [], "sequence": 1},
            {
                "event_type": "book",
                "asset_id": "no-token",
                "bids": [{"price": "0.11", "size": "2"}],
                "asks": [{"price": "0.14", "size": "2"}],
                "sequence": 2,
            },
        ]
    )

    assert summary["processed_events"] == 1
    assert summary["invalid_events"] == 1
    assert summary["errors"] == [{"index": 0, "error": "token_id is required"}]
    assert summary["snapshots"]["no-token"]["best_bid"] == 0.11


@pytest.mark.asyncio
async def test_run_clob_marketdata_stream_subscribes_and_stops_after_event_limit():
    sent_messages = []
    events = [
        {"event_type": "subscribed", "asset_id": "yes-token"},
        {
            "event_type": "book",
            "asset_id": "yes-token",
            "bids": [{"price": "0.62", "size": "3"}],
            "asks": [{"price": "0.67", "size": "4"}],
            "sequence": 11,
        },
        {
            "event_type": "book",
            "asset_id": "no-token",
            "bids": [{"price": "0.33", "size": "2"}],
            "asks": [{"price": "0.38", "size": "1"}],
            "sequence": 12,
        },
    ]

    async def fake_stream_factory(url, subscribe_message):
        sent_messages.append({"url": url, "subscribe_message": subscribe_message})
        for event in events:
            yield event

    summary = await run_clob_marketdata_stream(
        token_ids=["yes-token", "no-token"],
        stream_factory=fake_stream_factory,
        max_events=2,
    )

    assert sent_messages == [
        {
            "url": "wss://clob.polymarket.com/ws/market",
            "subscribe_message": {"type": "market", "assets_ids": ["yes-token", "no-token"]},
        }
    ]
    assert summary["mode"] == "paper/read-only clob websocket stream"
    assert summary["received_events"] == 2
    assert summary["processed_events"] == 1
    assert summary["ignored_events"] == 1
    assert summary["snapshots"]["yes-token"]["best_bid"] == 0.62
    assert "no-token" not in summary["snapshots"]


@pytest.mark.asyncio
async def test_run_clob_marketdata_stream_rejects_empty_token_list_before_connecting():
    async def fake_stream_factory(url, subscribe_message):
        raise AssertionError("stream should not be opened without token ids")
        yield {}

    with pytest.raises(ValueError, match="token_ids is required"):
        await run_clob_marketdata_stream(token_ids=[], stream_factory=fake_stream_factory)


@pytest.mark.asyncio
async def test_open_polymarket_clob_ws_stream_sends_subscription_and_decodes_messages():
    websocket = FakeWebSocket(
        [
            '{"event_type":"subscribed","asset_id":"yes-token"}',
            {"event_type": "book", "asset_id": "yes-token", "bids": [], "asks": []},
        ]
    )
    fake_websockets = FakeWebSocketsModule(websocket)

    stream = open_polymarket_clob_ws_stream(
        "wss://example.test/ws/market",
        {"type": "market", "assets_ids": ["yes-token"]},
        websockets_module=fake_websockets,
    )
    events = []
    async for event in stream:
        events.append(event)

    assert fake_websockets.calls == ["wss://example.test/ws/market"]
    assert websocket.sent_messages == ['{"type":"market","assets_ids":["yes-token"]}']
    assert events == [
        {"event_type": "subscribed", "asset_id": "yes-token"},
        {"event_type": "book", "asset_id": "yes-token", "bids": [], "asks": []},
    ]


@pytest.mark.asyncio
async def test_open_polymarket_clob_ws_stream_errors_clearly_when_dependency_missing():
    with pytest.raises(RuntimeError, match="websockets package is required"):
        stream = open_polymarket_clob_ws_stream(
            "wss://example.test/ws/market",
            {"type": "market", "assets_ids": ["yes-token"]},
            websockets_module=None,
        )
        async for _event in stream:
            pass
