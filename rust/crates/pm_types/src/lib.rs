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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
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

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum BookDeltaSide {
    Bid,
    Ask,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BookDelta {
    pub ts: DateTime<Utc>,
    pub seq: u64,
    pub side: BookDeltaSide,
    pub price: f64,
    pub quantity: f64,
    pub is_trade: bool,
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ExecutionMode {
    Replay,
    Paper,
    LiveDryRun,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ExecutionBlocker {
    EmptyBook,
    NoFill,
    InsufficientDepth,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ExecutionAssumptions {
    pub schema_version: String,
    pub mode: ExecutionMode,
    pub latency_ms: u64,
    pub slippage_bps: f64,
    pub queue_ahead_quantity: f64,
    pub allow_multi_level_sweep: bool,
    pub reject_on_empty_book: bool,
    pub reject_on_insufficient_depth: bool,
    pub maker_fee_bps: f64,
    pub taker_fee_bps: f64,
    pub min_fee: f64,
    pub deposit_fixed: f64,
    pub deposit_bps: f64,
    pub withdrawal_fixed: f64,
    pub withdrawal_bps: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ExecutionParityQuote {
    pub schema_version: String,
    pub mode: ExecutionMode,
    pub side: BookSide,
    pub requested_quantity: f64,
    pub filled_quantity: f64,
    pub unfilled_quantity: f64,
    pub average_fill_price: Option<f64>,
    pub top_of_book_price: Option<f64>,
    pub gross_notional: f64,
    pub book_slippage_cost: f64,
    pub assumption_slippage_cost: f64,
    pub total_slippage_cost: f64,
    pub latency_ms: u64,
    pub queue_ahead_quantity: f64,
    pub levels_consumed: usize,
    pub status: ExecutionStatus,
    pub blocker: Option<ExecutionBlocker>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PositionSnapshot {
    pub schema_version: String,
    pub market_id: String,
    pub side: OrderSide,
    pub quantity: f64,
    pub avg_entry_price: f64,
    pub realized_pnl_usdc: f64,
    pub unrealized_pnl_usdc: f64,
    pub fees_paid_usdc: f64,
    pub paper_only: bool,
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

pub fn execution_mode_str(value: &ExecutionMode) -> &'static str {
    match value {
        ExecutionMode::Replay => "replay",
        ExecutionMode::Paper => "paper",
        ExecutionMode::LiveDryRun => "live_dry_run",
    }
}

pub fn execution_blocker_str(value: &ExecutionBlocker) -> &'static str {
    match value {
        ExecutionBlocker::EmptyBook => "empty_book",
        ExecutionBlocker::NoFill => "no_fill",
        ExecutionBlocker::InsufficientDepth => "insufficient_depth",
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

    #[test]
    fn book_delta_has_explicit_l2_side_and_sequence() {
        let delta = BookDelta {
            ts: Utc::now(),
            seq: 42,
            side: BookDeltaSide::Bid,
            price: 0.47,
            quantity: 12.5,
            is_trade: false,
        };

        assert_eq!(delta.side, BookDeltaSide::Bid);
        assert_eq!(delta.seq, 42);
        assert!(!delta.is_trade);
    }

    #[test]
    fn execution_parity_contract_is_dry_run_only() {
        let assumptions = ExecutionAssumptions {
            schema_version: "v1".to_string(),
            mode: ExecutionMode::LiveDryRun,
            latency_ms: 250,
            slippage_bps: 5.0,
            queue_ahead_quantity: 2.0,
            allow_multi_level_sweep: true,
            reject_on_empty_book: true,
            reject_on_insufficient_depth: false,
            maker_fee_bps: 0.0,
            taker_fee_bps: 10.0,
            min_fee: 0.0,
            deposit_fixed: 0.0,
            deposit_bps: 0.0,
            withdrawal_fixed: 0.0,
            withdrawal_bps: 0.0,
        };

        assert_eq!(execution_mode_str(&assumptions.mode), "live_dry_run");
        assert_eq!(
            execution_blocker_str(&ExecutionBlocker::InsufficientDepth),
            "insufficient_depth"
        );
    }

    #[test]
    fn position_snapshot_requires_explicit_paper_only_flag() {
        let position = PositionSnapshot {
            schema_version: "v1".to_string(),
            market_id: "demo-market".to_string(),
            side: OrderSide::BuyYes,
            quantity: 3.0,
            avg_entry_price: 0.42,
            realized_pnl_usdc: 0.0,
            unrealized_pnl_usdc: 0.1,
            fees_paid_usdc: 0.01,
            paper_only: true,
        };

        assert!(position.paper_only);
        assert_eq!(order_side_str(&position.side), "buy_yes");
    }
}
