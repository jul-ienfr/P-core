use pm_types::RiskDecisionStatus;

#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionRiskDecision {
    pub allowed: bool,
    pub blocked_by: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct RiskDecision {
    pub decision: RiskDecisionStatus,
    pub reasons: Vec<String>,
}

pub fn evaluate_execution_risk(
    order_notional_usdc: f64,
    total_exposure_usdc: f64,
    daily_realized_pnl_usdc: f64,
    max_order_notional_usdc: f64,
    max_total_exposure_usdc: f64,
    max_daily_loss_usdc: f64,
    max_spread: f64,
    spread: Option<f64>,
    invalid_spread: bool,
) -> Result<ExecutionRiskDecision, String> {
    validate_positive("order_notional_usdc", order_notional_usdc)?;
    validate_non_negative("total_exposure_usdc", total_exposure_usdc)?;
    validate_finite("daily_realized_pnl_usdc", daily_realized_pnl_usdc)?;
    validate_positive("max_order_notional_usdc", max_order_notional_usdc)?;
    validate_positive("max_total_exposure_usdc", max_total_exposure_usdc)?;
    validate_positive("max_daily_loss_usdc", max_daily_loss_usdc)?;
    validate_positive("max_spread", max_spread)?;

    let mut blocked = Vec::new();
    if order_notional_usdc > max_order_notional_usdc {
        blocked.push("max_order_notional_usdc".to_string());
    }
    if total_exposure_usdc + order_notional_usdc > max_total_exposure_usdc {
        blocked.push("max_total_exposure_usdc".to_string());
    }
    if daily_realized_pnl_usdc <= -max_daily_loss_usdc.abs() {
        blocked.push("max_daily_loss_usdc".to_string());
    }
    match spread {
        None if invalid_spread => blocked.push("invalid_spread".to_string()),
        None => blocked.push("missing_spread".to_string()),
        Some(value) if !value.is_finite() => blocked.push("invalid_spread".to_string()),
        Some(value) if value > max_spread => blocked.push("max_spread".to_string()),
        Some(_) => {}
    }

    Ok(ExecutionRiskDecision {
        allowed: blocked.is_empty(),
        blocked_by: blocked,
    })
}

pub fn approve_if_spread_not_crossed(best_bid: Option<f64>, best_ask: Option<f64>) -> RiskDecision {
    match (best_bid, best_ask) {
        (Some(bid), Some(ask)) if valid_price(bid) && valid_price(ask) && bid <= ask => {
            RiskDecision {
                decision: RiskDecisionStatus::Approved,
                reasons: vec![],
            }
        }
        _ => RiskDecision {
            decision: RiskDecisionStatus::Rejected,
            reasons: vec!["crossed_or_incomplete_book".to_string()],
        },
    }
}

fn validate_positive(name: &str, value: f64) -> Result<(), String> {
    if !value.is_finite() || value <= 0.0 {
        return Err(format!("{name} must be finite and positive"));
    }
    Ok(())
}

fn validate_non_negative(name: &str, value: f64) -> Result<(), String> {
    if !value.is_finite() || value < 0.0 {
        return Err(format!("{name} must be finite and non-negative"));
    }
    Ok(())
}

fn validate_finite(name: &str, value: f64) -> Result<(), String> {
    if !value.is_finite() {
        return Err(format!("{name} must be finite"));
    }
    Ok(())
}

fn valid_price(value: f64) -> bool {
    value.is_finite() && (0.0..=1.0).contains(&value)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn execution_risk_allows_order_inside_limits() {
        let decision =
            evaluate_execution_risk(7.5, 20.0, 0.0, 10.0, 100.0, 25.0, 0.05, Some(0.03), false)
                .unwrap();

        assert!(decision.allowed);
        assert!(decision.blocked_by.is_empty());
    }

    #[test]
    fn execution_risk_blocks_order_limit_exposure_loss_and_spread() {
        let decision = evaluate_execution_risk(
            11.0,
            95.0,
            -30.0,
            10.0,
            100.0,
            25.0,
            0.05,
            Some(0.08),
            false,
        )
        .unwrap();

        assert!(!decision.allowed);
        assert_eq!(
            decision.blocked_by,
            vec![
                "max_order_notional_usdc".to_string(),
                "max_total_exposure_usdc".to_string(),
                "max_daily_loss_usdc".to_string(),
                "max_spread".to_string(),
            ]
        );
    }

    #[test]
    fn execution_risk_fails_closed_on_missing_or_invalid_spread() {
        let missing =
            evaluate_execution_risk(7.5, 20.0, 0.0, 10.0, 100.0, 25.0, 0.05, None, false).unwrap();
        let invalid =
            evaluate_execution_risk(7.5, 20.0, 0.0, 10.0, 100.0, 25.0, 0.05, None, true).unwrap();

        assert_eq!(missing.blocked_by, vec!["missing_spread".to_string()]);
        assert_eq!(invalid.blocked_by, vec!["invalid_spread".to_string()]);
    }

    #[test]
    fn execution_risk_rejects_invalid_inputs() {
        assert_eq!(
            evaluate_execution_risk(0.0, 20.0, 0.0, 10.0, 100.0, 25.0, 0.05, Some(0.03), false),
            Err("order_notional_usdc must be finite and positive".to_string())
        );
    }

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
        assert_eq!(
            decision.reasons,
            vec!["crossed_or_incomplete_book".to_string()]
        );
    }

    #[test]
    fn rejects_incomplete_book() {
        let decision = approve_if_spread_not_crossed(Some(0.47), None);

        assert_eq!(decision.decision, RiskDecisionStatus::Rejected);
    }

    #[test]
    fn rejects_non_finite_prices() {
        let decision = approve_if_spread_not_crossed(Some(0.47), Some(f64::INFINITY));

        assert_eq!(decision.decision, RiskDecisionStatus::Rejected);
    }
}
