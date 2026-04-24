from __future__ import annotations

from weather_pm.models import DecisionResult, ExecutionFeatures, ScoreResult


MIN_EDGE_TO_TRADE = 0.04


def build_decision(
    *,
    score: ScoreResult,
    is_exact_bin: bool,
    spread: float,
    forecast_dispersion: float | None,
    execution: ExecutionFeatures | None = None,
) -> DecisionResult:
    reasons: list[str] = []

    if execution is not None and execution.best_effort_reason == "market_already_resolving_or_resolved":
        reasons.append("skip: market already resolving or resolved")
        return DecisionResult(status="skip", max_position_pct_bankroll=0.0, reasons=reasons)

    if execution is not None and execution.best_effort_reason == "missing_tradeable_quote":
        reasons.append("skip: missing tradeable quote")
        return DecisionResult(status="skip", max_position_pct_bankroll=0.0, reasons=reasons)

    if score.raw_edge < MIN_EDGE_TO_TRADE:
        reasons.append("skip: raw edge too small")
        return DecisionResult(status="skip", max_position_pct_bankroll=0.0, reasons=reasons)

    if spread > 0.06:
        reasons.append("skip: spread too wide")
        return DecisionResult(status="skip", max_position_pct_bankroll=0.0, reasons=reasons)

    if (
        execution is not None
        and score.grade in {"A", "B"}
        and execution.all_in_cost_bps >= (score.raw_edge * 10000.0) * 0.95
    ):
        reasons.append("skip: all-in costs exceed raw edge")
        return DecisionResult(status="skip", max_position_pct_bankroll=0.0, reasons=reasons)

    dispersion = forecast_dispersion if forecast_dispersion is not None else 99.0

    if score.grade == "A" and not is_exact_bin and dispersion <= 2.0:
        reasons.append("trade: edge strong and setup clean")
        reasons.append("edge and structure support full MVP sizing")
        return DecisionResult(status="trade", max_position_pct_bankroll=0.02, reasons=reasons)

    if score.grade in {"A", "B"}:
        reasons.append("trade_small: decent score but not ideal")
        return DecisionResult(status="trade_small", max_position_pct_bankroll=0.01, reasons=reasons)

    if score.grade == "C":
        if not is_exact_bin and score.raw_edge >= MIN_EDGE_TO_TRADE and score.resolution_clarity >= 0.8:
            reasons.append("trade_small: threshold edge is actionable despite middling composite score")
            return DecisionResult(status="trade_small", max_position_pct_bankroll=0.01, reasons=reasons)
        reasons.append("watchlist: market is interesting but not strong enough")
        return DecisionResult(status="watchlist", max_position_pct_bankroll=0.0, reasons=reasons)

    reasons.append("skip: score too weak")
    return DecisionResult(status="skip", max_position_pct_bankroll=0.0, reasons=reasons)
