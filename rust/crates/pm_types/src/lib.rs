use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum Venue {
    Polymarket,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum MarketEventType {
    Quote,
    Trade,
    BookSnapshot,
    BookDelta,
    Status,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum OrderSide {
    BuyYes,
    SellYes,
    BuyNo,
    SellNo,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum RiskDecisionStatus {
    Approved,
    Rejected,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ExecutionStatus {
    Accepted,
    Rejected,
    Open,
    PartiallyFilled,
    Filled,
    Cancelled,
    Error,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketEvent {
    pub event_id: Uuid,
    pub ts: DateTime<Utc>,
    pub venue: Venue,
    pub market_id: String,
    pub event_type: MarketEventType,
    pub best_bid: Option<f64>,
    pub best_ask: Option<f64>,
    pub last_trade_price: Option<f64>,
    pub bid_size: Option<f64>,
    pub ask_size: Option<f64>,
    pub quote_age_ms: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BookLevel {
    pub price: f64,
    pub quantity: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OrderBookSnapshot {
    pub bids: Vec<BookLevel>,
    pub asks: Vec<BookLevel>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum BookSide {
    Buy,
    Sell,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FillEstimate {
    pub side: BookSide,
    pub requested_quantity: f64,
    pub filled_quantity: f64,
    pub unfilled_quantity: f64,
    pub gross_notional: f64,
    pub average_price: Option<f64>,
    pub top_of_book_price: Option<f64>,
    pub slippage_cost: f64,
    pub slippage_bps: f64,
    pub levels_consumed: usize,
    pub status: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SpendFillEstimate {
    pub requested_spend: f64,
    pub top_ask: Option<f64>,
    pub avg_fill_price: Option<f64>,
    pub fillable_spend: f64,
    pub filled_quantity: f64,
    pub levels_used: usize,
    pub slippage_from_top_ask: Option<f64>,
    pub edge_after_fill: Option<f64>,
    pub execution_blocker: Option<String>,
    pub fill_status: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ExitValueEstimate {
    pub requested_quantity: f64,
    pub filled_quantity: f64,
    pub unfilled_quantity: f64,
    pub average_price: Option<f64>,
    pub value: f64,
    pub levels_consumed: usize,
    pub status: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FillEvent {
    pub market_id: String,
    pub side: OrderSide,
    pub price: f64,
    pub size: f64,
}

pub fn market_event_type_str(value: &MarketEventType) -> &'static str {
    match value {
        MarketEventType::Quote => "quote",
        MarketEventType::Trade => "trade",
        MarketEventType::BookSnapshot => "book_snapshot",
        MarketEventType::BookDelta => "book_delta",
        MarketEventType::Status => "status",
    }
}

pub fn order_side_str(value: &OrderSide) -> &'static str {
    match value {
        OrderSide::BuyYes => "buy_yes",
        OrderSide::SellYes => "sell_yes",
        OrderSide::BuyNo => "buy_no",
        OrderSide::SellNo => "sell_no",
    }
}

pub fn risk_decision_status_str(value: &RiskDecisionStatus) -> &'static str {
    match value {
        RiskDecisionStatus::Approved => "approved",
        RiskDecisionStatus::Rejected => "rejected",
    }
}

pub fn execution_status_str(value: &ExecutionStatus) -> &'static str {
    match value {
        ExecutionStatus::Accepted => "accepted",
        ExecutionStatus::Rejected => "rejected",
        ExecutionStatus::Open => "open",
        ExecutionStatus::PartiallyFilled => "partially_filled",
        ExecutionStatus::Filled => "filled",
        ExecutionStatus::Cancelled => "cancelled",
        ExecutionStatus::Error => "error",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn market_event_type_strings_are_snake_case() {
        assert_eq!(market_event_type_str(&MarketEventType::Quote), "quote");
        assert_eq!(
            market_event_type_str(&MarketEventType::BookSnapshot),
            "book_snapshot"
        );
        assert_eq!(
            market_event_type_str(&MarketEventType::BookDelta),
            "book_delta"
        );
    }

    #[test]
    fn order_side_strings_are_snake_case() {
        assert_eq!(order_side_str(&OrderSide::BuyYes), "buy_yes");
        assert_eq!(order_side_str(&OrderSide::SellNo), "sell_no");
    }

    #[test]
    fn status_strings_are_snake_case() {
        assert_eq!(
            risk_decision_status_str(&RiskDecisionStatus::Approved),
            "approved"
        );
        assert_eq!(
            execution_status_str(&ExecutionStatus::PartiallyFilled),
            "partially_filled"
        );
    }

    #[test]
    fn fill_event_keeps_canonical_side() {
        let fill = FillEvent {
            market_id: "demo-market".to_string(),
            side: OrderSide::BuyYes,
            price: 0.5,
            size: 1.0,
        };

        assert_eq!(order_side_str(&fill.side), "buy_yes");
    }
}
