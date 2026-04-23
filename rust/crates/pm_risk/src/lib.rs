use pm_types::RiskDecisionStatus;

#[derive(Debug, Clone)]
pub struct RiskDecision {
    pub decision: RiskDecisionStatus,
    pub reasons: Vec<String>,
}

pub fn approve_if_spread_not_crossed(best_bid: Option<f64>, best_ask: Option<f64>) -> RiskDecision {
    match (best_bid, best_ask) {
        (Some(bid), Some(ask)) if bid <= ask => RiskDecision {
            decision: RiskDecisionStatus::Approved,
            reasons: vec![],
        },
        _ => RiskDecision {
            decision: RiskDecisionStatus::Rejected,
            reasons: vec!["crossed_or_incomplete_book".to_string()],
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn approves_non_crossed_book() {
        let decision = approve_if_spread_not_crossed(Some(0.47), Some(0.49));

        assert_eq!(decision.decision, RiskDecisionStatus::Approved);
        assert!(decision.reasons.is_empty());
    }

    #[test]
    fn rejects_crossed_book() {
        let decision = approve_if_spread_not_crossed(Some(0.51), Some(0.49));

        assert_eq!(decision.decision, RiskDecisionStatus::Rejected);
        assert_eq!(decision.reasons, vec!["crossed_or_incomplete_book".to_string()]);
    }

    #[test]
    fn rejects_incomplete_book() {
        let decision = approve_if_spread_not_crossed(Some(0.47), None);

        assert_eq!(decision.decision, RiskDecisionStatus::Rejected);
    }
}
