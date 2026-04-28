use chrono::Utc;
use pm_executor::build_order_intent;
use pm_risk::{approve_if_spread_not_crossed, RiskDecision};
use pm_signal::SignalEvent;
use pm_types::{ExecutionStatus, FillEvent, MarketEvent, MarketEventType, OrderSide, Venue};
use sqlx::postgres::{PgConnectOptions, PgPool, PgPoolOptions};
use url::Url;
use uuid::Uuid;

use crate::{
    apply_schema, execute_execution_report, execute_fill, execute_market_event,
    execute_order_intent, execute_risk_decision, execute_signal_event, execution_report_row,
};

fn assert_local_database_url(database_url: &str) -> Result<(), Box<dyn std::error::Error>> {
    let parsed = Url::parse(database_url)?;
    let host = parsed.host_str().unwrap_or_default();
    if matches!(host, "localhost" | "127.0.0.1" | "::1") {
        Ok(())
    } else {
        Err(format!(
            "runtime integration tests require a localhost DATABASE_URL, got host '{host}'"
        )
        .into())
    }
}

async fn isolated_pool() -> Result<(PgPool, String), Box<dyn std::error::Error>> {
    if std::env::var("PM_STORAGE_ALLOW_DESTRUCTIVE_DB_TESTS").as_deref() != Ok("1") {
        panic!("PM_STORAGE_ALLOW_DESTRUCTIVE_DB_TESTS=1 is required for runtime integration tests");
    }
    let database_url = std::env::var("DATABASE_URL").expect(
        "DATABASE_URL must point to a live Postgres instance for runtime integration tests",
    );
    assert_local_database_url(&database_url)?;

    let schema = format!("pm_storage_test_{}", Uuid::new_v4().simple());
    let bootstrap_pool = PgPoolOptions::new()
        .max_connections(1)
        .connect(&database_url)
        .await?;
    sqlx::query(&format!("CREATE SCHEMA {schema}"))
        .execute(&bootstrap_pool)
        .await?;

    let setup_result = async {
        let mut options: PgConnectOptions = database_url.parse()?;
        options = options.options([("search_path", schema.as_str())]);
        PgPoolOptions::new()
            .max_connections(1)
            .connect_with(options)
            .await
    }
    .await;

    match setup_result {
        Ok(pool) => {
            bootstrap_pool.close().await;
            Ok((pool, schema))
        }
        Err(error) => {
            drop_schema(&bootstrap_pool, &schema).await?;
            bootstrap_pool.close().await;
            Err(Box::new(error))
        }
    }
}

async fn run_isolated<F, Fut>(test: F) -> Result<(), Box<dyn std::error::Error>>
where
    F: FnOnce(PgPool) -> Fut,
    Fut: std::future::Future<Output = Result<(), Box<dyn std::error::Error>>>,
{
    let (pool, schema) = isolated_pool().await?;
    let result = test(pool.clone()).await;
    let cleanup = drop_schema(&pool, &schema).await;
    pool.close().await;
    result?;
    cleanup?;
    Ok(())
}

async fn drop_schema(pool: &PgPool, schema: &str) -> Result<(), sqlx::Error> {
    sqlx::query(&format!("DROP SCHEMA IF EXISTS {schema} CASCADE"))
        .execute(pool)
        .await?;
    Ok(())
}

fn sample_market_event() -> MarketEvent {
    MarketEvent {
        event_id: Uuid::new_v4(),
        ts: Utc::now(),
        venue: Venue::Polymarket,
        market_id: "runtime-demo-market".to_string(),
        event_type: MarketEventType::BookSnapshot,
        best_bid: Some(0.49),
        best_ask: Some(0.50),
        last_trade_price: Some(0.495),
        bid_size: Some(50.0),
        ask_size: Some(40.0),
        quote_age_ms: Some(12),
    }
}

fn sample_signal() -> SignalEvent {
    SignalEvent {
        venue: Venue::Polymarket,
        market_id: "runtime-demo-market".to_string(),
        side: OrderSide::BuyYes,
        side_fair_value: 0.52,
        observed_price: 0.50,
        edge_bps: 400.0,
    }
}

fn sample_risk_decision() -> RiskDecision {
    approve_if_spread_not_crossed(Some(0.49), Some(0.50))
}

fn sample_fill() -> FillEvent {
    FillEvent {
        market_id: "runtime-demo-market".to_string(),
        side: OrderSide::BuyYes,
        price: 0.50,
        size: 1.0,
    }
}

#[tokio::test]
#[ignore = "requires DATABASE_URL"]
async fn sqlx_runtime_executes_against_real_postgres() -> Result<(), Box<dyn std::error::Error>> {
    run_isolated(|pool| async move {
        apply_schema(&pool).await?;

        let market_event = sample_market_event();
        let signal = sample_signal();
        let decision = sample_risk_decision();
        let order_intent = build_order_intent("runtime-demo-market", OrderSide::BuyYes, 0.50);
        let fill = sample_fill();
        let report = execution_report_row(
            "runtime-demo-market",
            &ExecutionStatus::Accepted,
            Some("runtime integration ok".to_string()),
        );

        execute_market_event(&pool, &market_event).await?;
        execute_signal_event(&pool, &signal).await?;
        execute_risk_decision(&pool, &decision).await?;
        execute_order_intent(&pool, &order_intent).await?;
        execute_fill(&pool, &fill).await?;
        execute_execution_report(&pool, &report).await?;

        let market_events: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM market_events")
            .fetch_one(&pool)
            .await?;
        let signal_events: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM signal_events")
            .fetch_one(&pool)
            .await?;
        let risk_decisions: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM risk_decisions")
            .fetch_one(&pool)
            .await?;
        let order_intents: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM order_intents")
            .fetch_one(&pool)
            .await?;
        let fills: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM fills")
            .fetch_one(&pool)
            .await?;
        let execution_reports: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM execution_reports")
            .fetch_one(&pool)
            .await?;
        let stored_message: Option<String> = sqlx::query_scalar(
            "SELECT message FROM execution_reports WHERE market_id = 'runtime-demo-market' LIMIT 1",
        )
        .fetch_one(&pool)
        .await?;

        assert_eq!(market_events, 1);
        assert_eq!(signal_events, 1);
        assert_eq!(risk_decisions, 1);
        assert_eq!(order_intents, 1);
        assert_eq!(fills, 1);
        assert_eq!(execution_reports, 1);
        assert_eq!(stored_message.as_deref(), Some("runtime integration ok"));
        Ok(())
    })
    .await
}

#[tokio::test]
#[ignore = "requires DATABASE_URL"]
async fn sqlx_runtime_allows_repeated_schema_apply_against_real_postgres(
) -> Result<(), Box<dyn std::error::Error>> {
    run_isolated(|pool| async move {
        apply_schema(&pool).await?;
        let second_apply = apply_schema(&pool).await;

        assert!(second_apply.is_ok());

        let market_events: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM market_events")
            .fetch_one(&pool)
            .await?;
        let signal_events: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM signal_events")
            .fetch_one(&pool)
            .await?;
        let risk_decisions: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM risk_decisions")
            .fetch_one(&pool)
            .await?;
        let order_intents: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM order_intents")
            .fetch_one(&pool)
            .await?;
        let fills: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM fills")
            .fetch_one(&pool)
            .await?;
        let execution_reports: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM execution_reports")
            .fetch_one(&pool)
            .await?;

        assert_eq!(market_events, 0);
        assert_eq!(signal_events, 0);
        assert_eq!(risk_decisions, 0);
        assert_eq!(order_intents, 0);
        assert_eq!(fills, 0);
        assert_eq!(execution_reports, 0);
        Ok(())
    })
    .await
}

#[tokio::test]
#[ignore = "requires DATABASE_URL"]
async fn sqlx_runtime_preserves_insertability_after_repeated_schema_apply_against_real_postgres(
) -> Result<(), Box<dyn std::error::Error>> {
    run_isolated(|pool| async move {
        apply_schema(&pool).await?;
        apply_schema(&pool).await?;

        let market_event = sample_market_event();
        execute_market_event(&pool, &market_event).await?;

        let market_events: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM market_events")
            .fetch_one(&pool)
            .await?;
        let stored_market_id: String =
            sqlx::query_scalar("SELECT market_id FROM market_events WHERE event_id = $1 LIMIT 1")
                .bind(market_event.event_id.to_string())
                .fetch_one(&pool)
                .await?;

        assert_eq!(market_events, 1);
        assert_eq!(stored_market_id, market_event.market_id);
        Ok(())
    })
    .await
}

#[tokio::test]
#[ignore = "requires DATABASE_URL"]
async fn sqlx_runtime_rejects_duplicate_market_event_insert_against_real_postgres(
) -> Result<(), Box<dyn std::error::Error>> {
    run_isolated(|pool| async move {
        apply_schema(&pool).await?;

        let market_event = sample_market_event();
        execute_market_event(&pool, &market_event).await?;
        let duplicate_insert = execute_market_event(&pool, &market_event).await;

        assert!(duplicate_insert.is_err());
        let error_text = duplicate_insert.unwrap_err().to_string();
        assert!(
            error_text.contains("duplicate key value violates unique constraint")
                || error_text.contains("23505")
        );
        Ok(())
    })
    .await
}

#[tokio::test]
#[ignore = "requires DATABASE_URL"]
async fn sqlx_runtime_rolls_back_transaction_against_real_postgres(
) -> Result<(), Box<dyn std::error::Error>> {
    run_isolated(|pool| async move {
        apply_schema(&pool).await?;

        let market_event = sample_market_event();
        let signal = sample_signal();

        let mut tx = pool.begin().await?;
        execute_market_event(&mut *tx, &market_event).await?;
        execute_signal_event(&mut *tx, &signal).await?;
        tx.rollback().await?;

        let market_events: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM market_events")
            .fetch_one(&pool)
            .await?;
        let signal_events: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM signal_events")
            .fetch_one(&pool)
            .await?;

        assert_eq!(market_events, 0);
        assert_eq!(signal_events, 0);
        Ok(())
    })
    .await
}

#[tokio::test]
#[ignore = "requires DATABASE_URL"]
async fn sqlx_runtime_commits_multi_table_transaction_against_real_postgres(
) -> Result<(), Box<dyn std::error::Error>> {
    run_isolated(|pool| async move {
        apply_schema(&pool).await?;

        let market_event = sample_market_event();
        let signal = sample_signal();
        let decision = sample_risk_decision();
        let order_intent = build_order_intent("runtime-demo-market", OrderSide::BuyYes, 0.50);

        let mut tx = pool.begin().await?;
        execute_market_event(&mut *tx, &market_event).await?;
        execute_signal_event(&mut *tx, &signal).await?;
        execute_risk_decision(&mut *tx, &decision).await?;
        execute_order_intent(&mut *tx, &order_intent).await?;
        tx.commit().await?;

        let market_events: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM market_events")
            .fetch_one(&pool)
            .await?;
        let signal_events: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM signal_events")
            .fetch_one(&pool)
            .await?;
        let risk_decisions: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM risk_decisions")
            .fetch_one(&pool)
            .await?;
        let order_intents: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM order_intents")
            .fetch_one(&pool)
            .await?;

        assert_eq!(market_events, 1);
        assert_eq!(signal_events, 1);
        assert_eq!(risk_decisions, 1);
        assert_eq!(order_intents, 1);
        Ok(())
    })
    .await
}
