use pm_book::TopOfBook;
use pm_types::{OrderSide, Venue};

#[derive(Debug, Clone, PartialEq)]
pub struct SignalEvent {
    pub venue: Venue,
    pub market_id: String,
    pub side: OrderSide,
    pub fair_value: f64,
    pub observed_price: f64,
    pub edge_bps: f64,
}

#[derive(Debug, Clone)]
pub struct SignalConfig {
    pub min_edge_bps: f64,
    pub default_side: OrderSide,
}

impl Default for SignalConfig {
    fn default() -> Self {
        Self {
            min_edge_bps: 10.0,
            default_side: OrderSide::BuyYes,
        }
    }
}

pub fn compute_edge_bps(fair_value: f64, observed_price: f64) -> Option<f64> {
    if observed_price <= 0.0 {
        return None;
    }

    Some(((fair_value - observed_price) / observed_price) * 10_000.0)
}

pub fn signal_from_book(
    config: &SignalConfig,
    venue: Venue,
    market_id: impl Into<String>,
    book: &TopOfBook,
) -> Option<SignalEvent> {
    let fair_value = book.mid_price()?;
    let observed_price = book.best_ask?;
    let edge_bps = compute_edge_bps(fair_value, observed_price)?;

    if edge_bps.abs() < config.min_edge_bps {
        return None;
    }

    let side = if fair_value >= observed_price {
        config.default_side.clone()
    } else {
        match config.default_side {
            OrderSide::BuyYes => OrderSide::SellYes,
            OrderSide::SellYes => OrderSide::BuyYes,
            OrderSide::BuyNo => OrderSide::SellNo,
            OrderSide::SellNo => OrderSide::BuyNo,
        }
    };

    Some(SignalEvent {
        venue,
        market_id: market_id.into(),
        side,
        fair_value,
        observed_price,
        edge_bps,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compute_edge_bps_returns_none_for_non_positive_observed_price() {
        assert_eq!(compute_edge_bps(0.5, 0.0), None);
    }

    #[test]
    fn signal_from_book_emits_signal_when_edge_exceeds_threshold() {
        let book = TopOfBook {
            best_bid: Some(0.49),
            best_ask: Some(0.50),
        };

        let signal = signal_from_book(
            &SignalConfig {
                min_edge_bps: 5.0,
                default_side: OrderSide::BuyYes,
            },
            Venue::Polymarket,
            "demo-market",
            &book,
        )
        .expect("expected signal");

        assert_eq!(signal.market_id, "demo-market");
        assert_eq!(signal.side, OrderSide::BuyYes);
        assert!(signal.edge_bps.abs() >= 5.0);
    }

    #[test]
    fn signal_from_book_returns_none_when_edge_is_below_threshold() {
        let book = TopOfBook {
            best_bid: Some(0.4995),
            best_ask: Some(0.5000),
        };

        let signal = signal_from_book(
            &SignalConfig {
                min_edge_bps: 20.0,
                default_side: OrderSide::BuyYes,
            },
            Venue::Polymarket,
            "demo-market",
            &book,
        );

        assert_eq!(signal, None);
    }
}
