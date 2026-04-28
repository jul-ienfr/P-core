use chrono::{DateTime, Utc};
use pm_types::{BookDelta, BookDeltaSide, MarketEvent, MarketEventType, OrderBookSnapshot, Venue};
use serde::{Deserialize, Serialize};
use std::fs::File;
use std::io::{self, BufRead, BufReader, BufWriter, Write};
use std::path::Path;
use uuid::Uuid;

#[derive(Debug)]
pub enum MarketDataLogError {
    Io(io::Error),
    Json(serde_json::Error),
}

impl std::fmt::Display for MarketDataLogError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(error) => write!(f, "market data log I/O error: {error}"),
            Self::Json(error) => write!(f, "market data log JSON error: {error}"),
        }
    }
}

impl std::error::Error for MarketDataLogError {}

impl From<io::Error> for MarketDataLogError {
    fn from(value: io::Error) -> Self {
        Self::Io(value)
    }
}

impl From<serde_json::Error> for MarketDataLogError {
    fn from(value: serde_json::Error) -> Self {
        Self::Json(value)
    }
}

pub type Result<T> = std::result::Result<T, MarketDataLogError>;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum MarketDataPayload {
    MarketEvent(MarketEvent),
    OrderBookSnapshot(OrderBookSnapshot),
    BookDelta(BookDelta),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MarketDataLogRecord {
    pub market_id: String,
    pub ts: DateTime<Utc>,
    pub payload: MarketDataPayload,
}

impl MarketDataLogRecord {
    pub fn market_event(event: MarketEvent) -> Self {
        Self {
            market_id: event.market_id.clone(),
            ts: event.ts,
            payload: MarketDataPayload::MarketEvent(event),
        }
    }

    pub fn order_book_snapshot(
        market_id: impl Into<String>,
        ts: DateTime<Utc>,
        snapshot: OrderBookSnapshot,
    ) -> Self {
        Self {
            market_id: market_id.into(),
            ts,
            payload: MarketDataPayload::OrderBookSnapshot(snapshot),
        }
    }

    pub fn book_delta(market_id: impl Into<String>, delta: BookDelta) -> Self {
        Self {
            market_id: market_id.into(),
            ts: delta.ts,
            payload: MarketDataPayload::BookDelta(delta),
        }
    }

    pub fn to_market_event(&self, venue: Venue) -> Option<MarketEvent> {
        match &self.payload {
            MarketDataPayload::MarketEvent(event) => Some(event.clone()),
            MarketDataPayload::OrderBookSnapshot(snapshot) => Some(MarketEvent {
                event_id: Uuid::new_v4(),
                ts: self.ts,
                venue,
                market_id: self.market_id.clone(),
                event_type: MarketEventType::BookSnapshot,
                best_bid: snapshot.bids.first().map(|level| level.price),
                best_ask: snapshot.asks.first().map(|level| level.price),
                last_trade_price: None,
                bid_size: snapshot.bids.first().map(|level| level.quantity),
                ask_size: snapshot.asks.first().map(|level| level.quantity),
                quote_age_ms: None,
            }),
            MarketDataPayload::BookDelta(delta) => Some(MarketEvent {
                event_id: Uuid::new_v4(),
                ts: self.ts,
                venue,
                market_id: self.market_id.clone(),
                event_type: if delta.is_trade {
                    MarketEventType::Trade
                } else {
                    MarketEventType::BookDelta
                },
                best_bid: matches!(delta.side, BookDeltaSide::Bid).then_some(delta.price),
                best_ask: matches!(delta.side, BookDeltaSide::Ask).then_some(delta.price),
                last_trade_price: delta.is_trade.then_some(delta.price),
                bid_size: matches!(delta.side, BookDeltaSide::Bid).then_some(delta.quantity),
                ask_size: matches!(delta.side, BookDeltaSide::Ask).then_some(delta.quantity),
                quote_age_ms: None,
            }),
        }
    }

    pub fn to_order_book_snapshot(&self) -> Option<OrderBookSnapshot> {
        match &self.payload {
            MarketDataPayload::OrderBookSnapshot(snapshot) => Some(snapshot.clone()),
            _ => None,
        }
    }
}

pub fn encode_record(record: &MarketDataLogRecord) -> Result<String> {
    Ok(serde_json::to_string(record)?)
}

pub fn decode_record(line: &str) -> Result<MarketDataLogRecord> {
    Ok(serde_json::from_str(line)?)
}

pub fn append_record(path: impl AsRef<Path>, record: &MarketDataLogRecord) -> Result<()> {
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)?;
    writeln!(file, "{}", encode_record(record)?)?;
    Ok(())
}

pub fn write_records(path: impl AsRef<Path>, records: &[MarketDataLogRecord]) -> Result<()> {
    let file = File::create(path)?;
    let mut writer = BufWriter::new(file);
    for record in records {
        writeln!(writer, "{}", encode_record(record)?)?;
    }
    writer.flush()?;
    Ok(())
}

pub fn read_records(path: impl AsRef<Path>) -> Result<Vec<MarketDataLogRecord>> {
    iter_records(path)?.collect()
}

pub fn iter_records(path: impl AsRef<Path>) -> Result<MarketDataLogIter> {
    let file = File::open(path)?;
    Ok(MarketDataLogIter {
        lines: BufReader::new(file).lines(),
    })
}

pub fn iter_records_by_market_and_time(
    path: impl AsRef<Path>,
    market_id: impl Into<String>,
    start: Option<DateTime<Utc>>,
    end: Option<DateTime<Utc>>,
) -> Result<MarketDataLogFilterIter> {
    Ok(MarketDataLogFilterIter {
        inner: iter_records(path)?,
        market_id: market_id.into(),
        start,
        end,
    })
}

pub struct MarketDataLogIter {
    lines: std::io::Lines<BufReader<File>>,
}

impl Iterator for MarketDataLogIter {
    type Item = Result<MarketDataLogRecord>;

    fn next(&mut self) -> Option<Self::Item> {
        for line in self.lines.by_ref() {
            match line {
                Ok(line) if line.trim().is_empty() => continue,
                Ok(line) => return Some(decode_record(&line)),
                Err(error) => return Some(Err(MarketDataLogError::Io(error))),
            }
        }
        None
    }
}

pub struct MarketDataLogFilterIter {
    inner: MarketDataLogIter,
    market_id: String,
    start: Option<DateTime<Utc>>,
    end: Option<DateTime<Utc>>,
}

impl Iterator for MarketDataLogFilterIter {
    type Item = Result<MarketDataLogRecord>;

    fn next(&mut self) -> Option<Self::Item> {
        for record in self.inner.by_ref() {
            match record {
                Ok(record) if record.market_id != self.market_id => continue,
                Ok(record) if self.start.is_some_and(|start| record.ts < start) => continue,
                Ok(record) if self.end.is_some_and(|end| record.ts > end) => continue,
                other => return Some(other),
            }
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pm_types::{BookDeltaSide, BookLevel};

    fn temp_log_path(name: &str) -> std::path::PathBuf {
        let unique = format!(
            "p_core_market_data_log_{name}_{}_{}.jsonl",
            std::process::id(),
            Uuid::new_v4()
        );
        std::env::temp_dir().join(unique)
    }

    fn ts(seconds: i64) -> DateTime<Utc> {
        DateTime::from_timestamp(seconds, 0).expect("fixture timestamp should be valid")
    }

    fn delta(seconds: i64, seq: u64, side: BookDeltaSide, price: f64, quantity: f64) -> BookDelta {
        BookDelta {
            ts: ts(seconds),
            seq,
            side,
            price,
            quantity,
            is_trade: false,
        }
    }

    #[test]
    fn jsonl_roundtrip_preserves_book_delta_record() {
        let record = MarketDataLogRecord::book_delta(
            "demo-market",
            delta(10, 7, BookDeltaSide::Bid, 0.42, 3.0),
        );

        let encoded = encode_record(&record).expect("record should encode");
        let decoded = decode_record(&encoded).expect("record should decode");

        assert_eq!(decoded, record);
        assert!(encoded.contains("\"book_delta\""));
    }

    #[test]
    fn iterator_filters_by_market_and_inclusive_time_range() {
        let path = temp_log_path("filter");
        let records = vec![
            MarketDataLogRecord::book_delta("other", delta(10, 1, BookDeltaSide::Bid, 0.40, 1.0)),
            MarketDataLogRecord::book_delta("demo", delta(10, 1, BookDeltaSide::Bid, 0.41, 1.0)),
            MarketDataLogRecord::book_delta("demo", delta(20, 2, BookDeltaSide::Ask, 0.60, 2.0)),
            MarketDataLogRecord::book_delta("demo", delta(30, 3, BookDeltaSide::Ask, 0.61, 3.0)),
        ];
        write_records(&path, &records).expect("records should write");

        let filtered = iter_records_by_market_and_time(&path, "demo", Some(ts(10)), Some(ts(20)))
            .expect("iterator should open")
            .collect::<Result<Vec<_>>>()
            .expect("records should decode");

        assert_eq!(filtered.len(), 2);
        assert_eq!(filtered[0].market_id, "demo");
        assert_eq!(filtered[1].ts, ts(20));

        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn snapshot_record_converts_to_market_event_top_of_book() {
        let record = MarketDataLogRecord::order_book_snapshot(
            "demo",
            ts(100),
            OrderBookSnapshot {
                bids: vec![BookLevel {
                    price: 0.45,
                    quantity: 5.0,
                }],
                asks: vec![BookLevel {
                    price: 0.55,
                    quantity: 7.0,
                }],
            },
        );

        let event = record
            .to_market_event(Venue::Polymarket)
            .expect("snapshot converts to event");

        assert_eq!(event.event_type, MarketEventType::BookSnapshot);
        assert_eq!(event.best_bid, Some(0.45));
        assert_eq!(event.best_ask, Some(0.55));
        assert_eq!(event.bid_size, Some(5.0));
        assert_eq!(event.ask_size, Some(7.0));
    }

    #[test]
    fn append_record_adds_jsonl_entry() {
        let path = temp_log_path("append");
        append_record(
            &path,
            &MarketDataLogRecord::book_delta("demo", delta(1, 1, BookDeltaSide::Bid, 0.4, 1.0)),
        )
        .expect("first append should succeed");
        append_record(
            &path,
            &MarketDataLogRecord::book_delta("demo", delta(2, 2, BookDeltaSide::Ask, 0.6, 1.0)),
        )
        .expect("second append should succeed");

        let records = read_records(&path).expect("records should read");

        assert_eq!(records.len(), 2);
        assert_eq!(records[1].ts, ts(2));

        let _ = std::fs::remove_file(path);
    }
}
