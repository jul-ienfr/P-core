use chrono::{TimeZone, Utc};
use pm_feed::{Bbo, FeedMessage, FeedMessageType, L2Snapshot, NormalizedFeedEvent, Trade};
use pm_types::{MarketEventType, Venue};
use serde_json::json;

fn received_at() -> chrono::DateTime<Utc> {
    Utc.with_ymd_and_hms(2026, 4, 28, 15, 0, 0).unwrap()
}

#[test]
fn trade_fixture_converts_to_market_event_with_last_trade_price() {
    let message = FeedMessage {
        source: "fixture".to_string(),
        venue: Venue::Polymarket,
        market_id: "market-123".to_string(),
        symbol: "YES".to_string(),
        received_at: received_at(),
        message_type: FeedMessageType::Trade,
        raw_json: json!({
            "price": "0.47",
            "size": "12.5",
            "trade_id": "offline-trade-1"
        }),
    };

    let trade = Trade::from_message(&message).expect("fixture trade parses");
    assert_eq!(trade.price, 0.47);
    assert_eq!(trade.size, Some(12.5));

    let event: pm_types::MarketEvent = trade.into();
    assert_eq!(event.event_type, MarketEventType::Trade);
    assert_eq!(event.venue, Venue::Polymarket);
    assert_eq!(event.market_id, "market-123");
    assert_eq!(event.ts, received_at());
    assert_eq!(event.last_trade_price, Some(0.47));
    assert_eq!(event.best_bid, None);
    assert_eq!(event.best_ask, None);
}

#[test]
fn bbo_fixture_converts_to_quote_market_event() {
    let message = FeedMessage {
        source: "fixture".to_string(),
        venue: Venue::Polymarket,
        market_id: "market-123".to_string(),
        symbol: "YES".to_string(),
        received_at: received_at(),
        message_type: FeedMessageType::Bbo,
        raw_json: json!({
            "best_bid": 0.46,
            "best_ask": 0.48,
            "bid_size": "100.0",
            "ask_size": "75.5"
        }),
    };

    let bbo = Bbo::from_message(&message).expect("fixture bbo parses");
    let event: pm_types::MarketEvent = bbo.into();

    assert_eq!(event.event_type, MarketEventType::Quote);
    assert_eq!(event.best_bid, Some(0.46));
    assert_eq!(event.best_ask, Some(0.48));
    assert_eq!(event.bid_size, Some(100.0));
    assert_eq!(event.ask_size, Some(75.5));
    assert_eq!(event.last_trade_price, None);
}

#[test]
fn l2_snapshot_fixture_converts_to_order_book_snapshot() {
    let message = FeedMessage {
        source: "fixture".to_string(),
        venue: Venue::Polymarket,
        market_id: "market-123".to_string(),
        symbol: "YES".to_string(),
        received_at: received_at(),
        message_type: FeedMessageType::L2Snapshot,
        raw_json: json!({
            "bids": [
                {"price": "0.46", "quantity": "100"},
                {"price": 0.45, "quantity": 50.0}
            ],
            "asks": [
                {"price": "0.48", "quantity": "75.5"},
                {"price": 0.49, "quantity": 60.0}
            ]
        }),
    };

    let snapshot = L2Snapshot::from_message(&message).expect("fixture snapshot parses");
    let book = snapshot.to_order_book_snapshot();

    assert_eq!(book.bids.len(), 2);
    assert_eq!(book.asks.len(), 2);
    assert_eq!(book.bids[0].price, 0.46);
    assert_eq!(book.bids[0].quantity, 100.0);
    assert_eq!(book.asks[0].price, 0.48);
    assert_eq!(book.asks[0].quantity, 75.5);
}

#[test]
fn normalized_feed_event_preserves_offline_placeholder_events() {
    let delta = FeedMessage {
        source: "fixture".to_string(),
        venue: Venue::Polymarket,
        market_id: "market-123".to_string(),
        symbol: "YES".to_string(),
        received_at: received_at(),
        message_type: FeedMessageType::L2Delta,
        raw_json: json!({"changes": []}),
    };

    let normalized = NormalizedFeedEvent::try_from(delta).expect("delta placeholder is accepted");
    assert!(matches!(
        normalized,
        NormalizedFeedEvent::L2DeltaPlaceholder(_)
    ));
}
