use pm_types::MarketEvent;

#[derive(Debug, Clone, Default)]
pub struct TopOfBook {
    pub best_bid: Option<f64>,
    pub best_ask: Option<f64>,
}

impl TopOfBook {
    pub fn apply(&mut self, event: &MarketEvent) {
        if let Some(v) = event.best_bid {
            self.best_bid = Some(v);
        }
        if let Some(v) = event.best_ask {
            self.best_ask = Some(v);
        }
    }

    pub fn mid_price(&self) -> Option<f64> {
        match (self.best_bid, self.best_ask) {
            (Some(bid), Some(ask)) if ask >= bid => Some((bid + ask) / 2.0),
            _ => None,
        }
    }
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
}
