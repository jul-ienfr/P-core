use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct LedgerEnvelope<T> {
    pub kind: &'static str,
    pub payload: T,
}

impl<T: Serialize> LedgerEnvelope<T> {
    pub fn to_json(&self) -> Result<String, serde_json::Error> {
        serde_json::to_string(self)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct PaperCostState {
    pub opening_trading_fee_usdc: f64,
    pub opening_fixed_fee_usdc: f64,
    pub opening_fee_usdc: f64,
    pub slippage_usdc: f64,
    pub all_in_entry_cost_usdc: f64,
    pub estimated_exit_fixed_fee_usdc: f64,
    pub estimated_exit_fee_bps: f64,
    pub estimated_exit_fee_usdc: f64,
    pub paper_exit_value_usdc: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct SettlementAccounting {
    pub status: String,
    pub mtm_usdc: f64,
    pub pnl_usdc: f64,
    pub net_pnl_after_all_costs: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ExitDecision {
    pub action: String,
    pub reason: String,
    pub trigger_price: Option<f64>,
    pub current_price: Option<f64>,
    pub unrealized_return_pct: Option<f64>,
}

pub fn fee_amount(notional: f64, bps: f64, fixed: f64) -> Result<f64, String> {
    validate_finite("notional", notional)?;
    validate_finite("bps", bps)?;
    validate_finite("fixed", fixed)?;
    Ok(round6(
        fixed.max(0.0) + notional.max(0.0) * bps.max(0.0) / 10_000.0,
    ))
}

pub fn paper_opening_cost_state(
    filled_usdc: f64,
    top_ask: Option<f64>,
    avg_fill_price: Option<f64>,
    shares: f64,
    mtm_usdc: f64,
    opening_fee_bps: f64,
    opening_fixed_fee_usdc: f64,
    estimated_exit_fee_bps: f64,
    estimated_exit_fixed_fee_usdc: f64,
) -> Result<PaperCostState, String> {
    validate_finite("filled_usdc", filled_usdc)?;
    validate_finite("shares", shares)?;
    validate_finite("mtm_usdc", mtm_usdc)?;
    validate_finite("opening_fee_bps", opening_fee_bps)?;
    validate_finite("opening_fixed_fee_usdc", opening_fixed_fee_usdc)?;
    validate_finite("estimated_exit_fee_bps", estimated_exit_fee_bps)?;
    validate_finite(
        "estimated_exit_fixed_fee_usdc",
        estimated_exit_fixed_fee_usdc,
    )?;
    if let Some(value) = top_ask {
        validate_finite("top_ask", value)?;
    }
    if let Some(value) = avg_fill_price {
        validate_finite("avg_fill_price", value)?;
    }

    let opening_trading_fee = fee_amount(filled_usdc, opening_fee_bps, 0.0)?;
    let opening_fixed_fee = round6(opening_fixed_fee_usdc.max(0.0));
    let opening_fee = round6(opening_trading_fee + opening_fixed_fee);
    let slippage_usdc = match (top_ask, avg_fill_price) {
        (Some(top), Some(avg)) if shares > 0.0 => round6((avg - top).max(0.0) * shares),
        _ => 0.0,
    };
    let estimated_exit_fixed_fee = round6(estimated_exit_fixed_fee_usdc.max(0.0));
    let estimated_exit_fee = fee_amount(
        filled_usdc,
        estimated_exit_fee_bps,
        estimated_exit_fixed_fee,
    )?;

    Ok(PaperCostState {
        opening_trading_fee_usdc: opening_trading_fee,
        opening_fixed_fee_usdc: opening_fixed_fee,
        opening_fee_usdc: opening_fee,
        slippage_usdc,
        all_in_entry_cost_usdc: round6(filled_usdc + opening_fee),
        estimated_exit_fixed_fee_usdc: estimated_exit_fixed_fee,
        estimated_exit_fee_bps,
        estimated_exit_fee_usdc: estimated_exit_fee,
        paper_exit_value_usdc: round6(mtm_usdc),
    })
}

pub fn refresh_pnl(
    mtm_usdc: f64,
    all_in_entry_cost_usdc: f64,
    estimated_exit_fee_usdc: f64,
    realized_exit_fee_usdc: Option<f64>,
) -> Result<f64, String> {
    validate_finite("mtm_usdc", mtm_usdc)?;
    validate_finite("all_in_entry_cost_usdc", all_in_entry_cost_usdc)?;
    validate_finite("estimated_exit_fee_usdc", estimated_exit_fee_usdc)?;
    if let Some(value) = realized_exit_fee_usdc {
        validate_finite("realized_exit_fee_usdc", value)?;
    }
    let exit_fee = realized_exit_fee_usdc.unwrap_or(estimated_exit_fee_usdc);
    Ok(round6(mtm_usdc - all_in_entry_cost_usdc - exit_fee))
}

pub fn settlement_pnl(
    shares: f64,
    all_in_entry_cost_usdc: f64,
    filled_usdc: f64,
    won: bool,
) -> Result<SettlementAccounting, String> {
    validate_finite("shares", shares)?;
    validate_finite("all_in_entry_cost_usdc", all_in_entry_cost_usdc)?;
    validate_finite("filled_usdc", filled_usdc)?;
    let entry_cost = if all_in_entry_cost_usdc > 0.0 {
        all_in_entry_cost_usdc
    } else {
        filled_usdc
    };
    let mtm = if won { round6(shares) } else { 0.0 };
    let pnl = round6(mtm - entry_cost);
    Ok(SettlementAccounting {
        status: if won { "settled_win" } else { "settled_loss" }.to_string(),
        mtm_usdc: mtm,
        pnl_usdc: pnl,
        net_pnl_after_all_costs: pnl,
    })
}

#[allow(clippy::too_many_arguments)]
pub fn evaluate_exit_policy(
    entry_price: Option<f64>,
    current_price: Option<f64>,
    highest_price: Option<f64>,
    filled_usdc: f64,
    shares: f64,
    status: &str,
    stop_loss_pct: f64,
    trailing_stop_pct: f64,
    breakeven_after_profit_pct: f64,
) -> Result<ExitDecision, String> {
    let entry = positive_float("entry_price", entry_price)?;
    let current = positive_float("current_price", current_price)?;
    let highest = positive_float("highest_price", highest_price)?;
    validate_finite("filled_usdc", filled_usdc)?;
    validate_finite("shares", shares)?;
    validate_finite("stop_loss_pct", stop_loss_pct)?;
    validate_finite("trailing_stop_pct", trailing_stop_pct)?;
    validate_finite("breakeven_after_profit_pct", breakeven_after_profit_pct)?;

    let filled = if filled_usdc > 0.0 { filled_usdc } else { 0.0 };
    let share_count = if shares > 0.0 { shares } else { 0.0 };
    let normalized_status = status.to_lowercase();
    if normalized_status != "filled" && normalized_status != "partial"
        || filled <= 0.0
        || share_count <= 0.0
    {
        return Ok(exit_decision(
            "HOLD",
            "not_open_position",
            None,
            current,
            None,
        ));
    }
    let (Some(entry), Some(current)) = (entry, current) else {
        return Ok(exit_decision("HOLD", "missing_price", None, current, None));
    };

    let high = highest.unwrap_or(entry.max(current));
    let unrealized_return = Some(round6((current - entry) / entry));

    let stop_loss_price = round6(entry * (1.0 - stop_loss_pct.max(0.0)));
    if current <= stop_loss_price {
        return Ok(exit_decision(
            "EXIT_REVIEW_PAPER",
            "stop_loss",
            Some(stop_loss_price),
            Some(round6(current)),
            unrealized_return,
        ));
    }

    let trailing_stop_price = round6(high * (1.0 - trailing_stop_pct.max(0.0)));
    if high > entry && current <= trailing_stop_price {
        return Ok(exit_decision(
            "EXIT_REVIEW_PAPER",
            "trailing_stop",
            Some(trailing_stop_price),
            Some(round6(current)),
            unrealized_return,
        ));
    }

    let profit_trigger = breakeven_after_profit_pct.max(0.0);
    let breakeven_buffer = 0.02_f64.min(profit_trigger / 10.0);
    let breakeven_floor = round6(entry * (1.0 + breakeven_buffer));
    if high >= entry * (1.0 + profit_trigger) && current <= breakeven_floor {
        return Ok(exit_decision(
            "EXIT_REVIEW_PAPER",
            "breakeven_after_profit",
            Some(round6(entry)),
            Some(round6(current)),
            unrealized_return,
        ));
    }

    Ok(exit_decision(
        "HOLD",
        "no_exit_trigger",
        None,
        Some(round6(current)),
        unrealized_return,
    ))
}

fn validate_finite(name: &str, value: f64) -> Result<(), String> {
    if !value.is_finite() {
        return Err(format!("{name} must be finite"));
    }
    Ok(())
}

fn positive_float(name: &str, value: Option<f64>) -> Result<Option<f64>, String> {
    let Some(value) = value else {
        return Ok(None);
    };
    validate_finite(name, value)?;
    Ok((value > 0.0).then_some(value))
}

fn exit_decision(
    action: &str,
    reason: &str,
    trigger_price: Option<f64>,
    current_price: Option<f64>,
    unrealized_return_pct: Option<f64>,
) -> ExitDecision {
    ExitDecision {
        action: action.to_string(),
        reason: reason.to_string(),
        trigger_price,
        current_price,
        unrealized_return_pct,
    }
}

fn round6(value: f64) -> f64 {
    (value * 1_000_000.0).round() / 1_000_000.0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fee_amount_ignores_negative_inputs() {
        assert_eq!(fee_amount(10.0, 150.0, 0.25).unwrap(), 0.4);
        assert_eq!(fee_amount(-10.0, -150.0, -0.25).unwrap(), 0.0);
    }

    #[test]
    fn opening_cost_state_matches_python_contract() {
        let cost = paper_opening_cost_state(
            10.0,
            Some(0.28),
            Some(0.288462),
            34.666611,
            0.0,
            50.0,
            0.10,
            40.0,
            0.20,
        )
        .unwrap();

        assert_eq!(cost.opening_trading_fee_usdc, 0.05);
        assert_eq!(cost.opening_fee_usdc, 0.15);
        assert_eq!(cost.slippage_usdc, 0.293349);
        assert_eq!(cost.all_in_entry_cost_usdc, 10.15);
        assert_eq!(cost.estimated_exit_fee_usdc, 0.24);
    }

    #[test]
    fn refresh_pnl_uses_realized_exit_fee_when_available() {
        assert_eq!(refresh_pnl(12.0, 10.15, 0.24, None).unwrap(), 1.61);
        assert_eq!(refresh_pnl(12.0, 10.15, 0.24, Some(0.3)).unwrap(), 1.55);
    }

    #[test]
    fn settlement_pnl_handles_win_and_loss() {
        let win = settlement_pnl(21.5, 10.15, 10.0, true).unwrap();
        let loss = settlement_pnl(21.5, 10.15, 10.0, false).unwrap();

        assert_eq!(win.status, "settled_win");
        assert_eq!(win.mtm_usdc, 21.5);
        assert_eq!(win.pnl_usdc, 11.35);
        assert_eq!(loss.status, "settled_loss");
        assert_eq!(loss.pnl_usdc, -10.15);
    }

    #[test]
    fn exit_policy_recommends_stop_loss() {
        let decision = evaluate_exit_policy(
            Some(0.40),
            Some(0.33),
            Some(0.45),
            10.0,
            25.0,
            "filled",
            0.15,
            0.20,
            0.25,
        )
        .unwrap();

        assert_eq!(decision.action, "EXIT_REVIEW_PAPER");
        assert_eq!(decision.reason, "stop_loss");
        assert_eq!(decision.trigger_price, Some(0.34));
        assert_eq!(decision.current_price, Some(0.33));
        assert_eq!(decision.unrealized_return_pct, Some(-0.175));
    }

    #[test]
    fn exit_policy_preserves_trigger_priority() {
        let trailing = evaluate_exit_policy(
            Some(0.40),
            Some(0.50),
            Some(0.72),
            10.0,
            25.0,
            "filled",
            0.20,
            0.25,
            0.50,
        )
        .unwrap();
        let breakeven = evaluate_exit_policy(
            Some(0.40),
            Some(0.405),
            Some(0.55),
            10.0,
            25.0,
            "filled",
            0.20,
            0.40,
            0.25,
        )
        .unwrap();

        assert_eq!(trailing.reason, "trailing_stop");
        assert_eq!(trailing.trigger_price, Some(0.54));
        assert_eq!(breakeven.reason, "breakeven_after_profit");
        assert_eq!(breakeven.trigger_price, Some(0.40));
    }

    #[test]
    fn exit_policy_holds_for_missing_price_or_closed_position() {
        let missing = evaluate_exit_policy(
            Some(0.40),
            None,
            Some(0.50),
            10.0,
            25.0,
            "filled",
            0.20,
            0.25,
            0.25,
        )
        .unwrap();
        let closed = evaluate_exit_policy(
            Some(0.40),
            Some(0.50),
            Some(0.50),
            0.0,
            0.0,
            "planned",
            0.20,
            0.25,
            0.25,
        )
        .unwrap();

        assert_eq!(missing.action, "HOLD");
        assert_eq!(missing.reason, "missing_price");
        assert_eq!(closed.action, "HOLD");
        assert_eq!(closed.reason, "not_open_position");
    }
}
