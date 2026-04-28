use pm_types::{
    BookLevel, BookSide, ExitValueEstimate, FillEstimate, MarketEvent, OrderBookSnapshot,
    SpendFillEstimate,
};

#[derive(Debug, Clone, Default)]
pub struct TopOfBook {
    pub best_bid: Option<f64>,
    pub best_ask: Option<f64>,
}

impl TopOfBook {
    pub fn apply(&mut self, event: &MarketEvent) {
        if let Some(v) = event.best_bid {
            if valid_price(v) {
                self.best_bid = Some(v);
            }
        }
        if let Some(v) = event.best_ask {
            if valid_price(v) {
                self.best_ask = Some(v);
            }
        }
    }

    pub fn mid_price(&self) -> Option<f64> {
        match (self.best_bid, self.best_ask) {
            (Some(bid), Some(ask)) if valid_price(bid) && valid_price(ask) && ask >= bid => {
                Some((bid + ask) / 2.0)
            }
            _ => None,
        }
    }
}

pub fn normalize_asks(levels: &[BookLevel]) -> Vec<BookLevel> {
    let mut normalized: Vec<BookLevel> = levels
        .iter()
        .filter(|level| valid_level(level))
        .cloned()
        .collect();
    normalized.sort_by(|a, b| a.price.total_cmp(&b.price));
    normalized
}

pub fn normalize_bids(levels: &[BookLevel]) -> Vec<BookLevel> {
    let mut normalized: Vec<BookLevel> = levels
        .iter()
        .filter(|level| valid_level(level))
        .cloned()
        .collect();
    normalized.sort_by(|a, b| b.price.total_cmp(&a.price));
    normalized
}

pub fn estimate_fill_from_book(
    book: &OrderBookSnapshot,
    side: BookSide,
    requested_quantity: f64,
) -> FillEstimate {
    let requested_quantity = finite_non_negative(requested_quantity);
    let levels = match side {
        BookSide::Buy => normalize_asks(&book.asks),
        BookSide::Sell => normalize_bids(&book.bids),
    };
    let top_of_book_price = levels.first().map(|level| level.price);
    let (filled_quantity, gross_notional, levels_consumed) =
        consume_quantity(&levels, requested_quantity);
    let average_price = (filled_quantity > 0.0).then_some(round6(gross_notional / filled_quantity));
    let mut slippage_cost = 0.0;
    let mut slippage_bps = 0.0;

    if let (Some(top), true) = (top_of_book_price, filled_quantity > 0.0) {
        let reference_notional = top * filled_quantity;
        slippage_cost = match side {
            BookSide::Buy => gross_notional - reference_notional,
            BookSide::Sell => reference_notional - gross_notional,
        };
        slippage_cost = round6(slippage_cost.max(0.0));
        if reference_notional > 0.0 {
            slippage_bps = round2((slippage_cost / reference_notional) * 10000.0);
        }
    }

    FillEstimate {
        side,
        requested_quantity: round6(requested_quantity),
        filled_quantity: round6(filled_quantity),
        unfilled_quantity: round6((requested_quantity - filled_quantity).max(0.0)),
        gross_notional: round6(gross_notional),
        average_price,
        top_of_book_price,
        slippage_cost,
        slippage_bps,
        levels_consumed,
        status: fill_status(levels.is_empty(), filled_quantity, requested_quantity).to_string(),
    }
}

pub fn simulate_spend_fill(
    book: &OrderBookSnapshot,
    spend: f64,
    strict_limit_price: Option<f64>,
    probability_edge: Option<f64>,
) -> SpendFillEstimate {
    let requested_spend = round6(finite_non_negative(spend));
    let asks = normalize_asks(&book.asks);

    if requested_spend <= 0.0 || asks.is_empty() {
        return SpendFillEstimate {
            requested_spend,
            top_ask: None,
            avg_fill_price: None,
            fillable_spend: 0.0,
            filled_quantity: 0.0,
            levels_used: 0,
            slippage_from_top_ask: None,
            edge_after_fill: None,
            execution_blocker: Some("missing_tradeable_quote".to_string()),
            fill_status: "empty_book".to_string(),
        };
    }

    let top_ask = asks[0].price;
    let (filled_quantity, filled_spend, levels_used) = consume_spend(&asks, requested_spend);
    let avg_fill_price = (filled_quantity > 0.0).then_some(round6(filled_spend / filled_quantity));
    let slippage_from_top_ask = avg_fill_price.map(|price| round6(price - top_ask));
    let edge_after_fill = match (probability_edge, slippage_from_top_ask) {
        (Some(edge), Some(slippage)) if edge.is_finite() => Some(round6(edge - slippage)),
        _ => None,
    };
    let fill_status = if filled_spend + 0.000000001 >= requested_spend {
        "filled"
    } else {
        "partial_fill"
    };
    let execution_blocker =
        if strict_limit_price.is_some_and(|limit| limit.is_finite() && top_ask > limit) {
            Some("strict_limit_price_exceeded".to_string())
        } else if fill_status != "filled" {
            Some("insufficient_executable_depth".to_string())
        } else if matches!(edge_after_fill, Some(edge) if edge <= 0.0) {
            Some("edge_destroyed_by_fill".to_string())
        } else {
            None
        };

    SpendFillEstimate {
        requested_spend,
        top_ask: Some(round6(top_ask)),
        avg_fill_price,
        fillable_spend: round6(filled_spend),
        filled_quantity: round6(filled_quantity),
        levels_used,
        slippage_from_top_ask,
        edge_after_fill,
        execution_blocker,
        fill_status: fill_status.to_string(),
    }
}

pub fn simulate_exit_value(book: &OrderBookSnapshot, requested_quantity: f64) -> ExitValueEstimate {
    let requested_quantity = finite_non_negative(requested_quantity);
    let bids = normalize_bids(&book.bids);
    let (filled_quantity, value, levels_consumed) = consume_quantity(&bids, requested_quantity);
    let average_price = (filled_quantity > 0.0).then_some(round6(value / filled_quantity));

    ExitValueEstimate {
        requested_quantity: round6(requested_quantity),
        filled_quantity: round6(filled_quantity),
        unfilled_quantity: round6((requested_quantity - filled_quantity).max(0.0)),
        average_price,
        value: round6(value),
        levels_consumed,
        status: fill_status(bids.is_empty(), filled_quantity, requested_quantity).to_string(),
    }
}

fn consume_quantity(levels: &[BookLevel], requested_quantity: f64) -> (f64, f64, usize) {
    let mut remaining = requested_quantity;
    let mut filled_quantity = 0.0;
    let mut notional = 0.0;
    let mut levels_consumed = 0;

    for level in levels {
        if remaining <= 0.0 {
            break;
        }
        let quantity = level.quantity.min(remaining);
        if quantity <= 0.0 {
            continue;
        }
        filled_quantity += quantity;
        notional += quantity * level.price;
        remaining -= quantity;
        levels_consumed += 1;
    }

    (filled_quantity, notional, levels_consumed)
}

fn consume_spend(levels: &[BookLevel], spend: f64) -> (f64, f64, usize) {
    let mut remaining = spend;
    let mut filled_quantity = 0.0;
    let mut notional = 0.0;
    let mut levels_used = 0;

    for level in levels {
        if remaining <= 0.000000000001 {
            break;
        }
        let spend_at_level = remaining.min(level.price * level.quantity);
        if spend_at_level <= 0.0 {
            continue;
        }
        filled_quantity += spend_at_level / level.price;
        notional += spend_at_level;
        remaining -= spend_at_level;
        levels_used += 1;
    }

    (filled_quantity, notional, levels_used)
}

fn fill_status(empty_book: bool, filled: f64, requested: f64) -> &'static str {
    if empty_book {
        "empty_book"
    } else if filled >= requested && requested > 0.0 {
        "filled"
    } else {
        "partial"
    }
}

fn valid_level(level: &BookLevel) -> bool {
    valid_price(level.price)
        && level.price > 0.0
        && level.quantity.is_finite()
        && level.quantity > 0.0
}

fn valid_price(value: f64) -> bool {
    value.is_finite() && (0.0..=1.0).contains(&value)
}

fn finite_non_negative(value: f64) -> f64 {
    if value.is_finite() {
        value.max(0.0)
    } else {
        0.0
    }
}

fn round6(value: f64) -> f64 {
    (value * 1_000_000.0).round() / 1_000_000.0
}

fn round2(value: f64) -> f64 {
    (value * 100.0).round() / 100.0
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use pm_types::{MarketEvent, MarketEventType, Venue};
    use uuid::Uuid;

    fn quote_event(best_bid: Option<f64>, best_ask: Option<f64>) -> MarketEvent {
        MarketEvent {
            event_id: Uuid::new_v4(),
            ts: Utc::now(),
            venue: Venue::Polymarket,
            market_id: "demo-market".to_string(),
            event_type: MarketEventType::Quote,
            best_bid,
            best_ask,
            last_trade_price: None,
            bid_size: None,
            ask_size: None,
            quote_age_ms: Some(100),
        }
    }

    fn level(price: f64, quantity: f64) -> BookLevel {
        BookLevel { price, quantity }
    }

    fn book(bids: Vec<BookLevel>, asks: Vec<BookLevel>) -> OrderBookSnapshot {
        OrderBookSnapshot { bids, asks }
    }

    #[test]
    fn apply_updates_top_of_book_from_event() {
        let mut book = TopOfBook::default();

        book.apply(&quote_event(Some(0.47), Some(0.49)));

        assert_eq!(book.best_bid, Some(0.47));
        assert_eq!(book.best_ask, Some(0.49));
    }

    #[test]
    fn mid_price_returns_mean_for_valid_book() {
        let book = TopOfBook {
            best_bid: Some(0.47),
            best_ask: Some(0.49),
        };

        assert_eq!(book.mid_price(), Some(0.48));
    }

    #[test]
    fn mid_price_returns_none_for_crossed_book() {
        let book = TopOfBook {
            best_bid: Some(0.51),
            best_ask: Some(0.49),
        };

        assert_eq!(book.mid_price(), None);
    }

    #[test]
    fn apply_ignores_non_finite_prices() {
        let mut book = TopOfBook::default();

        book.apply(&quote_event(Some(f64::NAN), Some(f64::INFINITY)));

        assert_eq!(book.best_bid, None);
        assert_eq!(book.best_ask, None);
        assert_eq!(book.mid_price(), None);
    }

    #[test]
    fn invalid_quote_update_does_not_clear_existing_top_of_book() {
        let mut book = TopOfBook::default();
        book.apply(&quote_event(Some(0.47), Some(0.49)));

        book.apply(&quote_event(Some(f64::NAN), Some(1.2)));

        assert_eq!(book.best_bid, Some(0.47));
        assert_eq!(book.best_ask, Some(0.49));
    }

    #[test]
    fn single_ask_fill() {
        let estimate =
            estimate_fill_from_book(&book(vec![], vec![level(0.5, 10.0)]), BookSide::Buy, 4.0);

        assert_eq!(estimate.requested_quantity, 4.0);
        assert_eq!(estimate.filled_quantity, 4.0);
        assert_eq!(estimate.unfilled_quantity, 0.0);
        assert_eq!(estimate.gross_notional, 2.0);
        assert_eq!(estimate.average_price, Some(0.5));
        assert_eq!(estimate.top_of_book_price, Some(0.5));
        assert_eq!(estimate.slippage_cost, 0.0);
        assert_eq!(estimate.slippage_bps, 0.0);
        assert_eq!(estimate.levels_consumed, 1);
        assert_eq!(estimate.status, "filled");
    }

    #[test]
    fn multi_level_buy_fill_consumes_asks_ascending() {
        let estimate = estimate_fill_from_book(
            &book(vec![], vec![level(0.6, 5.0), level(0.5, 5.0)]),
            BookSide::Buy,
            8.0,
        );

        assert_eq!(estimate.filled_quantity, 8.0);
        assert_eq!(estimate.average_price, Some(0.5375));
        assert_eq!(estimate.slippage_cost, 0.3);
        assert_eq!(estimate.gross_notional, 4.3);
        assert_eq!(estimate.unfilled_quantity, 0.0);
        assert_eq!(estimate.slippage_bps, 750.0);
        assert_eq!(estimate.levels_consumed, 2);
    }

    #[test]
    fn multi_level_sell_fill_consumes_bids_descending() {
        let estimate = estimate_fill_from_book(
            &book(vec![level(0.4, 5.0), level(0.45, 5.0)], vec![]),
            BookSide::Sell,
            8.0,
        );

        assert_eq!(estimate.filled_quantity, 8.0);
        assert_eq!(estimate.average_price, Some(0.43125));
        assert_eq!(estimate.gross_notional, 3.45);
        assert_eq!(estimate.top_of_book_price, Some(0.45));
        assert_eq!(estimate.slippage_cost, 0.15);
        assert_eq!(estimate.slippage_bps, 416.67);
        assert_eq!(estimate.levels_consumed, 2);
    }

    #[test]
    fn partial_fill() {
        let estimate =
            estimate_fill_from_book(&book(vec![], vec![level(0.5, 3.0)]), BookSide::Buy, 5.0);

        assert_eq!(estimate.filled_quantity, 3.0);
        assert_eq!(estimate.unfilled_quantity, 2.0);
        assert_eq!(estimate.gross_notional, 1.5);
        assert_eq!(estimate.status, "partial");
    }

    #[test]
    fn empty_book_fill() {
        let estimate = estimate_fill_from_book(&book(vec![], vec![]), BookSide::Buy, 5.0);

        assert_eq!(estimate.filled_quantity, 0.0);
        assert_eq!(estimate.unfilled_quantity, 5.0);
        assert_eq!(estimate.gross_notional, 0.0);
        assert_eq!(estimate.average_price, None);
        assert_eq!(estimate.slippage_bps, 0.0);
        assert_eq!(estimate.status, "empty_book");
    }

    #[test]
    fn invalid_levels_are_ignored() {
        let estimate = estimate_fill_from_book(
            &book(
                vec![],
                vec![
                    level(f64::NAN, 10.0),
                    level(0.0, 10.0),
                    level(1.2, 10.0),
                    level(0.5, -1.0),
                    level(0.6, 2.0),
                ],
            ),
            BookSide::Buy,
            2.0,
        );

        assert_eq!(estimate.filled_quantity, 2.0);
        assert_eq!(estimate.average_price, Some(0.6));
    }

    #[test]
    fn strict_limit_blocks_spend_fill() {
        let estimate =
            simulate_spend_fill(&book(vec![], vec![level(0.6, 10.0)]), 1.0, Some(0.5), None);

        assert_eq!(estimate.fillable_spend, 1.0);
        assert_eq!(
            estimate.execution_blocker,
            Some("strict_limit_price_exceeded".to_string())
        );
        assert_eq!(estimate.fill_status, "filled");
    }

    #[test]
    fn edge_destroyed_blocks_spend_fill() {
        let estimate = simulate_spend_fill(
            &book(vec![], vec![level(0.5, 5.0), level(0.6, 5.0)]),
            4.0,
            None,
            Some(0.01),
        );

        assert_eq!(
            estimate.execution_blocker,
            Some("edge_destroyed_by_fill".to_string())
        );
        assert_eq!(estimate.edge_after_fill, Some(-0.023333));
        assert_eq!(estimate.fill_status, "filled");
    }

    #[test]
    fn exit_value_consumes_bids() {
        let estimate =
            simulate_exit_value(&book(vec![level(0.4, 5.0), level(0.45, 5.0)], vec![]), 8.0);

        assert_eq!(estimate.filled_quantity, 8.0);
        assert_eq!(estimate.unfilled_quantity, 0.0);
        assert_eq!(estimate.average_price, Some(0.43125));
        assert_eq!(estimate.value, 3.45);
        assert_eq!(estimate.levels_consumed, 2);
        assert_eq!(estimate.status, "filled");
    }

    #[test]
    fn shared_parity_fixture_values_match_python_contract() {
        let parity_book = book(
            vec![level(0.42, 12.0), level(0.41, 10.0)],
            vec![level(0.45, 10.0), level(0.46, 15.0)],
        );

        let buy = estimate_fill_from_book(&parity_book, BookSide::Buy, 20.0);
        assert_eq!(buy.requested_quantity, 20.0);
        assert_eq!(buy.filled_quantity, 20.0);
        assert_eq!(buy.unfilled_quantity, 0.0);
        assert_eq!(buy.gross_notional, 9.1);
        assert_eq!(buy.average_price, Some(0.455));
        assert_eq!(buy.top_of_book_price, Some(0.45));
        assert_eq!(buy.slippage_cost, 0.1);
        assert_eq!(buy.slippage_bps, 111.11);
        assert_eq!(buy.levels_consumed, 2);

        let sell = estimate_fill_from_book(&parity_book, BookSide::Sell, 20.0);
        assert_eq!(sell.requested_quantity, 20.0);
        assert_eq!(sell.filled_quantity, 20.0);
        assert_eq!(sell.unfilled_quantity, 0.0);
        assert_eq!(sell.gross_notional, 8.32);
        assert_eq!(sell.average_price, Some(0.416));
        assert_eq!(sell.top_of_book_price, Some(0.42));
        assert_eq!(sell.slippage_cost, 0.08);
        assert_eq!(sell.slippage_bps, 95.24);
        assert_eq!(sell.levels_consumed, 2);

        let polymarket_book = book(
            vec![level(0.43, 7.85715), level(0.41, 20.0)],
            vec![level(0.28, 20.0), level(0.30, 20.0)],
        );
        let spend = simulate_spend_fill(&polymarket_book, 10.0, Some(0.30), None);
        assert_eq!(spend.requested_spend, 10.0);
        assert_eq!(spend.top_ask, Some(0.28));
        assert_eq!(spend.avg_fill_price, Some(0.288462));
        assert_eq!(spend.fillable_spend, 10.0);
        assert_eq!(spend.filled_quantity, 34.666667);
        assert_eq!(spend.levels_used, 2);
        assert_eq!(spend.slippage_from_top_ask, Some(0.008462));
        assert_eq!(spend.edge_after_fill, None);
        assert_eq!(spend.execution_blocker, None);
        assert_eq!(spend.fill_status, "filled");

        let exit = simulate_exit_value(&polymarket_book, 17.857142);
        assert_eq!(exit.requested_quantity, 17.857142);
        assert_eq!(exit.filled_quantity, 17.857142);
        assert_eq!(exit.unfilled_quantity, 0.0);
        assert_eq!(exit.average_price, Some(0.4188));
        assert_eq!(exit.value, 7.478571);
        assert_eq!(exit.levels_consumed, 2);
        assert_eq!(exit.status, "filled");
    }
}
