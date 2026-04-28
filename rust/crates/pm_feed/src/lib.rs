use chrono::{DateTime, Utc};
use pm_types::{BookLevel, MarketEvent, MarketEventType, OrderBookSnapshot, Venue};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::error::Error;
use std::fmt;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FeedMessage {
    pub source: String,
    pub venue: Venue,
    pub market_id: String,
    pub symbol: String,
    pub received_at: DateTime<Utc>,
    pub message_type: FeedMessageType,
    pub raw_json: Value,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum FeedMessageType {
    Trade,
    Bbo,
    L2Snapshot,
    L2Delta,
    Status,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum NormalizedFeedEvent {
    MarketEvent(MarketEvent),
    OrderBookSnapshot {
        source: String,
        venue: Venue,
        market_id: String,
        symbol: String,
        received_at: DateTime<Utc>,
        snapshot: OrderBookSnapshot,
        raw_json: Value,
    },
    L2DeltaPlaceholder(FeedMessage),
    Status(FeedMessage),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Trade {
    pub source: String,
    pub venue: Venue,
    pub market_id: String,
    pub symbol: String,
    pub received_at: DateTime<Utc>,
    pub price: f64,
    pub size: Option<f64>,
    pub raw_json: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Bbo {
    pub source: String,
    pub venue: Venue,
    pub market_id: String,
    pub symbol: String,
    pub received_at: DateTime<Utc>,
    pub best_bid: Option<f64>,
    pub best_ask: Option<f64>,
    pub bid_size: Option<f64>,
    pub ask_size: Option<f64>,
    pub raw_json: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct L2Snapshot {
    pub source: String,
    pub venue: Venue,
    pub market_id: String,
    pub symbol: String,
    pub received_at: DateTime<Utc>,
    pub bids: Vec<BookLevel>,
    pub asks: Vec<BookLevel>,
    pub raw_json: Value,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FeedConversionError {
    WrongMessageType {
        expected: FeedMessageType,
        actual: FeedMessageType,
    },
    MissingField(&'static str),
    InvalidNumber(&'static str),
}

impl fmt::Display for FeedConversionError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::WrongMessageType { expected, actual } => {
                write!(
                    f,
                    "wrong feed message type: expected {expected:?}, got {actual:?}"
                )
            }
            Self::MissingField(field) => write!(f, "missing field `{field}`"),
            Self::InvalidNumber(field) => write!(f, "invalid numeric field `{field}`"),
        }
    }
}

impl Error for FeedConversionError {}

impl Trade {
    pub fn from_message(message: &FeedMessage) -> Result<Self, FeedConversionError> {
        ensure_type(message, FeedMessageType::Trade)?;
        Ok(Self {
            source: message.source.clone(),
            venue: message.venue.clone(),
            market_id: message.market_id.clone(),
            symbol: message.symbol.clone(),
            received_at: message.received_at,
            price: required_f64(&message.raw_json, "price")?,
            size: optional_f64(&message.raw_json, "size")?,
            raw_json: message.raw_json.clone(),
        })
    }
}

impl Bbo {
    pub fn from_message(message: &FeedMessage) -> Result<Self, FeedConversionError> {
        ensure_type(message, FeedMessageType::Bbo)?;
        Ok(Self {
            source: message.source.clone(),
            venue: message.venue.clone(),
            market_id: message.market_id.clone(),
            symbol: message.symbol.clone(),
            received_at: message.received_at,
            best_bid: optional_f64(&message.raw_json, "best_bid")?,
            best_ask: optional_f64(&message.raw_json, "best_ask")?,
            bid_size: optional_f64(&message.raw_json, "bid_size")?,
            ask_size: optional_f64(&message.raw_json, "ask_size")?,
            raw_json: message.raw_json.clone(),
        })
    }
}

impl L2Snapshot {
    pub fn from_message(message: &FeedMessage) -> Result<Self, FeedConversionError> {
        ensure_type(message, FeedMessageType::L2Snapshot)?;
        Ok(Self {
            source: message.source.clone(),
            venue: message.venue.clone(),
            market_id: message.market_id.clone(),
            symbol: message.symbol.clone(),
            received_at: message.received_at,
            bids: required_levels(&message.raw_json, "bids")?,
            asks: required_levels(&message.raw_json, "asks")?,
            raw_json: message.raw_json.clone(),
        })
    }

    pub fn to_order_book_snapshot(&self) -> OrderBookSnapshot {
        OrderBookSnapshot {
            bids: self.bids.clone(),
            asks: self.asks.clone(),
        }
    }
}

impl From<Trade> for MarketEvent {
    fn from(trade: Trade) -> Self {
        MarketEvent {
            event_id: Uuid::new_v4(),
            ts: trade.received_at,
            venue: trade.venue,
            market_id: trade.market_id,
            event_type: MarketEventType::Trade,
            best_bid: None,
            best_ask: None,
            last_trade_price: Some(trade.price),
            bid_size: None,
            ask_size: None,
            quote_age_ms: None,
        }
    }
}

impl From<Bbo> for MarketEvent {
    fn from(bbo: Bbo) -> Self {
        MarketEvent {
            event_id: Uuid::new_v4(),
            ts: bbo.received_at,
            venue: bbo.venue,
            market_id: bbo.market_id,
            event_type: MarketEventType::Quote,
            best_bid: bbo.best_bid,
            best_ask: bbo.best_ask,
            last_trade_price: None,
            bid_size: bbo.bid_size,
            ask_size: bbo.ask_size,
            quote_age_ms: None,
        }
    }
}

impl TryFrom<FeedMessage> for NormalizedFeedEvent {
    type Error = FeedConversionError;

    fn try_from(message: FeedMessage) -> Result<Self, Self::Error> {
        match message.message_type {
            FeedMessageType::Trade => Ok(Self::MarketEvent(Trade::from_message(&message)?.into())),
            FeedMessageType::Bbo => Ok(Self::MarketEvent(Bbo::from_message(&message)?.into())),
            FeedMessageType::L2Snapshot => {
                let snapshot = L2Snapshot::from_message(&message)?;
                let order_book_snapshot = snapshot.to_order_book_snapshot();
                Ok(Self::OrderBookSnapshot {
                    source: snapshot.source,
                    venue: snapshot.venue,
                    market_id: snapshot.market_id,
                    symbol: snapshot.symbol,
                    received_at: snapshot.received_at,
                    snapshot: order_book_snapshot,
                    raw_json: snapshot.raw_json,
                })
            }
            FeedMessageType::L2Delta => Ok(Self::L2DeltaPlaceholder(message)),
            FeedMessageType::Status => Ok(Self::Status(message)),
        }
    }
}

fn ensure_type(
    message: &FeedMessage,
    expected: FeedMessageType,
) -> Result<(), FeedConversionError> {
    if message.message_type == expected {
        Ok(())
    } else {
        Err(FeedConversionError::WrongMessageType {
            expected,
            actual: message.message_type,
        })
    }
}

fn required_f64(value: &Value, field: &'static str) -> Result<f64, FeedConversionError> {
    optional_f64(value, field)?.ok_or(FeedConversionError::MissingField(field))
}

fn optional_f64(value: &Value, field: &'static str) -> Result<Option<f64>, FeedConversionError> {
    let Some(raw) = value.get(field) else {
        return Ok(None);
    };
    let number = match raw {
        Value::Number(number) => number.as_f64(),
        Value::String(text) => text.parse::<f64>().ok(),
        _ => None,
    }
    .filter(|number| number.is_finite());

    number
        .ok_or(FeedConversionError::InvalidNumber(field))
        .map(Some)
}

fn required_levels(
    value: &Value,
    field: &'static str,
) -> Result<Vec<BookLevel>, FeedConversionError> {
    let levels = value
        .get(field)
        .and_then(Value::as_array)
        .ok_or(FeedConversionError::MissingField(field))?;

    levels
        .iter()
        .map(|level| {
            Ok(BookLevel {
                price: required_f64(level, "price")?,
                quantity: required_f64(level, "quantity")?,
            })
        })
        .collect()
}
