use pm_types::OrderSide;

#[derive(Debug, Clone)]
pub struct OrderIntent {
    pub market_id: String,
    pub side: OrderSide,
    pub price: f64,
    pub size: f64,
}

pub fn build_order_intent(market_id: impl Into<String>, side: OrderSide, price: f64) -> OrderIntent {
    OrderIntent {
        market_id: market_id.into(),
        side,
        price,
        size: 1.0,
    }
}
