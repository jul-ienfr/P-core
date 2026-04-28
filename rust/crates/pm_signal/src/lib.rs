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
pub struct EntryDecision {
    pub policy: String,
    pub enter: bool,
    pub action: String,
    pub side: String,
    pub market_price: f64,
    pub model_probability: f64,
    pub confidence: f64,
    pub edge_gross: f64,
    pub edge_net_all_in: f64,
    pub blocked_by: Vec<String>,
    pub size_hint_usd: f64,
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

#[allow(clippy::too_many_arguments)]
pub fn evaluate_entry(
    policy_name: &str,
    q_min: f64,
    q_max: f64,
    min_edge: f64,
    min_confidence: f64,
    max_spread: f64,
    min_depth_usd: f64,
    max_position_usd: f64,
    market_price: f64,
    model_probability: f64,
    confidence: f64,
    spread: f64,
    depth_usd: f64,
    execution_cost_bps: f64,
    side: &str,
) -> Result<EntryDecision, String> {
    let price = validate_probability("market_price", market_price)?;
    let probability = validate_probability("model_probability", model_probability)?;
    let resolved_confidence = validate_probability("confidence", confidence)?;
    validate_finite("q_min", q_min)?;
    validate_finite("q_max", q_max)?;
    validate_finite("min_edge", min_edge)?;
    validate_finite("min_confidence", min_confidence)?;
    validate_finite("max_spread", max_spread)?;
    validate_finite("min_depth_usd", min_depth_usd)?;
    validate_finite("max_position_usd", max_position_usd)?;
    let resolved_spread = validate_finite("spread", spread)?;
    let resolved_depth_usd = validate_finite("depth_usd", depth_usd)?;
    let resolved_cost_bps = validate_finite("execution_cost_bps", execution_cost_bps)?;
    let resolved_side = validate_entry_side(side)?;
    let gross_edge = entry_edge(probability, price, &resolved_side);
    let cost = resolved_cost_bps.max(0.0) / 10_000.0;
    let net_edge = round4(gross_edge - cost);

    let mut blocked_by = Vec::new();
    if price < q_min || price > q_max {
        blocked_by.push("price_outside_window".to_string());
    }
    if gross_edge < min_edge {
        blocked_by.push("edge_below_threshold".to_string());
    }
    if resolved_confidence < min_confidence {
        blocked_by.push("confidence_below_threshold".to_string());
    }
    if resolved_spread > max_spread {
        blocked_by.push("spread_too_wide".to_string());
    }
    if resolved_depth_usd < min_depth_usd {
        blocked_by.push("depth_insufficient".to_string());
    }
    if net_edge <= 0.0 || net_edge < min_edge {
        blocked_by.push("execution_cost_exceeds_edge".to_string());
    }

    let enter = blocked_by.is_empty();
    Ok(EntryDecision {
        policy: policy_name.to_string(),
        enter,
        action: if enter { "paper_trade_small" } else { "skip" }.to_string(),
        side: resolved_side,
        market_price: round4(price),
        model_probability: round4(probability),
        confidence: round4(resolved_confidence),
        edge_gross: round4(gross_edge),
        edge_net_all_in: round4(net_edge),
        blocked_by,
        size_hint_usd: if enter { round4(max_position_usd) } else { 0.0 },
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

fn entry_edge(probability: f64, price: f64, side: &str) -> f64 {
    if side == "yes" {
        round4(probability - price)
    } else {
        round4(price - probability)
    }
}

fn validate_entry_side(side: &str) -> Result<String, String> {
    let resolved = side.trim().to_lowercase();
    let resolved = if resolved.is_empty() {
        "yes".to_string()
    } else {
        resolved
    };
    match resolved.as_str() {
        "buy" | "y" | "yes" => Ok("yes".to_string()),
        "n" | "no" => Ok("no".to_string()),
        _ => Err("side must be 'yes' or 'no'".to_string()),
    }
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
    fn evaluate_entry_allows_trade_inside_policy() {
        let decision = evaluate_entry(
            "weather_station",
            0.08,
            0.92,
            0.07,
            0.75,
            0.08,
            50.0,
            10.0,
            0.55,
            0.67,
            0.81,
            0.03,
            240.0,
            120.0,
            "yes",
        )
        .unwrap();

        assert!(decision.enter);
        assert_eq!(decision.action, "paper_trade_small");
        assert_eq!(decision.blocked_by, Vec::<String>::new());
        assert_eq!(decision.edge_gross, 0.12);
        assert_eq!(decision.edge_net_all_in, 0.108);
        assert_eq!(decision.size_hint_usd, 10.0);
    }

    #[test]
    fn evaluate_entry_blocks_with_stable_reasons() {
        let decision = evaluate_entry(
            "crypto_5m_conservative",
            0.60,
            0.95,
            0.05,
            0.85,
            0.02,
            1000.0,
            0.0,
            0.40,
            0.43,
            0.70,
            0.06,
            100.0,
            100.0,
            "yes",
        )
        .unwrap();

        assert!(!decision.enter);
        assert_eq!(
            decision.blocked_by,
            vec![
                "price_outside_window".to_string(),
                "edge_below_threshold".to_string(),
                "confidence_below_threshold".to_string(),
                "spread_too_wide".to_string(),
                "depth_insufficient".to_string(),
                "execution_cost_exceeds_edge".to_string(),
            ]
        );
        assert_eq!(decision.edge_gross, 0.03);
        assert_eq!(decision.edge_net_all_in, 0.02);
    }

    #[test]
    fn evaluate_entry_supports_no_side() {
        let decision = evaluate_entry(
            "tail_risk_micro",
            0.01,
            0.20,
            0.09,
            0.90,
            0.05,
            20.0,
            5.0,
            0.12,
            0.02,
            0.95,
            0.02,
            100.0,
            50.0,
            "no",
        )
        .unwrap();

        assert!(decision.enter);
        assert_eq!(decision.side, "no");
        assert_eq!(decision.edge_gross, 0.10);
        assert_eq!(decision.edge_net_all_in, 0.095);
        assert_eq!(decision.size_hint_usd, 5.0);
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
