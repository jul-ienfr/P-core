use pm_book::estimate_fill_from_book as rust_estimate_fill_from_book;
use pm_executor::compute_order_size as rust_compute_order_size;
use pm_ledger::{
    fee_amount as rust_paper_fee_amount, paper_opening_cost_state as rust_paper_opening_cost_state,
    refresh_pnl as rust_paper_refresh_pnl, settlement_pnl as rust_paper_settlement_pnl,
};
use pm_risk::evaluate_execution_risk as rust_evaluate_execution_risk;
use pm_signal::calculate_edge_sizing as rust_calculate_edge_sizing;
use pm_types::{BookLevel, BookSide, OrderBookSnapshot};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

#[pyfunction]
fn estimate_fill_from_book<'py>(
    py: Python<'py>,
    book: &Bound<'_, PyAny>,
    side: &str,
    requested_quantity: f64,
) -> PyResult<Bound<'py, PyDict>> {
    let snapshot = parse_snapshot(book)?;
    let side = parse_side(side)?;
    let estimate = rust_estimate_fill_from_book(&snapshot, side, requested_quantity);
    let result = PyDict::new_bound(py);
    result.set_item("requested_quantity", estimate.requested_quantity)?;
    result.set_item("filled_quantity", estimate.filled_quantity)?;
    result.set_item("unfilled_quantity", estimate.unfilled_quantity)?;
    result.set_item("gross_notional", estimate.gross_notional)?;
    result.set_item("average_price", estimate.average_price)?;
    result.set_item("top_of_book_price", estimate.top_of_book_price)?;
    result.set_item("slippage_cost", estimate.slippage_cost)?;
    result.set_item("slippage_bps", estimate.slippage_bps)?;
    result.set_item("levels_consumed", estimate.levels_consumed)?;
    result.set_item("status", estimate.status)?;
    Ok(result)
}

#[pyfunction]
#[pyo3(signature = (prediction_probability, market_price, side="buy", edge_cost_bps=0.0, kelly_scale=0.25, max_fraction=0.02, min_net_edge=0.015))]
fn calculate_edge_sizing<'py>(
    py: Python<'py>,
    prediction_probability: f64,
    market_price: f64,
    side: &str,
    edge_cost_bps: f64,
    kelly_scale: f64,
    max_fraction: f64,
    min_net_edge: f64,
) -> PyResult<Bound<'py, PyDict>> {
    let sizing = rust_calculate_edge_sizing(
        prediction_probability,
        market_price,
        side,
        edge_cost_bps,
        kelly_scale,
        max_fraction,
        min_net_edge,
    )
    .map_err(PyValueError::new_err)?;
    let result = PyDict::new_bound(py);
    result.set_item("prediction_probability", sizing.prediction_probability)?;
    result.set_item("market_price", sizing.market_price)?;
    result.set_item("side", sizing.side)?;
    result.set_item("raw_edge", sizing.raw_edge)?;
    result.set_item("net_edge", sizing.net_edge)?;
    result.set_item("edge_bps", sizing.edge_bps)?;
    result.set_item("net_edge_bps", sizing.net_edge_bps)?;
    result.set_item("kelly_fraction", sizing.kelly_fraction)?;
    result.set_item("suggested_fraction", sizing.suggested_fraction)?;
    result.set_item("recommendation", sizing.recommendation)?;
    Ok(result)
}

#[pyfunction]
#[pyo3(signature = (order_notional_usdc, total_exposure_usdc, daily_realized_pnl_usdc, max_order_notional_usdc, max_total_exposure_usdc, max_daily_loss_usdc, max_spread, spread=None))]
fn evaluate_execution_risk<'py>(
    py: Python<'py>,
    order_notional_usdc: f64,
    total_exposure_usdc: f64,
    daily_realized_pnl_usdc: f64,
    max_order_notional_usdc: f64,
    max_total_exposure_usdc: f64,
    max_daily_loss_usdc: f64,
    max_spread: f64,
    spread: Option<&Bound<'_, PyAny>>,
) -> PyResult<Bound<'py, PyDict>> {
    let (spread_value, invalid_spread) = parse_optional_spread(spread)?;
    let decision = rust_evaluate_execution_risk(
        order_notional_usdc,
        total_exposure_usdc,
        daily_realized_pnl_usdc,
        max_order_notional_usdc,
        max_total_exposure_usdc,
        max_daily_loss_usdc,
        max_spread,
        spread_value,
        invalid_spread,
    )
    .map_err(PyValueError::new_err)?;
    let result = PyDict::new_bound(py);
    result.set_item("allowed", decision.allowed)?;
    result.set_item("blocked_by", decision.blocked_by)?;
    Ok(result)
}

#[pyfunction]
fn compute_order_size(
    notional_usdc: f64,
    limit_price: f64,
    min_order_size: f64,
    size_tick: f64,
) -> PyResult<f64> {
    rust_compute_order_size(notional_usdc, limit_price, min_order_size, size_tick)
        .map_err(PyValueError::new_err)
}

#[pyfunction]
fn paper_fee_amount(notional: f64, bps: f64, fixed: f64) -> PyResult<f64> {
    rust_paper_fee_amount(notional, bps, fixed).map_err(PyValueError::new_err)
}

#[pyfunction]
#[pyo3(signature = (filled_usdc, top_ask=None, avg_fill_price=None, shares=0.0, mtm_usdc=0.0, opening_fee_bps=0.0, opening_fixed_fee_usdc=0.0, estimated_exit_fee_bps=0.0, estimated_exit_fixed_fee_usdc=0.0))]
fn paper_opening_cost_state<'py>(
    py: Python<'py>,
    filled_usdc: f64,
    top_ask: Option<f64>,
    avg_fill_price: Option<f64>,
    shares: f64,
    mtm_usdc: f64,
    opening_fee_bps: f64,
    opening_fixed_fee_usdc: f64,
    estimated_exit_fee_bps: f64,
    estimated_exit_fixed_fee_usdc: f64,
) -> PyResult<Bound<'py, PyDict>> {
    let cost = rust_paper_opening_cost_state(
        filled_usdc,
        top_ask,
        avg_fill_price,
        shares,
        mtm_usdc,
        opening_fee_bps,
        opening_fixed_fee_usdc,
        estimated_exit_fee_bps,
        estimated_exit_fixed_fee_usdc,
    )
    .map_err(PyValueError::new_err)?;
    let result = PyDict::new_bound(py);
    result.set_item("opening_trading_fee_usdc", cost.opening_trading_fee_usdc)?;
    result.set_item("opening_fixed_fee_usdc", cost.opening_fixed_fee_usdc)?;
    result.set_item("opening_fee_usdc", cost.opening_fee_usdc)?;
    result.set_item("slippage_usdc", cost.slippage_usdc)?;
    result.set_item("all_in_entry_cost_usdc", cost.all_in_entry_cost_usdc)?;
    result.set_item(
        "estimated_exit_fixed_fee_usdc",
        cost.estimated_exit_fixed_fee_usdc,
    )?;
    result.set_item("estimated_exit_fee_bps", cost.estimated_exit_fee_bps)?;
    result.set_item("estimated_exit_fee_usdc", cost.estimated_exit_fee_usdc)?;
    result.set_item("paper_exit_value_usdc", cost.paper_exit_value_usdc)?;
    Ok(result)
}

#[pyfunction]
#[pyo3(signature = (mtm_usdc, all_in_entry_cost_usdc, estimated_exit_fee_usdc, realized_exit_fee_usdc=None))]
fn paper_refresh_pnl(
    mtm_usdc: f64,
    all_in_entry_cost_usdc: f64,
    estimated_exit_fee_usdc: f64,
    realized_exit_fee_usdc: Option<f64>,
) -> PyResult<f64> {
    rust_paper_refresh_pnl(
        mtm_usdc,
        all_in_entry_cost_usdc,
        estimated_exit_fee_usdc,
        realized_exit_fee_usdc,
    )
    .map_err(PyValueError::new_err)
}

#[pyfunction]
fn paper_settlement_pnl<'py>(
    py: Python<'py>,
    shares: f64,
    all_in_entry_cost_usdc: f64,
    filled_usdc: f64,
    won: bool,
) -> PyResult<Bound<'py, PyDict>> {
    let settlement = rust_paper_settlement_pnl(shares, all_in_entry_cost_usdc, filled_usdc, won)
        .map_err(PyValueError::new_err)?;
    let result = PyDict::new_bound(py);
    result.set_item("status", settlement.status)?;
    result.set_item("mtm_usdc", settlement.mtm_usdc)?;
    result.set_item("pnl_usdc", settlement.pnl_usdc)?;
    result.set_item(
        "net_pnl_after_all_costs",
        settlement.net_pnl_after_all_costs,
    )?;
    Ok(result)
}

#[pymodule]
fn _rust_orderbook(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(estimate_fill_from_book, module)?)?;
    module.add_function(wrap_pyfunction!(calculate_edge_sizing, module)?)?;
    module.add_function(wrap_pyfunction!(evaluate_execution_risk, module)?)?;
    module.add_function(wrap_pyfunction!(compute_order_size, module)?)?;
    module.add_function(wrap_pyfunction!(paper_fee_amount, module)?)?;
    module.add_function(wrap_pyfunction!(paper_opening_cost_state, module)?)?;
    module.add_function(wrap_pyfunction!(paper_refresh_pnl, module)?)?;
    module.add_function(wrap_pyfunction!(paper_settlement_pnl, module)?)?;
    Ok(())
}

fn parse_snapshot(book: &Bound<'_, PyAny>) -> PyResult<OrderBookSnapshot> {
    if let Ok(mapping) = book.downcast::<PyDict>() {
        return Ok(OrderBookSnapshot {
            bids: parse_mapping_levels(mapping, "bids")?,
            asks: parse_mapping_levels(mapping, "asks")?,
        });
    }
    Ok(OrderBookSnapshot {
        bids: parse_attr_levels(book, "bids")?,
        asks: parse_attr_levels(book, "asks")?,
    })
}

fn parse_mapping_levels(book: &Bound<'_, PyDict>, key: &str) -> PyResult<Vec<BookLevel>> {
    let Some(raw_levels) = book.get_item(key)? else {
        return Ok(Vec::new());
    };
    parse_levels(&raw_levels)
}

fn parse_attr_levels(book: &Bound<'_, PyAny>, key: &str) -> PyResult<Vec<BookLevel>> {
    parse_levels(&book.getattr(key)?)
}

fn parse_levels(raw_levels: &Bound<'_, PyAny>) -> PyResult<Vec<BookLevel>> {
    let levels = raw_levels.downcast::<PyList>()?;
    let mut parsed = Vec::with_capacity(levels.len());
    for raw in levels {
        parsed.push(BookLevel {
            price: extract_level_value(&raw, "price")?,
            quantity: extract_level_value(&raw, "quantity")?,
        });
    }
    Ok(parsed)
}

fn extract_level_value(level: &Bound<'_, PyAny>, key: &str) -> PyResult<f64> {
    if let Ok(mapping) = level.downcast::<PyDict>() {
        let Some(value) = mapping.get_item(key)? else {
            return Err(PyValueError::new_err(format!("book level missing {key}")));
        };
        return value.extract::<f64>();
    }
    level.getattr(key)?.extract::<f64>()
}

fn parse_side(side: &str) -> PyResult<BookSide> {
    match side {
        "buy" => Ok(BookSide::Buy),
        "sell" => Ok(BookSide::Sell),
        _ => Err(PyValueError::new_err("side must be buy or sell")),
    }
}

fn parse_optional_spread(spread: Option<&Bound<'_, PyAny>>) -> PyResult<(Option<f64>, bool)> {
    let Some(raw) = spread else {
        return Ok((None, false));
    };
    if raw.is_none() {
        return Ok((None, false));
    }
    match raw.extract::<f64>() {
        Ok(value) => Ok((Some(value), false)),
        Err(_) => Ok((None, true)),
    }
}
