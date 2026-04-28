use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use pm_book::{estimate_fill_from_book, simulate_exit_value, simulate_spend_fill};
use pm_types::{BookLevel, BookSide, OrderBookSnapshot};
use serde::Deserialize;

const EPS: f64 = 1e-6;

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("xtask crate should live under prediction_core/rust")
        .to_path_buf()
}

fn usage() -> &'static str {
    "usage: cargo run -p xtask -- pm-storage-runtime [rust_test_name ...]\n       cargo run -p xtask -- orderbook-parity <fixture-json>"
}

#[derive(Debug, Deserialize)]
struct ParityFixture {
    case_id: String,
    book: FixtureBook,
    polymarket_orderbook: PolymarketBook,
    requests: Requests,
    expected: Expected,
}

#[derive(Debug, Deserialize)]
struct FixtureBook {
    bids: Vec<BookLevel>,
    asks: Vec<BookLevel>,
}

#[derive(Debug, Deserialize)]
struct PolymarketBook {
    no_asks: Vec<PolymarketLevel>,
    no_bids: Vec<PolymarketLevel>,
}

#[derive(Debug, Deserialize)]
struct PolymarketLevel {
    price: f64,
    size: f64,
}

#[derive(Debug, Deserialize)]
struct Requests {
    quantity: f64,
    spend_usdc: f64,
    strict_limit: f64,
    exit_quantity: f64,
}

#[derive(Debug, Deserialize)]
struct Expected {
    estimate_buy: ExpectedFill,
    estimate_sell: ExpectedFill,
    spend_fill: ExpectedSpendFill,
    exit_value: ExpectedExitValue,
}

#[derive(Debug, Deserialize)]
struct ExpectedFill {
    requested_quantity: f64,
    filled_quantity: f64,
    unfilled_quantity: f64,
    gross_notional: f64,
    average_price: Option<f64>,
    top_of_book_price: Option<f64>,
    slippage_cost: f64,
    slippage_bps: f64,
    levels_consumed: usize,
}

#[derive(Debug, Deserialize)]
struct ExpectedSpendFill {
    requested_spend: f64,
    top_ask: Option<f64>,
    avg_fill_price: Option<f64>,
    fillable_spend: f64,
    filled_quantity: f64,
    levels_used: usize,
    slippage_from_top_ask: Option<f64>,
    edge_after_fill: Option<f64>,
    execution_blocker: Option<String>,
    fill_status: String,
}

#[derive(Debug, Deserialize)]
struct ExpectedExitValue {
    requested_quantity: f64,
    filled_quantity: f64,
    unfilled_quantity: f64,
    average_price: Option<f64>,
    value: f64,
    levels_consumed: usize,
    status: String,
}

fn run_pm_storage_runtime(selected_tests: &[String]) -> Result<(), String> {
    let script_name = if selected_tests.is_empty() {
        "check_pm_storage_runtime.sh"
    } else {
        "run_pm_storage_runtime_test.sh"
    };
    let script_path = repo_root().join("scripts").join(script_name);

    let mut command = Command::new(&script_path);
    command.current_dir(repo_root());
    if !selected_tests.is_empty() {
        command.args(selected_tests);
    }

    let status = command
        .status()
        .map_err(|error| format!("failed to launch {}: {error}", script_path.display()))?;

    if status.success() {
        Ok(())
    } else {
        Err(format!(
            "{} exited with status {status}",
            script_path.display()
        ))
    }
}

fn run_orderbook_parity(fixture_path: &Path) -> Result<(), String> {
    let raw = fs::read_to_string(fixture_path)
        .map_err(|error| format!("failed to read {}: {error}", fixture_path.display()))?;
    let fixture: ParityFixture = serde_json::from_str(&raw)
        .map_err(|error| format!("failed to parse {}: {error}", fixture_path.display()))?;

    let book = OrderBookSnapshot {
        bids: fixture.book.bids,
        asks: fixture.book.asks,
    };
    let polymarket_book = OrderBookSnapshot {
        bids: fixture
            .polymarket_orderbook
            .no_bids
            .into_iter()
            .map(|level| BookLevel {
                price: level.price,
                quantity: level.size,
            })
            .collect(),
        asks: fixture
            .polymarket_orderbook
            .no_asks
            .into_iter()
            .map(|level| BookLevel {
                price: level.price,
                quantity: level.size,
            })
            .collect(),
    };

    let buy = estimate_fill_from_book(&book, BookSide::Buy, fixture.requests.quantity);
    check_fill("estimate_buy", &buy, &fixture.expected.estimate_buy)?;

    let sell = estimate_fill_from_book(&book, BookSide::Sell, fixture.requests.quantity);
    check_fill("estimate_sell", &sell, &fixture.expected.estimate_sell)?;

    let spend = simulate_spend_fill(
        &polymarket_book,
        fixture.requests.spend_usdc,
        Some(fixture.requests.strict_limit),
        None,
    );
    check_spend_fill("spend_fill", &spend, &fixture.expected.spend_fill)?;

    let exit = simulate_exit_value(&polymarket_book, fixture.requests.exit_quantity);
    check_exit_value("exit_value", &exit, &fixture.expected.exit_value)?;

    println!("orderbook parity ok: {}", fixture.case_id);
    Ok(())
}

fn check_fill(
    label: &str,
    actual: &pm_types::FillEstimate,
    expected: &ExpectedFill,
) -> Result<(), String> {
    check_f64(
        label,
        "requested_quantity",
        actual.requested_quantity,
        expected.requested_quantity,
    )?;
    check_f64(
        label,
        "filled_quantity",
        actual.filled_quantity,
        expected.filled_quantity,
    )?;
    check_f64(
        label,
        "unfilled_quantity",
        actual.unfilled_quantity,
        expected.unfilled_quantity,
    )?;
    check_f64(
        label,
        "gross_notional",
        actual.gross_notional,
        expected.gross_notional,
    )?;
    check_option_f64(
        label,
        "average_price",
        actual.average_price,
        expected.average_price,
    )?;
    check_option_f64(
        label,
        "top_of_book_price",
        actual.top_of_book_price,
        expected.top_of_book_price,
    )?;
    check_f64(
        label,
        "slippage_cost",
        actual.slippage_cost,
        expected.slippage_cost,
    )?;
    check_f64(
        label,
        "slippage_bps",
        actual.slippage_bps,
        expected.slippage_bps,
    )?;
    check_usize(
        label,
        "levels_consumed",
        actual.levels_consumed,
        expected.levels_consumed,
    )
}

fn check_spend_fill(
    label: &str,
    actual: &pm_types::SpendFillEstimate,
    expected: &ExpectedSpendFill,
) -> Result<(), String> {
    check_f64(
        label,
        "requested_spend",
        actual.requested_spend,
        expected.requested_spend,
    )?;
    check_option_f64(label, "top_ask", actual.top_ask, expected.top_ask)?;
    check_option_f64(
        label,
        "avg_fill_price",
        actual.avg_fill_price,
        expected.avg_fill_price,
    )?;
    check_f64(
        label,
        "fillable_spend",
        actual.fillable_spend,
        expected.fillable_spend,
    )?;
    check_f64(
        label,
        "filled_quantity",
        actual.filled_quantity,
        expected.filled_quantity,
    )?;
    check_usize(
        label,
        "levels_used",
        actual.levels_used,
        expected.levels_used,
    )?;
    check_option_f64(
        label,
        "slippage_from_top_ask",
        actual.slippage_from_top_ask,
        expected.slippage_from_top_ask,
    )?;
    check_option_f64(
        label,
        "edge_after_fill",
        actual.edge_after_fill,
        expected.edge_after_fill,
    )?;
    check_option_string(
        label,
        "execution_blocker",
        actual.execution_blocker.as_ref(),
        expected.execution_blocker.as_ref(),
    )?;
    check_string(
        label,
        "fill_status",
        &actual.fill_status,
        &expected.fill_status,
    )
}

fn check_exit_value(
    label: &str,
    actual: &pm_types::ExitValueEstimate,
    expected: &ExpectedExitValue,
) -> Result<(), String> {
    check_f64(
        label,
        "requested_quantity",
        actual.requested_quantity,
        expected.requested_quantity,
    )?;
    check_f64(
        label,
        "filled_quantity",
        actual.filled_quantity,
        expected.filled_quantity,
    )?;
    check_f64(
        label,
        "unfilled_quantity",
        actual.unfilled_quantity,
        expected.unfilled_quantity,
    )?;
    check_option_f64(
        label,
        "average_price",
        actual.average_price,
        expected.average_price,
    )?;
    check_f64(label, "value", actual.value, expected.value)?;
    check_usize(
        label,
        "levels_consumed",
        actual.levels_consumed,
        expected.levels_consumed,
    )?;
    check_string(label, "status", &actual.status, &expected.status)
}

fn check_f64(label: &str, field: &str, actual: f64, expected: f64) -> Result<(), String> {
    if (actual - expected).abs() <= EPS {
        Ok(())
    } else {
        Err(format!(
            "{label}.{field} mismatch: actual={actual} expected={expected}"
        ))
    }
}

fn check_option_f64(
    label: &str,
    field: &str,
    actual: Option<f64>,
    expected: Option<f64>,
) -> Result<(), String> {
    match (actual, expected) {
        (Some(actual), Some(expected)) => check_f64(label, field, actual, expected),
        (None, None) => Ok(()),
        _ => Err(format!(
            "{label}.{field} mismatch: actual={actual:?} expected={expected:?}"
        )),
    }
}

fn check_usize(label: &str, field: &str, actual: usize, expected: usize) -> Result<(), String> {
    if actual == expected {
        Ok(())
    } else {
        Err(format!(
            "{label}.{field} mismatch: actual={actual} expected={expected}"
        ))
    }
}

fn check_option_string(
    label: &str,
    field: &str,
    actual: Option<&String>,
    expected: Option<&String>,
) -> Result<(), String> {
    match (actual, expected) {
        (Some(actual), Some(expected)) => check_string(label, field, actual, expected),
        (None, None) => Ok(()),
        _ => Err(format!(
            "{label}.{field} mismatch: actual={actual:?} expected={expected:?}"
        )),
    }
}

fn check_string(label: &str, field: &str, actual: &str, expected: &str) -> Result<(), String> {
    if actual == expected {
        Ok(())
    } else {
        Err(format!(
            "{label}.{field} mismatch: actual={actual} expected={expected}"
        ))
    }
}

fn main() {
    let mut args = env::args().skip(1);
    let Some(command) = args.next() else {
        eprintln!("{}", usage());
        std::process::exit(1);
    };

    let result = match command.as_str() {
        "pm-storage-runtime" => {
            let selected_tests: Vec<String> = args.collect();
            run_pm_storage_runtime(&selected_tests)
        }
        "orderbook-parity" => {
            let Some(path) = args.next() else {
                exit_with_error("missing fixture path for orderbook-parity".to_string());
            };
            if args.next().is_some() {
                exit_with_error("orderbook-parity accepts exactly one fixture path".to_string());
            }
            run_orderbook_parity(Path::new(&path))
        }
        _ => Err(format!("unknown xtask command: {command}\n{}", usage())),
    };

    if let Err(error) = result {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

fn exit_with_error(error: String) -> ! {
    eprintln!("{error}\n{}", usage());
    std::process::exit(1);
}
