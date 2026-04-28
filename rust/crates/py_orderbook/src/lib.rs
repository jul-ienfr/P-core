use pm_book::estimate_fill_from_book as rust_estimate_fill_from_book;
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

#[pymodule]
fn _rust_orderbook(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(estimate_fill_from_book, module)?)?;
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
