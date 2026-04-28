use pm_types::OrderSide;

#[derive(Debug, Clone)]
pub struct OrderIntent {
    pub market_id: String,
    pub side: OrderSide,
    pub price: f64,
    pub size: f64,
}

pub fn build_order_intent(
    market_id: impl Into<String>,
    side: OrderSide,
    price: f64,
) -> OrderIntent {
    OrderIntent {
        market_id: market_id.into(),
        side,
        price,
        size: 1.0,
    }
}

pub fn compute_order_size(
    notional_usdc: f64,
    limit_price: f64,
    min_order_size: f64,
    size_tick: f64,
) -> Result<f64, String> {
    validate_positive("notional_usdc", notional_usdc)?;
    if !limit_price.is_finite() || limit_price <= 0.0 || limit_price >= 1.0 {
        return Err("limit_price must be finite and between 0 and 1".to_string());
    }
    validate_positive("min_order_size", min_order_size)?;
    validate_positive("size_tick", size_tick)?;

    let raw_size = notional_usdc / limit_price;
    let size = round8((raw_size / size_tick).floor() * size_tick);
    if !size.is_finite() || size < min_order_size {
        return Err("computed Polymarket order size is below minimum".to_string());
    }
    let effective_notional = size * limit_price;
    if effective_notional <= 0.0 || effective_notional > notional_usdc {
        return Err("computed Polymarket order notional is invalid".to_string());
    }
    if (notional_usdc - effective_notional) / notional_usdc > 0.05 {
        return Err(
            "computed Polymarket order size is too far below requested notional".to_string(),
        );
    }
    Ok(size)
}

fn validate_positive(name: &str, value: f64) -> Result<(), String> {
    if !value.is_finite() || value <= 0.0 {
        return Err(format!("{name} must be finite and positive"));
    }
    Ok(())
}

fn round8(value: f64) -> f64 {
    (value * 100_000_000.0).round() / 100_000_000.0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compute_order_size_rounds_down_to_tick() {
        assert_eq!(compute_order_size(5.0, 0.5, 0.01, 0.01).unwrap(), 10.0);
        assert_eq!(compute_order_size(5.0, 0.44, 0.01, 0.01).unwrap(), 11.36);
    }

    #[test]
    fn compute_order_size_rejects_below_minimum() {
        assert_eq!(
            compute_order_size(0.01, 0.5, 0.1, 0.01),
            Err("computed Polymarket order size is below minimum".to_string())
        );
    }

    #[test]
    fn compute_order_size_rejects_large_tick_undershoot() {
        assert_eq!(
            compute_order_size(1.0, 0.52, 0.01, 1.0),
            Err("computed Polymarket order size is too far below requested notional".to_string())
        );
    }

    #[test]
    fn compute_order_size_rejects_invalid_inputs() {
        assert_eq!(
            compute_order_size(f64::NAN, 0.5, 0.01, 0.01),
            Err("notional_usdc must be finite and positive".to_string())
        );
        assert_eq!(
            compute_order_size(5.0, 1.0, 0.01, 0.01),
            Err("limit_price must be finite and between 0 and 1".to_string())
        );
        assert_eq!(
            compute_order_size(5.0, 0.5, 0.0, 0.01),
            Err("min_order_size must be finite and positive".to_string())
        );
    }
}
