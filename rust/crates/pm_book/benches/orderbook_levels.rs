use std::hint::black_box;
use std::time::{Duration, Instant};

use pm_book::{
    estimate_fill_from_book, normalize_asks, normalize_bids, simulate_exit_value,
    simulate_spend_fill,
};
use pm_types::{BookLevel, BookSide, OrderBookSnapshot};

const ITERATIONS: usize = 10_000;

fn main() {
    for levels in [10_usize, 100, 1_000] {
        let book = make_book(levels);
        report(levels, "normalize_asks", || {
            black_box(normalize_asks(black_box(&book.asks)));
        });
        report(levels, "normalize_bids", || {
            black_box(normalize_bids(black_box(&book.bids)));
        });
        report(levels, "estimate_fill_buy", || {
            black_box(estimate_fill_from_book(
                black_box(&book),
                black_box(BookSide::Buy),
                black_box(levels as f64 / 2.0),
            ));
        });
        report(levels, "simulate_spend_fill", || {
            black_box(simulate_spend_fill(
                black_box(&book),
                black_box(levels as f64 * 0.05),
                black_box(Some(0.99)),
                black_box(None),
            ));
        });
        report(levels, "simulate_exit_value", || {
            black_box(simulate_exit_value(
                black_box(&book),
                black_box(levels as f64 / 2.0),
            ));
        });
    }
}

fn make_book(levels: usize) -> OrderBookSnapshot {
    let mut bids = Vec::with_capacity(levels);
    let mut asks = Vec::with_capacity(levels);

    for index in 0..levels {
        let step = index as f64 * 0.0001;
        bids.push(BookLevel {
            price: 0.49 - step,
            quantity: 1.0 + (index % 7) as f64,
        });
        asks.push(BookLevel {
            price: 0.50 + step,
            quantity: 1.0 + (index % 7) as f64,
        });
    }

    OrderBookSnapshot { bids, asks }
}

fn report<F>(levels: usize, label: &str, mut run_once: F)
where
    F: FnMut(),
{
    let start = Instant::now();
    for _ in 0..ITERATIONS {
        run_once();
    }
    let elapsed = start.elapsed();
    println!(
        "levels={levels:4} op={label:20} iterations={ITERATIONS:6} total_ms={:.3} ns_per_op={:.1}",
        millis(elapsed),
        elapsed.as_nanos() as f64 / ITERATIONS as f64
    );
}

fn millis(duration: Duration) -> f64 {
    duration.as_secs_f64() * 1_000.0
}
