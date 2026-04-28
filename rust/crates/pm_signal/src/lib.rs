use pm_book::TopOfBook;
use pm_types::{OrderSide, Venue};

#[derive(Debug, Clone, PartialEq)]
pub struct EdgeSizing {
    pub prediction_probability: f64,
    pub market_price: f64,
    pub side: String,
    pub raw_edge: f64,
    pub net_edge: f64,
    pub edge_bps: i64,
    pub net_edge_bps: i64,
    pub kelly_fraction: f64,
    pub suggested_fraction: f64,
    pub recommendation: String,
}

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

pub fn calculate_edge_sizing(
    prediction_probability: f64,
    market_price: f64,
    side: &str,
    edge_cost_bps: f64,
    kelly_scale: f64,
    max_fraction: f64,
    min_net_edge: f64,
) -> Result<EdgeSizing, String> {
    let prediction = validate_probability("prediction_probability", prediction_probability)?;
    let price = validate_probability("market_price", market_price)?;
    let resolved_side = validate_side(side)?;
    let cost_bps = validate_finite("edge_cost_bps", edge_cost_bps)?;
    let scale = validate_finite("kelly_scale", kelly_scale)?;
    let fraction_cap = validate_finite("max_fraction", max_fraction)?;
    let minimum_edge = validate_finite("min_net_edge", min_net_edge)?;
    let cost_fraction = cost_bps.max(0.0) / 10_000.0;

    let raw_edge = round4(prediction - price);
    let directional_edge = if resolved_side == "buy" {
        raw_edge
    } else {
        -raw_edge
    };
    let net_edge = round4(directional_edge - cost_fraction);
    let kelly_fraction = kelly_fraction(prediction, price, &resolved_side);
    let suggested_fraction = if net_edge >= minimum_edge {
        (kelly_fraction.max(0.0) * scale.max(0.0)).min(fraction_cap.max(0.0))
    } else {
        0.0
    };
    let recommendation = if suggested_fraction > 0.0 {
        resolved_side.clone()
    } else {
        "skip".to_string()
    };

    Ok(EdgeSizing {
        prediction_probability: prediction,
        market_price: price,
        side: resolved_side,
        raw_edge: round4(raw_edge),
        net_edge: round4(net_edge),
        edge_bps: (raw_edge * 10_000.0).round() as i64,
        net_edge_bps: (net_edge * 10_000.0).round() as i64,
        kelly_fraction: round4(kelly_fraction),
        suggested_fraction: round4(suggested_fraction),
        recommendation,
    })
}

pub fn compute_edge_bps(side_fair_value: f64, observed_price: f64) -> Option<f64> {
    if !valid_price(side_fair_value) || !valid_price(observed_price) || observed_price <= 0.0 {
        return None;
    }

    let edge_bps = ((side_fair_value - observed_price) / observed_price) * 10_000.0;
    edge_bps.is_finite().then_some(edge_bps)
}

fn kelly_fraction(prediction: f64, price: f64, side: &str) -> f64 {
    if price <= 0.0 || price >= 1.0 {
        return 0.0;
    }
    let (b, p) = if side == "buy" {
        ((1.0 - price) / price, prediction)
    } else {
        let no_price = 1.0 - price;
        if no_price <= 0.0 || no_price >= 1.0 {
            return 0.0;
        }
        ((1.0 - no_price) / no_price, 1.0 - prediction)
    };
    let q = 1.0 - p;
    if b <= 0.0 {
        return 0.0;
    }
    ((b * p - q) / b).max(0.0)
}

fn validate_probability(name: &str, value: f64) -> Result<f64, String> {
    let resolved = validate_finite(name, value)?;
    if !(0.0..=1.0).contains(&resolved) {
        return Err(format!("{name} must be between 0 and 1"));
    }
    Ok(resolved)
}

fn validate_finite(name: &str, value: f64) -> Result<f64, String> {
    if !value.is_finite() {
        return Err(format!("{name} must be finite"));
    }
    Ok(value)
}

fn validate_side(side: &str) -> Result<String, String> {
    let resolved = side.trim().to_lowercase();
    let resolved = if resolved.is_empty() {
        "buy".to_string()
    } else {
        resolved
    };
    if resolved != "buy" && resolved != "sell" {
        return Err("side must be 'buy' or 'sell'".to_string());
    }
    Ok(resolved)
}

fn valid_price(value: f64) -> bool {
    value.is_finite() && (0.0..=1.0).contains(&value)
}

fn round4(value: f64) -> f64 {
    (value * 10_000.0).round() / 10_000.0
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
    fn calculates_buy_edge_sizing() {
        let sizing = calculate_edge_sizing(0.62, 0.55, "buy", 120.0, 0.25, 0.02, 0.015).unwrap();

        assert_eq!(sizing.recommendation, "buy");
        assert_eq!(sizing.raw_edge, 0.07);
        assert_eq!(sizing.net_edge, 0.058);
        assert_eq!(sizing.edge_bps, 700);
        assert_eq!(sizing.net_edge_bps, 580);
        assert!(sizing.kelly_fraction > 0.0);
        assert!(sizing.suggested_fraction <= sizing.kelly_fraction);
    }

    #[test]
    fn calculates_sell_edge_sizing() {
        let sizing = calculate_edge_sizing(0.40, 0.48, "sell", 100.0, 0.25, 0.02, 0.015).unwrap();

        assert_eq!(sizing.recommendation, "sell");
        assert_eq!(sizing.raw_edge, -0.08);
        assert_eq!(sizing.net_edge, 0.07);
        assert_eq!(sizing.edge_bps, -800);
        assert_eq!(sizing.net_edge_bps, 700);
        assert!(sizing.suggested_fraction > 0.0);
    }

    #[test]
    fn calculate_edge_sizing_rejects_invalid_probability() {
        assert_eq!(
            calculate_edge_sizing(1.2, 0.5, "buy", 0.0, 0.25, 0.02, 0.015),
            Err("prediction_probability must be between 0 and 1".to_string())
        );
    }

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
