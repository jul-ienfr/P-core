use pm_executor::OrderIntent;
use pm_ledger::LedgerEnvelope;
use pm_risk::RiskDecision;
use pm_signal::SignalEvent;
use pm_types::{
    execution_status_str, market_event_type_str, order_side_str, risk_decision_status_str,
    ExecutionStatus, FillEvent, MarketEvent,
};
use serde::Serialize;
use sqlx::postgres::PgArguments;
use sqlx::{Arguments, Executor, Postgres};

pub const STORAGE_SQL_SCHEMA: &str = r#"
CREATE TABLE IF NOT EXISTS market_events (
    market_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_id TEXT NOT NULL UNIQUE,
    best_bid DOUBLE PRECISION,
    best_ask DOUBLE PRECISION,
    last_trade_price DOUBLE PRECISION,
    quote_age_ms BIGINT
);

CREATE TABLE IF NOT EXISTS signal_events (
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,
    fair_value DOUBLE PRECISION NOT NULL,
    observed_price DOUBLE PRECISION NOT NULL,
    edge_bps DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_decisions (
    decision TEXT NOT NULL,
    reasons_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_intents (
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    size DOUBLE PRECISION NOT NULL
);
ALTER TABLE order_intents ADD COLUMN IF NOT EXISTS local_order_id TEXT;
ALTER TABLE order_intents ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'advisory_intent';
ALTER TABLE order_intents DROP CONSTRAINT IF EXISTS order_intents_advisory_status;
ALTER TABLE order_intents ADD CONSTRAINT order_intents_advisory_status CHECK (status = 'advisory_intent');
CREATE INDEX IF NOT EXISTS idx_order_intents_local_order_id ON order_intents (local_order_id);

CREATE TABLE IF NOT EXISTS fills (
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    size DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_reports (
    market_id TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT
);
"#;

#[derive(Debug, Clone, Serialize, PartialEq)]
pub enum SqlValue {
    Text(String),
    OptF64(Option<f64>),
    OptI64(Option<i64>),
    OptText(Option<String>),
}

#[derive(Debug, Clone, Serialize)]
pub struct SqlInsert {
    pub table: &'static str,
    pub columns: Vec<&'static str>,
    pub values: Vec<SqlValue>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PostgresInsertStatement {
    pub sql: String,
    pub params: Vec<SqlValue>,
}

impl SqlInsert {
    pub fn to_postgres_insert_statement(&self) -> PostgresInsertStatement {
        let placeholders = (1..=self.columns.len())
            .map(|index| format!("${index}"))
            .collect::<Vec<_>>()
            .join(", ");
        let columns = self.columns.join(", ");
        let sql = format!(
            "INSERT INTO {} ({}) VALUES ({})",
            self.table, columns, placeholders
        );

        PostgresInsertStatement {
            sql,
            params: self.values.clone(),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct MarketEventRow {
    pub event_type: &'static str,
    pub market_id: String,
    pub best_bid: Option<f64>,
    pub best_ask: Option<f64>,
    pub last_trade_price: Option<f64>,
    pub quote_age_ms: Option<i64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct SignalEventRow {
    pub market_id: String,
    pub side: &'static str,
    pub fair_value: f64,
    pub observed_price: f64,
    pub edge_bps: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct RiskDecisionRow {
    pub decision: &'static str,
    pub reasons: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct OrderIntentRow {
    pub local_order_id: String,
    pub market_id: String,
    pub side: &'static str,
    pub price: f64,
    pub size: f64,
    pub status: &'static str,
}

#[derive(Debug, Clone, Serialize)]
pub struct FillRow {
    pub market_id: String,
    pub side: &'static str,
    pub price: f64,
    pub size: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct ExecutionReportRow {
    pub market_id: String,
    pub status: &'static str,
    pub message: Option<String>,
}

fn sql_text(value: impl Into<String>) -> SqlValue {
    SqlValue::Text(value.into())
}

fn sql_f64(value: f64) -> SqlValue {
    assert!(value.is_finite(), "SQL f64 values must be finite");
    SqlValue::OptF64(Some(value))
}

fn sql_opt_f64(value: Option<f64>) -> SqlValue {
    if let Some(value) = value {
        assert!(value.is_finite(), "SQL optional f64 values must be finite");
    }
    SqlValue::OptF64(value)
}

fn sql_opt_i64(value: Option<i64>) -> SqlValue {
    SqlValue::OptI64(value)
}

fn sql_opt_text(value: Option<String>) -> SqlValue {
    SqlValue::OptText(value)
}

fn local_order_id(market_id: &str, side: &str, price: f64, size: f64) -> String {
    assert!(price.is_finite(), "local order price must be finite");
    assert!(size.is_finite(), "local order size must be finite");
    format!("intent:{market_id}:{side}:{price:.6}:{size:.6}")
}

fn bind_sql_value<'a>(arguments: &mut PgArguments, value: &'a SqlValue) {
    match value {
        SqlValue::Text(value) => arguments
            .add(value.clone())
            .expect("text bind should succeed"),
        SqlValue::OptF64(value) => arguments.add(*value).expect("f64 bind should succeed"),
        SqlValue::OptI64(value) => arguments.add(*value).expect("i64 bind should succeed"),
        SqlValue::OptText(value) => arguments
            .add(value.clone())
            .expect("optional text bind should succeed"),
    }
}

pub fn market_event_row(event: &MarketEvent) -> MarketEventRow {
    MarketEventRow {
        event_type: market_event_type_str(&event.event_type),
        market_id: event.market_id.clone(),
        best_bid: event.best_bid,
        best_ask: event.best_ask,
        last_trade_price: event.last_trade_price,
        quote_age_ms: event.quote_age_ms,
    }
}

pub fn signal_event_row(signal: &SignalEvent) -> SignalEventRow {
    SignalEventRow {
        market_id: signal.market_id.clone(),
        side: order_side_str(&signal.side),
        fair_value: signal.side_fair_value,
        observed_price: signal.observed_price,
        edge_bps: signal.edge_bps,
    }
}

pub fn risk_decision_row(decision: &RiskDecision) -> RiskDecisionRow {
    RiskDecisionRow {
        decision: risk_decision_status_str(&decision.decision),
        reasons: decision.reasons.clone(),
    }
}

pub fn order_intent_row(intent: &OrderIntent) -> OrderIntentRow {
    let side = order_side_str(&intent.side);
    OrderIntentRow {
        local_order_id: local_order_id(&intent.market_id, side, intent.price, intent.size),
        market_id: intent.market_id.clone(),
        side,
        price: intent.price,
        size: intent.size,
        status: "advisory_intent",
    }
}

pub fn fill_row(fill: &FillEvent) -> FillRow {
    FillRow {
        market_id: fill.market_id.clone(),
        side: order_side_str(&fill.side),
        price: fill.price,
        size: fill.size,
    }
}

pub fn execution_report_row(
    market_id: impl Into<String>,
    status: &ExecutionStatus,
    message: Option<String>,
) -> ExecutionReportRow {
    ExecutionReportRow {
        market_id: market_id.into(),
        status: execution_status_str(status),
        message,
    }
}

pub fn market_event_insert(event: &MarketEvent) -> SqlInsert {
    let row = market_event_row(event);
    SqlInsert {
        table: "market_events",
        columns: vec![
            "market_id",
            "event_type",
            "event_id",
            "best_bid",
            "best_ask",
            "last_trade_price",
            "quote_age_ms",
        ],
        values: vec![
            sql_text(row.market_id),
            sql_text(row.event_type),
            sql_text(event.event_id.to_string()),
            sql_opt_f64(row.best_bid),
            sql_opt_f64(row.best_ask),
            sql_opt_f64(row.last_trade_price),
            sql_opt_i64(row.quote_age_ms),
        ],
    }
}

pub fn signal_event_insert(signal: &SignalEvent) -> SqlInsert {
    let row = signal_event_row(signal);
    SqlInsert {
        table: "signal_events",
        columns: vec![
            "market_id",
            "side",
            "fair_value",
            "observed_price",
            "edge_bps",
        ],
        values: vec![
            sql_text(row.market_id),
            sql_text(row.side),
            sql_f64(row.fair_value),
            sql_f64(row.observed_price),
            sql_f64(row.edge_bps),
        ],
    }
}

pub fn risk_decision_insert(decision: &RiskDecision) -> SqlInsert {
    let row = risk_decision_row(decision);
    SqlInsert {
        table: "risk_decisions",
        columns: vec!["decision", "reasons_json"],
        values: vec![
            sql_text(row.decision),
            sql_text(serde_json::to_string(&row.reasons).expect("risk reasons should serialize")),
        ],
    }
}

pub fn order_intent_insert(intent: &OrderIntent) -> SqlInsert {
    let row = order_intent_row(intent);
    SqlInsert {
        table: "order_intents",
        columns: vec![
            "local_order_id",
            "market_id",
            "side",
            "price",
            "size",
            "status",
        ],
        values: vec![
            sql_text(row.local_order_id),
            sql_text(row.market_id),
            sql_text(row.side),
            sql_f64(row.price),
            sql_f64(row.size),
            sql_text(row.status),
        ],
    }
}

pub fn fill_insert(fill: &FillEvent) -> SqlInsert {
    let row = fill_row(fill);
    SqlInsert {
        table: "fills",
        columns: vec!["market_id", "side", "price", "size"],
        values: vec![
            sql_text(row.market_id),
            sql_text(row.side),
            sql_f64(row.price),
            sql_f64(row.size),
        ],
    }
}

pub fn execution_report_insert(report: &ExecutionReportRow) -> SqlInsert {
    SqlInsert {
        table: "execution_reports",
        columns: vec!["market_id", "status", "message"],
        values: vec![
            sql_text(report.market_id.clone()),
            sql_text(report.status),
            sql_opt_text(report.message.clone()),
        ],
    }
}

pub fn market_event_postgres_insert(event: &MarketEvent) -> PostgresInsertStatement {
    market_event_insert(event).to_postgres_insert_statement()
}

pub fn signal_event_postgres_insert(signal: &SignalEvent) -> PostgresInsertStatement {
    signal_event_insert(signal).to_postgres_insert_statement()
}

pub fn risk_decision_postgres_insert(decision: &RiskDecision) -> PostgresInsertStatement {
    risk_decision_insert(decision).to_postgres_insert_statement()
}

pub fn order_intent_postgres_insert(intent: &OrderIntent) -> PostgresInsertStatement {
    order_intent_insert(intent).to_postgres_insert_statement()
}

pub fn fill_postgres_insert(fill: &FillEvent) -> PostgresInsertStatement {
    fill_insert(fill).to_postgres_insert_statement()
}

pub fn execution_report_postgres_insert(report: &ExecutionReportRow) -> PostgresInsertStatement {
    execution_report_insert(report).to_postgres_insert_statement()
}

pub async fn apply_schema<'e, E>(executor: E) -> Result<(), sqlx::Error>
where
    E: Executor<'e, Database = Postgres>,
{
    executor.execute(STORAGE_SQL_SCHEMA).await?;
    Ok(())
}

pub async fn execute_sql_insert<'e, E>(executor: E, insert: &SqlInsert) -> Result<(), sqlx::Error>
where
    E: Executor<'e, Database = Postgres>,
{
    let statement = insert.to_postgres_insert_statement();
    let mut arguments = PgArguments::default();
    for param in &statement.params {
        bind_sql_value(&mut arguments, param);
    }
    sqlx::query_with(&statement.sql, arguments)
        .execute(executor)
        .await?;
    Ok(())
}

pub async fn execute_market_event<'e, E>(
    executor: E,
    event: &MarketEvent,
) -> Result<(), sqlx::Error>
where
    E: Executor<'e, Database = Postgres>,
{
    execute_sql_insert(executor, &market_event_insert(event)).await
}

pub async fn execute_signal_event<'e, E>(
    executor: E,
    signal: &SignalEvent,
) -> Result<(), sqlx::Error>
where
    E: Executor<'e, Database = Postgres>,
{
    execute_sql_insert(executor, &signal_event_insert(signal)).await
}

pub async fn execute_risk_decision<'e, E>(
    executor: E,
    decision: &RiskDecision,
) -> Result<(), sqlx::Error>
where
    E: Executor<'e, Database = Postgres>,
{
    execute_sql_insert(executor, &risk_decision_insert(decision)).await
}

pub async fn execute_order_intent<'e, E>(
    executor: E,
    intent: &OrderIntent,
) -> Result<(), sqlx::Error>
where
    E: Executor<'e, Database = Postgres>,
{
    execute_sql_insert(executor, &order_intent_insert(intent)).await
}

pub async fn execute_fill<'e, E>(executor: E, fill: &FillEvent) -> Result<(), sqlx::Error>
where
    E: Executor<'e, Database = Postgres>,
{
    execute_sql_insert(executor, &fill_insert(fill)).await
}

pub async fn execute_execution_report<'e, E>(
    executor: E,
    report: &ExecutionReportRow,
) -> Result<(), sqlx::Error>
where
    E: Executor<'e, Database = Postgres>,
{
    execute_sql_insert(executor, &execution_report_insert(report)).await
}

pub fn market_event_ledger(event: &MarketEvent) -> Result<String, serde_json::Error> {
    LedgerEnvelope {
        kind: "market_event",
        payload: market_event_row(event),
    }
    .to_json()
}

pub fn signal_event_ledger(signal: &SignalEvent) -> Result<String, serde_json::Error> {
    LedgerEnvelope {
        kind: "signal_event",
        payload: signal_event_row(signal),
    }
    .to_json()
}

#[cfg(test)]
mod runtime_integration;

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use pm_types::{MarketEventType, OrderSide, RiskDecisionStatus, Venue};
    use uuid::Uuid;

    #[test]
    fn market_event_row_uses_explicit_snake_case_type() {
        let event = MarketEvent {
            event_id: Uuid::new_v4(),
            ts: Utc::now(),
            venue: Venue::Polymarket,
            market_id: "demo-market".to_string(),
            event_type: MarketEventType::BookSnapshot,
            best_bid: Some(0.49),
            best_ask: Some(0.50),
            last_trade_price: None,
            bid_size: None,
            ask_size: None,
            quote_age_ms: Some(15),
        };

        let row = market_event_row(&event);
        assert_eq!(row.event_type, "book_snapshot");
    }

    #[test]
    fn signal_event_row_uses_explicit_snake_case_side() {
        let signal = SignalEvent {
            venue: Venue::Polymarket,
            market_id: "demo-market".to_string(),
            side: OrderSide::BuyYes,
            side_fair_value: 0.52,
            observed_price: 0.50,
            edge_bps: 400.0,
        };

        let row = signal_event_row(&signal);
        assert_eq!(row.side, "buy_yes");
    }

    #[test]
    fn order_intent_row_has_stable_local_id_and_advisory_status() {
        let intent = OrderIntent {
            market_id: "demo-market".to_string(),
            side: OrderSide::BuyYes,
            price: 0.5,
            size: 1.0,
        };

        let row = order_intent_row(&intent);

        assert_eq!(
            row.local_order_id,
            "intent:demo-market:buy_yes:0.500000:1.000000"
        );
        assert_eq!(row.status, "advisory_intent");
    }

    #[test]
    fn risk_decision_and_fill_rows_use_canonical_strings() {
        let decision = RiskDecision {
            decision: RiskDecisionStatus::Rejected,
            reasons: vec!["crossed_or_incomplete_book".to_string()],
        };
        let fill = FillEvent {
            market_id: "demo-market".to_string(),
            side: OrderSide::BuyYes,
            price: 0.5,
            size: 1.0,
        };

        assert_eq!(risk_decision_row(&decision).decision, "rejected");
        assert_eq!(fill_row(&fill).side, "buy_yes");
    }

    #[test]
    fn market_event_insert_is_insert_ready() {
        let event = MarketEvent {
            event_id: Uuid::new_v4(),
            ts: Utc::now(),
            venue: Venue::Polymarket,
            market_id: "demo-market".to_string(),
            event_type: MarketEventType::Quote,
            best_bid: Some(0.49),
            best_ask: Some(0.50),
            last_trade_price: None,
            bid_size: None,
            ask_size: None,
            quote_age_ms: Some(10),
        };

        let insert = market_event_insert(&event);
        assert_eq!(insert.table, "market_events");
        assert_eq!(insert.columns[1], "event_type");
        assert_eq!(insert.values[1], SqlValue::Text("quote".to_string()));
        assert_eq!(insert.values[5], SqlValue::OptF64(None));
    }

    #[test]
    #[should_panic(expected = "SQL optional f64 values must be finite")]
    fn market_event_insert_rejects_non_finite_values() {
        let event = MarketEvent {
            event_id: Uuid::new_v4(),
            ts: Utc::now(),
            venue: Venue::Polymarket,
            market_id: "demo-market".to_string(),
            event_type: MarketEventType::Quote,
            best_bid: Some(f64::NAN),
            best_ask: Some(0.50),
            last_trade_price: None,
            bid_size: None,
            ask_size: None,
            quote_age_ms: Some(10),
        };

        market_event_insert(&event);
    }

    #[test]
    #[should_panic(expected = "SQL f64 values must be finite")]
    fn signal_event_insert_rejects_non_finite_values() {
        let signal = SignalEvent {
            venue: Venue::Polymarket,
            market_id: "demo-market".to_string(),
            side: OrderSide::BuyYes,
            side_fair_value: f64::INFINITY,
            observed_price: 0.50,
            edge_bps: 400.0,
        };

        signal_event_insert(&signal);
    }

    #[test]
    fn risk_decision_insert_serializes_reasons_json() {
        let decision = RiskDecision {
            decision: RiskDecisionStatus::Rejected,
            reasons: vec!["crossed_or_incomplete_book".to_string()],
        };

        let insert = risk_decision_insert(&decision);
        assert_eq!(insert.table, "risk_decisions");
        assert_eq!(insert.values[0], SqlValue::Text("rejected".to_string()));
        assert!(
            matches!(&insert.values[1], SqlValue::Text(value) if value.contains("crossed_or_incomplete_book"))
        );
    }

    #[test]
    fn order_intent_insert_includes_identifier_and_status() {
        let intent = OrderIntent {
            market_id: "demo-market".to_string(),
            side: OrderSide::BuyYes,
            price: 0.5,
            size: 1.0,
        };

        let insert = order_intent_insert(&intent);

        assert_eq!(insert.table, "order_intents");
        assert_eq!(
            insert.columns,
            vec![
                "local_order_id",
                "market_id",
                "side",
                "price",
                "size",
                "status"
            ]
        );
        assert_eq!(
            insert.values[0],
            SqlValue::Text("intent:demo-market:buy_yes:0.500000:1.000000".to_string())
        );
        assert_eq!(
            insert.values[5],
            SqlValue::Text("advisory_intent".to_string())
        );
    }

    #[test]
    fn execution_report_insert_uses_null_for_missing_message() {
        let report = execution_report_row("demo-market", &ExecutionStatus::Accepted, None);
        let insert = execution_report_insert(&report);

        assert_eq!(insert.table, "execution_reports");
        assert_eq!(insert.values[1], SqlValue::Text("accepted".to_string()));
        assert_eq!(insert.values[2], SqlValue::OptText(None));
    }

    #[test]
    fn postgres_insert_statement_uses_numbered_placeholders() {
        let report = execution_report_row("demo-market", &ExecutionStatus::Accepted, None);
        let statement = execution_report_postgres_insert(&report);

        assert_eq!(
            statement.sql,
            "INSERT INTO execution_reports (market_id, status, message) VALUES ($1, $2, $3)"
        );
        assert_eq!(
            statement.params[0],
            SqlValue::Text("demo-market".to_string())
        );
        assert_eq!(statement.params[1], SqlValue::Text("accepted".to_string()));
        assert_eq!(statement.params[2], SqlValue::OptText(None));
    }

    #[test]
    fn market_event_postgres_insert_builds_table_specific_sql() {
        let event = MarketEvent {
            event_id: Uuid::new_v4(),
            ts: Utc::now(),
            venue: Venue::Polymarket,
            market_id: "demo-market".to_string(),
            event_type: MarketEventType::Quote,
            best_bid: Some(0.49),
            best_ask: Some(0.50),
            last_trade_price: None,
            bid_size: None,
            ask_size: None,
            quote_age_ms: Some(10),
        };

        let statement = market_event_postgres_insert(&event);
        assert!(statement.sql.starts_with("INSERT INTO market_events"));
        assert!(statement.sql.contains("$1"));
        assert!(statement.sql.contains("$2"));
        assert_eq!(statement.params[1], SqlValue::Text("quote".to_string()));
    }

    #[test]
    fn market_event_ledger_serializes_kind_marker() {
        let event = MarketEvent {
            event_id: Uuid::new_v4(),
            ts: Utc::now(),
            venue: Venue::Polymarket,
            market_id: "demo-market".to_string(),
            event_type: MarketEventType::Quote,
            best_bid: Some(0.49),
            best_ask: Some(0.50),
            last_trade_price: None,
            bid_size: None,
            ask_size: None,
            quote_age_ms: Some(10),
        };

        let payload = market_event_ledger(&event).expect("expected json payload");
        assert!(payload.contains("\"kind\":\"market_event\""));
        assert!(payload.contains("\"event_type\":\"quote\""));
    }
}
