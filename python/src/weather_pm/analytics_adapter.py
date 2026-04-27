from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from prediction_core.analytics.events import (
    DebugDecisionEvent,
    ExecutionEvent,
    PaperOrderEvent,
    PaperPnlSnapshotEvent,
    PaperPositionEvent,
    ProfileDecisionEvent,
    StrategySignalEvent,
)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def _parse_observed_at(payload: dict[str, Any], default: datetime | None) -> datetime:
    return _parse_datetime(payload.get("observed_at")) or _parse_datetime(payload.get("generated_at")) or default or datetime.now(UTC)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _bool_from_row(row: dict[str, Any], key: str, default: bool = False) -> bool:
    value = row.get(key)
    if value is None:
        return default
    return bool(value)


def _rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidate = payload.get("rows") if "rows" in payload else payload.get("shortlist")
    if candidate is None and isinstance(payload.get("operator"), dict):
        candidate = payload.get("operator", {}).get("watchlist")
    if not isinstance(candidate, list):
        return []
    return [row for row in candidate if isinstance(row, dict)]


def _execution_rows_from_payload(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    for key, mode_hint in (("execution_events", None), ("events", None), ("live_orders", "live"), ("orders", None)):
        candidate = payload.get(key)
        if isinstance(candidate, list):
            return [row for row in candidate if isinstance(row, dict)], mode_hint
    return [], None


def profile_decision_events_from_shortlist(
    payload: dict[str, Any], *, default_observed_at: datetime | None = None
) -> list[ProfileDecisionEvent]:
    """Convert weather shortlist/profile rows to profile_decisions analytics events."""
    if not isinstance(payload, dict):
        raise ValueError("shortlist payload must be an object")

    payload_observed_at = _parse_observed_at(payload, default_observed_at)
    run_id = payload.get("run_id") or payload.get("report_id") or payload_observed_at.strftime("weather-%Y%m%dT%H%M%SZ")
    mode = str(payload.get("mode") or "paper")

    events: list[ProfileDecisionEvent] = []
    for row in _rows_from_payload(payload):
        observed_at = _parse_datetime(row.get("observed_at")) or _parse_datetime(row.get("generated_at")) or payload_observed_at
        profile_id = row.get("strategy_profile_id") or row.get("profile_id") or row.get("profile") or "default"
        strategy_id = row.get("strategy_id") or row.get("strategy") or "weather_pm"
        decision_status = row.get("decision_status") or row.get("operator_action") or row.get("action") or "unknown"
        skip_reason = row.get("execution_blocker") or row.get("skip_reason") or row.get("blocker") or ""
        risk_caps = row.get("profile_risk_caps") or {}
        capped = row.get("capped_spend_usdc")
        if capped is None and isinstance(risk_caps, dict):
            capped = risk_caps.get("max_order_usdc")
        requested = row.get("requested_spend_usdc") or row.get("paper_notional_usd")
        orderbook_value = row.get("orderbook_ok")
        if orderbook_value is None:
            orderbook_value = row.get("orderbook") or row.get("execution_snapshot") or row.get("order_book_depth_usd")
        risk_ok = row.get("risk_ok")
        if risk_ok is None:
            risk_ok = not bool(skip_reason)

        events.append(
            ProfileDecisionEvent(
                run_id=str(run_id),
                strategy_id=str(strategy_id),
                profile_id=str(profile_id),
                market_id=str(row.get("market_id") or row.get("condition_id") or ""),
                token_id=str(row.get("token_id") or ""),
                observed_at=observed_at,
                mode=mode,
                decision_status=str(decision_status),
                skip_reason=str(skip_reason),
                execution_mode=str(row.get("profile_execution_mode") or row.get("execution_mode") or ""),
                edge=_optional_float(row.get("edge") if row.get("edge") is not None else row.get("probability_edge")),
                limit_price=_optional_float(row.get("strict_limit_price") if row.get("strict_limit_price") is not None else row.get("limit_price")),
                requested_spend_usdc=_optional_float(requested),
                capped_spend_usdc=_optional_float(capped),
                source_ok=bool(row.get("source_ok") if row.get("source_ok") is not None else row.get("source_direct", False)),
                orderbook_ok=bool(orderbook_value),
                risk_ok=bool(risk_ok),
                paper_only=bool(row.get("paper_only", True)),
                live_order_allowed=bool(row.get("live_order_allowed", False)),
                raw=row,
            )
        )
    return events


def debug_decision_events_from_shortlist(
    payload: dict[str, Any], *, default_observed_at: datetime | None = None
) -> list[DebugDecisionEvent]:
    """Convert shortlist/profile rows to focused debug_decisions events."""
    decisions = profile_decision_events_from_shortlist(payload, default_observed_at=default_observed_at)
    return [
        DebugDecisionEvent(
            run_id=event.run_id,
            strategy_id=event.strategy_id,
            profile_id=event.profile_id,
            market_id=event.market_id,
            token_id=event.token_id,
            observed_at=event.observed_at,
            mode=event.mode,
            decision_status=event.decision_status,
            skip_reason=event.skip_reason,
            edge=event.edge,
            limit_price=event.limit_price,
            source_ok=event.source_ok,
            orderbook_ok=event.orderbook_ok,
            risk_ok=event.risk_ok,
            blocker=str((event.raw or {}).get("blocker") or event.skip_reason or ""),
            raw=event.raw,
        )
        for event in decisions
    ]


def strategy_signal_events_from_shortlist(
    payload: dict[str, Any], *, default_observed_at: datetime | None = None
) -> list[StrategySignalEvent]:
    if not isinstance(payload, dict):
        raise ValueError("shortlist payload must be an object")

    payload_observed_at = _parse_observed_at(payload, default_observed_at)
    run_id = payload.get("run_id") or payload.get("report_id") or payload_observed_at.strftime("weather-%Y%m%dT%H%M%SZ")
    mode = str(payload.get("mode") or "paper")

    events: list[StrategySignalEvent] = []
    for index, row in enumerate(_rows_from_payload(payload), start=1):
        observed_at = _parse_datetime(row.get("observed_at")) or _parse_datetime(row.get("generated_at")) or payload_observed_at
        profile_id = row.get("strategy_profile_id") or row.get("profile_id") or row.get("profile") or "default"
        strategy_id = row.get("strategy_id") or row.get("strategy") or "weather_pm"
        market_id = str(row.get("market_id") or row.get("condition_id") or "")
        token_id = str(row.get("token_id") or "")
        signal_id = str(row.get("signal_id") or f"{run_id}:{strategy_id}:{profile_id}:{market_id}:{token_id}:{index}")
        events.append(
            StrategySignalEvent(
                run_id=str(run_id),
                strategy_id=str(strategy_id),
                profile_id=str(profile_id),
                market_id=market_id,
                token_id=token_id,
                observed_at=observed_at,
                mode=mode,
                signal_id=signal_id,
                signal_type=str(row.get("signal_type") or row.get("decision_status") or row.get("operator_action") or row.get("action") or "decision"),
                side=str(row.get("side") or row.get("trade_side") or row.get("paper_side") or row.get("outcome") or "unknown"),
                probability=_optional_float(row.get("probability") if row.get("probability") is not None else row.get("model_probability")),
                market_price=_optional_float(row.get("market_price") if row.get("market_price") is not None else row.get("yes_price")),
                edge=_optional_float(row.get("edge") if row.get("edge") is not None else row.get("probability_edge")),
                confidence=_optional_float(row.get("confidence")),
                paper_only=bool(row.get("paper_only", True)),
                live_order_allowed=bool(row.get("live_order_allowed", False)),
                raw=row,
            )
        )
    return events


def execution_events_from_payload(
    payload: dict[str, Any], *, default_observed_at: datetime | None = None
) -> list[ExecutionEvent]:
    if not isinstance(payload, dict):
        raise ValueError("execution events payload must be an object")

    payload_observed_at = _parse_observed_at(payload, default_observed_at)
    payload_run_id = payload.get("run_id") or payload.get("report_id") or payload_observed_at.strftime("weather-execution-%Y%m%dT%H%M%SZ")
    rows, mode_hint = _execution_rows_from_payload(payload)
    events: list[ExecutionEvent] = []
    for index, row in enumerate(rows, start=1):
        observed_at = _parse_datetime(row.get("observed_at")) or _parse_datetime(row.get("created_at")) or _parse_datetime(row.get("updated_at")) or payload_observed_at
        run_id = row.get("run_id") or payload_run_id
        strategy_id = row.get("strategy_id") or payload.get("strategy_id") or row.get("strategy") or "weather_pm"
        profile_id = row.get("profile_id") or row.get("strategy_profile_id") or payload.get("profile_id") or "default"
        market_id = str(row.get("market_id") or row.get("condition_id") or "")
        token_id = str(row.get("token_id") or "")
        event_id = row.get("execution_event_id") or row.get("order_id") or row.get("live_order_id") or row.get("paper_order_id")
        if not event_id:
            event_id = f"{run_id}:{strategy_id}:{profile_id}:{market_id}:{token_id}:{index}"
        mode = str(row.get("mode") or payload.get("mode") or mode_hint or ("live" if row.get("live_order_allowed") else "paper"))
        events.append(
            ExecutionEvent(
                run_id=str(run_id),
                strategy_id=str(strategy_id),
                profile_id=str(profile_id),
                market_id=market_id,
                token_id=token_id,
                observed_at=observed_at,
                execution_event_id=str(event_id),
                event_type=str(row.get("event_type") or row.get("status") or row.get("order_status") or "unknown"),
                mode=mode,
                paper_only=_bool_from_row(row, "paper_only", mode != "live"),
                live_order_allowed=_bool_from_row(row, "live_order_allowed", mode == "live"),
                raw=row,
            )
        )
    return events



def _orders_from_ledger(ledger: dict[str, Any], observed_default: datetime) -> list[dict[str, Any]]:
    if isinstance(ledger.get("orders"), list):
        return [order for order in ledger["orders"] if isinstance(order, dict)]

    candidates = ledger.get("top_current_candidates")
    if not isinstance(candidates, list):
        return []

    generated_at = str(ledger.get("generated_at") or ledger.get("report_generated_at") or observed_default.isoformat())
    orders: list[dict[str, Any]] = []
    for index, candidate in enumerate([row for row in candidates if isinstance(row, dict)], start=1):
        execution = candidate.get("execution") if isinstance(candidate.get("execution"), dict) else {}
        market_id = str(candidate.get("market_id") or "")
        side = str(candidate.get("side") or candidate.get("candidate_side") or execution.get("side") or "")
        avg_fill_price = _optional_float(execution.get("avg_fill_price") if execution.get("avg_fill_price") is not None else candidate.get("strict_limit"))
        filled_usdc = _optional_float(execution.get("fillable_spend") if execution.get("fill_status") == "filled" else 0.0)
        shares = round(filled_usdc / avg_fill_price, 8) if filled_usdc and avg_fill_price else 0.0
        orders.append(
            {
                "order_id": f"operator-report-{market_id or index}-{side or 'unknown'}",
                "created_at": generated_at,
                "updated_at": generated_at,
                "market_id": market_id,
                "token_id": str(candidate.get("token_id") or ""),
                "side": side,
                "status": str(execution.get("fill_status") or "planned"),
                "strict_limit": candidate.get("strict_limit"),
                "avg_fill_price": avg_fill_price,
                "filled_usdc": filled_usdc,
                "spend_usdc": filled_usdc,
                "shares": shares,
                "pnl_usdc": 0.0,
                "net_pnl_after_all_costs": 0.0,
                "opening_fee_usdc": 0.0,
                "estimated_exit_fee_usdc": 0.0,
                "strategy_id": str(candidate.get("strategy_id") or ledger.get("strategy_id") or "weather_profile_surface_grid_trader_v1"),
                "profile_id": str(candidate.get("profile_id") or candidate.get("strategy_profile_id") or ledger.get("profile_id") or "surface_grid_trader"),
                "paper_only": True,
                "live_order_allowed": bool(candidate.get("live_order_allowed", False)),
                "candidate_rank": candidate.get("rank") or index,
                "question": candidate.get("question") or candidate.get("title"),
                "outcome": candidate.get("outcome"),
                "execution_blocker": candidate.get("execution_blocker") or candidate.get("blocker"),
                "source_status": candidate.get("source_status"),
                "source_latency_tier": candidate.get("source_latency_tier"),
                "source_latency_priority": candidate.get("source_latency_priority"),
                "primary_archetype": candidate.get("primary_archetype"),
                "profile_label": candidate.get("profile_label"),
                "profile_execution_mode": candidate.get("profile_execution_mode"),
                "execution": execution,
            }
        )
    return orders


def paper_order_events_from_ledger(
    ledger: dict[str, Any], *, default_observed_at: datetime | None = None
) -> list[PaperOrderEvent]:
    """Convert weather paper ledger order rows to paper_orders events."""
    if not isinstance(ledger, dict):
        raise ValueError("paper ledger payload must be an object")
    run_id = str(ledger.get("run_id") or ledger.get("report_id") or "weather-paper-ledger")
    mode = str(ledger.get("mode") or "paper")
    observed_default = _parse_observed_at(ledger, default_observed_at)
    orders = _orders_from_ledger(ledger, observed_default)
    events: list[PaperOrderEvent] = []
    for order in orders:
        if not isinstance(order, dict):
            continue
        observed_at = _parse_datetime(order.get("created_at")) or _parse_datetime(order.get("updated_at")) or observed_default
        events.append(
            PaperOrderEvent(
                run_id=run_id,
                strategy_id=str(order.get("strategy_id") or ledger.get("strategy_id") or "weather_pm"),
                profile_id=str(order.get("profile_id") or ledger.get("profile_id") or "default"),
                market_id=str(order.get("market_id") or ""),
                token_id=str(order.get("token_id") or ""),
                observed_at=observed_at,
                mode=mode,
                paper_order_id=str(order.get("order_id") or order.get("paper_order_id") or ""),
                side=str(order.get("side") or ""),
                price=_optional_float(order.get("avg_fill_price") if order.get("avg_fill_price") is not None else order.get("strict_limit")),
                size=_optional_float(order.get("shares") if order.get("shares") is not None else order.get("quantity")),
                spend_usdc=_optional_float(order.get("filled_usdc") if order.get("filled_usdc") is not None else order.get("spend_usdc")),
                status=str(order.get("status") or "unknown"),
                opening_fee_usdc=_optional_float(order.get("opening_fee_usdc")),
                opening_slippage_usdc=_optional_float(order.get("slippage_usdc")),
                estimated_exit_cost_usdc=_optional_float(order.get("estimated_exit_fee_usdc")),
                paper_only=_bool_from_row(order, "paper_only", True),
                live_order_allowed=_bool_from_row(order, "live_order_allowed", False),
                raw=order,
            )
        )
    return events


def paper_position_events_from_ledger(
    ledger: dict[str, Any], *, default_observed_at: datetime | None = None
) -> list[PaperPositionEvent]:
    """Convert filled/active weather paper ledger orders to paper_positions snapshots."""
    if not isinstance(ledger, dict):
        raise ValueError("paper ledger payload must be an object")
    run_id = str(ledger.get("run_id") or ledger.get("report_id") or "weather-paper-ledger")
    mode = str(ledger.get("mode") or "paper")
    observed_default = _parse_observed_at(ledger, default_observed_at)
    orders = _orders_from_ledger(ledger, observed_default)
    events: list[PaperPositionEvent] = []
    for order in orders:
        if not isinstance(order, dict):
            continue
        quantity = float(order.get("shares") or order.get("quantity") or 0.0)
        if quantity <= 0.0:
            continue
        observed_at = _parse_datetime(order.get("updated_at")) or _parse_datetime(order.get("created_at")) or observed_default
        order_id = str(order.get("order_id") or order.get("paper_order_id") or "")
        events.append(
            PaperPositionEvent(
                run_id=run_id,
                strategy_id=str(order.get("strategy_id") or ledger.get("strategy_id") or "weather_pm"),
                profile_id=str(order.get("profile_id") or ledger.get("profile_id") or "default"),
                market_id=str(order.get("market_id") or ""),
                token_id=str(order.get("token_id") or ""),
                observed_at=observed_at,
                mode=mode,
                paper_position_id=str(order.get("position_id") or order_id or f"{order.get('market_id', '')}:{order.get('token_id', '')}"),
                quantity=quantity,
                avg_price=_optional_float(order.get("avg_fill_price") if order.get("avg_fill_price") is not None else order.get("strict_limit")),
                exposure_usdc=_optional_float(order.get("filled_usdc") if order.get("filled_usdc") is not None else order.get("exposure_usdc")),
                mtm_bid_usdc=_optional_float(order.get("mtm_usdc")),
                status=str(order.get("status") or "unknown"),
                raw=order,
            )
        )
    return events


def paper_pnl_snapshot_events_from_ledger(
    ledger: dict[str, Any], *, default_observed_at: datetime | None = None
) -> list[PaperPnlSnapshotEvent]:
    """Convert a weather paper ledger summary to paper_pnl_snapshots events."""
    if not isinstance(ledger, dict):
        raise ValueError("paper ledger payload must be an object")

    run_id = str(ledger.get("run_id") or ledger.get("report_id") or "weather-paper-ledger")
    mode = str(ledger.get("mode") or "paper")
    observed_at = _parse_observed_at(ledger, default_observed_at)
    summary = ledger.get("summary") if isinstance(ledger.get("summary"), dict) else {}
    if isinstance(ledger.get("components"), dict) and isinstance(ledger["components"].get("paper_ledger"), dict):
        summary = {**summary, **ledger["components"]["paper_ledger"]}
    orders = _orders_from_ledger(ledger, observed_at)

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for order in orders:
        strategy_id = str(order.get("strategy_id") or ledger.get("strategy_id") or "weather_pm")
        profile_id = str(order.get("profile_id") or ledger.get("profile_id") or "default")
        groups.setdefault((strategy_id, profile_id), []).append(order)

    if not groups:
        groups[(str(ledger.get("strategy_id") or "weather_pm"), str(ledger.get("profile_id") or "default"))] = []

    events: list[PaperPnlSnapshotEvent] = []
    use_summary = len(groups) == 1
    for (strategy_id, profile_id), group_orders in groups.items():
        gross_pnl = _optional_float(summary.get("pnl_usdc")) if use_summary else None
        net_pnl = _optional_float(summary.get("net_pnl_after_all_costs")) if use_summary else None
        exposure = _optional_float(summary.get("filled_usdc")) if use_summary else None
        opening_fee = _optional_float(summary.get("opening_fee_usdc")) if use_summary else None
        estimated_exit_fee = _optional_float(summary.get("estimated_exit_fee_usdc")) if use_summary else None
        realized_exit_fee = _optional_float(summary.get("realized_exit_fee_usdc")) if use_summary else None

        if gross_pnl is None:
            gross_pnl = sum(float(order.get("pnl_usdc") or 0.0) for order in group_orders)
        if net_pnl is None:
            net_pnl = sum(float(order.get("net_pnl_after_all_costs") or order.get("pnl_usdc") or 0.0) for order in group_orders)
        if exposure is None:
            exposure = sum(float(order.get("filled_usdc") or order.get("spend_usdc") or 0.0) for order in group_orders)
        if opening_fee is None:
            opening_fee = sum(float(order.get("opening_fee_usdc") or 0.0) for order in group_orders)
        if estimated_exit_fee is None:
            estimated_exit_fee = sum(float(order.get("estimated_exit_fee_usdc") or 0.0) for order in group_orders)
        if realized_exit_fee is None:
            realized_exit_fee = sum(float(order.get("realized_exit_fee_usdc") or 0.0) for order in group_orders)

        costs = round(opening_fee + estimated_exit_fee + realized_exit_fee, 6)
        settled_orders = [order for order in group_orders if str(order.get("status") or "").startswith("settled_")]
        wins = [order for order in settled_orders if str(order.get("status") or "") == "settled_win"]
        events.append(
            PaperPnlSnapshotEvent(
                run_id=run_id,
                strategy_id=strategy_id,
                profile_id=profile_id,
                market_id="",
                observed_at=observed_at,
                mode=mode,
                gross_pnl_usdc=gross_pnl,
                net_pnl_usdc=net_pnl,
                costs_usdc=costs,
                exposure_usdc=exposure,
                roi=round(net_pnl / exposure, 6) if exposure else None,
                winrate=(len(wins) / len(settled_orders)) if settled_orders else None,
                raw={"summary": summary, "orders": group_orders},
            )
        )
    return events
