use pm_book::TopOfBook;
use pm_types::{OrderSide, Venue};

#[derive(Debug, Clone, PartialEq)]
pub struct SignalEvent {
    pub venue: Venue,
    pub market_id: String,
    pub side: OrderSide,
    pub side_fair_value: f64,
    pub observed_price: f64,
    pub edge_bps: f64,
}

#[derive(Debug, Clone)]
pub struct SignalConfig {
    pub min_edge_bps: f64,
    pub default_side: OrderSide,
    pub side_fair_value: Option<f64>,
}

impl Default for SignalConfig {
    fn default() -> Self {
        Self {
            min_edge_bps: 10.0,
            default_side: OrderSide::BuyYes,
            side_fair_value: None,
        }
    }
}

pub fn compute_edge_bps(side_fair_value: f64, observed_price: f64) -> Option<f64> {
    if !valid_price(side_fair_value) || !valid_price(observed_price) || observed_price <= 0.0 {
        return None;
    }

    let edge_bps = ((side_fair_value - observed_price) / observed_price) * 10_000.0;
    edge_bps.is_finite().then_some(edge_bps)
}

fn valid_price(value: f64) -> bool {
    value.is_finite() && (0.0..=1.0).contains(&value)
}

pub fn signal_from_book(
    config: &SignalConfig,
    venue: Venue,
    market_id: impl Into<String>,
    book: &TopOfBook,
) -> Option<SignalEvent> {
    book.mid_price()?;
    let side_fair_value = config.side_fair_value?;
    let observed_price = match config.default_side {
        OrderSide::BuyYes => book.best_ask?,
        OrderSide::BuyNo => 1.0 - book.best_bid?,
        OrderSide::SellYes | OrderSide::SellNo => return None,
    };
    let edge_bps = compute_edge_bps(side_fair_value, observed_price)?;

    if edge_bps < config.min_edge_bps {
        return None;
    }

    Some(SignalEvent {
        venue,
        market_id: market_id.into(),
        side: config.default_side.clone(),
        side_fair_value,
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
    fn compute_edge_bps_returns_none_for_non_finite_values() {
        assert_eq!(compute_edge_bps(f64::NAN, 0.5), None);
        assert_eq!(compute_edge_bps(0.5, f64::INFINITY), None);
    }

    #[test]
    fn signal_from_book_requires_explicit_side_fair_value() {
        let book = TopOfBook {
            best_bid: Some(0.49),
            best_ask: Some(0.50),
        };

        let signal = signal_from_book(
            &SignalConfig {
                min_edge_bps: 5.0,
                default_side: OrderSide::BuyYes,
                side_fair_value: None,
            },
            Venue::Polymarket,
            "demo-market",
            &book,
        );

        assert_eq!(signal, None);
    }

    #[test]
    fn signal_from_book_emits_buy_signal_when_model_edge_exceeds_threshold() {
        let book = TopOfBook {
            best_bid: Some(0.49),
            best_ask: Some(0.50),
        };

        let signal = signal_from_book(
            &SignalConfig {
                min_edge_bps: 5.0,
                default_side: OrderSide::BuyYes,
                side_fair_value: Some(0.52),
            },
            Venue::Polymarket,
            "demo-market",
            &book,
        )
        .expect("expected signal");

        assert_eq!(signal.market_id, "demo-market");
        assert_eq!(signal.side, OrderSide::BuyYes);
        assert!(signal.edge_bps >= 5.0);
    }

    #[test]
    fn signal_from_book_prices_buy_no_against_no_ask() {
        let book = TopOfBook {
            best_bid: Some(0.49),
            best_ask: Some(0.50),
        };

        let signal = signal_from_book(
            &SignalConfig {
                min_edge_bps: 5.0,
                default_side: OrderSide::BuyNo,
                side_fair_value: Some(0.53),
            },
            Venue::Polymarket,
            "demo-market",
            &book,
        )
        .expect("expected no-side signal");

        assert_eq!(signal.side, OrderSide::BuyNo);
        assert_eq!(signal.observed_price, 0.51);
    }

    #[test]
    fn signal_from_book_rejects_sell_side_configs() {
        let book = TopOfBook {
            best_bid: Some(0.49),
            best_ask: Some(0.50),
        };

        let signal = signal_from_book(
            &SignalConfig {
                min_edge_bps: 5.0,
                default_side: OrderSide::SellYes,
                side_fair_value: Some(0.40),
            },
            Venue::Polymarket,
            "demo-market",
            &book,
        );

        assert_eq!(signal, None);
    }

    #[test]
    fn signal_from_book_returns_none_when_model_edge_is_below_threshold() {
        let book = TopOfBook {
            best_bid: Some(0.4995),
            best_ask: Some(0.5000),
        };

        let signal = signal_from_book(
            &SignalConfig {
                min_edge_bps: 20.0,
                default_side: OrderSide::BuyYes,
                side_fair_value: Some(0.5005),
            },
            Venue::Polymarket,
            "demo-market",
            &book,
        );

        assert_eq!(signal, None);
    }
}
