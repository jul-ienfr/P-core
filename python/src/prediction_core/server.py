from __future__ import annotations

import json
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from prediction_core.execution import (
    BookLevel,
    OrderBookSnapshot,
    TradingFeeSchedule,
    TransferFeeSchedule,
    quote_execution_cost,
)
from prediction_core.paper import (
    PaperPositionSide,
    simulate_paper_trade_from_execution,
    derive_filled_execution,
    derive_requested_quantity,
)
from prediction_core.strategies.config_store import StrategyConfigStore
from weather_pm.cli import (
    _score_market_from_market_id,
    resolution_status_for_market_id,
    station_history_for_market_id,
    station_latest_for_market_id,
    station_source_plan_for_market_id,
)
from weather_pm.market_parser import parse_market_question
from weather_pm.pipeline import score_market_from_question
from weather_pm.polymarket_client import list_weather_markets, normalize_market_record
from weather_pm.resolution_monitor import write_paper_resolution_monitor
from weather_pm.source_coverage import build_weather_source_coverage_report


class PredictionCoreHandler(BaseHTTPRequestHandler):
    server_version = "prediction_core_python/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/health":
            self._json_response(200, {"status": "ok", "service": "prediction_core_python"})
            return
        if parsed_url.path == "/strategies/config":
            try:
                self._json_response(200, strategy_config_store().list_configs())
            except ValueError as exc:
                self._json_response(400, {"status": "error", "message": str(exc)})
            except Exception as exc:  # pragma: no cover - defensive boundary
                self._json_response(500, {"status": "error", "message": "internal error"})
            return
        if parsed_url.path.startswith("/strategies/config/"):
            strategy_id = parsed_url.path.removeprefix("/strategies/config/").strip("/")
            if strategy_id and "/" not in strategy_id:
                try:
                    config = strategy_config_store().get_config(strategy_id)
                    self._json_response(200, {"strategy": strategy_config_payload(config)})
                except ValueError as exc:
                    self._json_response(400, {"status": "error", "message": str(exc)})
                except Exception as exc:  # pragma: no cover - defensive boundary
                    self._json_response(500, {"status": "error", "message": "internal error"})
                return
        if parsed_url.path == "/weather/polymarket/markets":
            try:
                result = polymarket_weather_markets_query(parse_qs(parsed_url.query))
                self._json_response(200, result)
            except ValueError as exc:
                self._json_response(400, {"status": "error", "message": str(exc)})
            except Exception as exc:  # pragma: no cover - defensive boundary
                self._json_response(500, {"status": "error", "message": "internal error"})
            return
        if parsed_url.path == "/ops/status":
            self._json_response(200, ops_status_request())
            return
        if parsed_url.path == "/ops/risk":
            self._json_response(200, ops_risk_request())
            return
        if parsed_url.path == "/ops/reconciliation":
            self._json_response(200, ops_reconciliation_request())
            return
        self._json_response(404, {"status": "error", "message": f"unknown path: {self.path}"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self._read_json_body()
        except ValueError as exc:
            self._json_response(400, {"status": "error", "message": str(exc)})
            return

        try:
            if self.path.startswith("/strategies/config/"):
                result = strategy_config_mutation_request(self.path, payload)
                self._json_response(200, result)
                return

            if self.path == "/weather/parse-market":
                question = self._require_string(payload, "question")
                result = parse_market_question(question).to_dict()
                self._json_response(200, result)
                return

            if self.path == "/weather/fetch-markets":
                result = fetch_markets_request(payload)
                self._json_response(200, {"markets": result})
                return

            if self.path == "/weather/score-market":
                result = score_market_request(payload)
                self._json_response(200, result)
                return

            if self.path == "/weather/station-history":
                result = station_history_request(payload)
                self._json_response(200, result)
                return

            if self.path == "/weather/station-latest":
                result = station_latest_request(payload)
                self._json_response(200, result)
                return

            if self.path == "/weather/station-source-plan":
                result = station_source_plan_request(payload)
                self._json_response(200, result)
                return

            if self.path == "/weather/source-coverage":
                result = source_coverage_request(payload)
                self._json_response(200, result)
                return

            if self.path == "/weather/resolution-status":
                result = resolution_status_request(payload)
                self._json_response(200, result)
                return

            if self.path == "/weather/monitor-paper-resolution":
                result = monitor_paper_resolution_request(payload)
                self._json_response(200, result)
                return

            if self.path == "/weather/paper-cycle":
                result = paper_cycle_request(payload)
                self._json_response(200, result)
                return

            if self.path == "/ops/live-preflight":
                result = ops_live_preflight_request(payload)
                self._json_response(200, result)
                return

            self._json_response(404, {"status": "error", "message": f"unknown path: {self.path}"})
        except ValueError as exc:
            self._json_response(400, {"status": "error", "message": str(exc)})
        except Exception as exc:  # pragma: no cover - defensive boundary
            self._json_response(500, {"status": "error", "message": "internal error"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON body: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _require_string(self, payload: dict[str, Any], field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} is required")
        return value

    def _json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def strategy_config_store() -> StrategyConfigStore:
    return StrategyConfigStore()


def strategy_config_payload(config: Any) -> dict[str, Any]:
    return {
        "strategy_id": config.strategy_id,
        "enabled": config.enabled,
        "mode": config.mode.value,
        "allow_live": config.allow_live,
        "settings": dict(config.settings),
    }


def strategy_config_mutation_request(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) < 3 or parts[0] != "strategies" or parts[1] != "config":
        raise ValueError("invalid strategy config path")
    strategy_id = parts[2]
    if not strategy_id:
        raise ValueError("strategy_id is required")
    store = strategy_config_store()
    if len(parts) == 3:
        config = store.update_config(strategy_id, payload)
    elif len(parts) == 4 and parts[3] == "enable":
        config = store.set_enabled(strategy_id, True)
    elif len(parts) == 4 and parts[3] == "disable":
        config = store.set_enabled(strategy_id, False)
    elif len(parts) == 4 and parts[3] == "mode":
        mode = _required_string(payload, "mode")
        allow_live = payload.get("allow_live")
        config = store.set_mode(strategy_id, mode, allow_live=bool(allow_live) if allow_live is not None else None)
    else:
        raise ValueError("unknown strategy config action")
    return {"strategy": strategy_config_payload(config)}


def fetch_markets_request(payload: dict[str, Any]) -> list[dict[str, Any]]:
    source = _coerce_source(payload.get("source", "fixture"))
    limit_value = _coerce_limit(payload.get("limit", 100))
    return _normalized_weather_markets(source=source, limit=limit_value)


def polymarket_weather_markets_query(query: dict[str, list[str]]) -> dict[str, Any]:
    source = _coerce_source(_first_query_value(query, "source") or "fixture")
    limit_value = _coerce_limit(_first_query_value(query, "limit") or 100)
    return {
        "source": source,
        "limit": limit_value,
        "markets": _normalized_weather_markets(source=source, limit=limit_value),
    }


def ops_status_request() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "prediction_core_python",
        "mode": "read_only",
        "orders_enabled": False,
    }


def ops_risk_request() -> dict[str, Any]:
    return {
        "status": "ok",
        "mode": "read_only",
        "orders_enabled": False,
        "risk": {
            "live_submit_enabled": False,
            "max_order_size_usd": 0.0,
            "open_order_count": 0,
        },
    }


def ops_reconciliation_request() -> dict[str, Any]:
    return {
        "status": "ok",
        "mode": "read_only",
        "orders_enabled": False,
        "reconciliation": {
            "open_order_count": 0,
            "unmatched_fill_count": 0,
            "pending_cancel_count": 0,
        },
    }


def ops_live_preflight_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "ok",
        "mode": "read_only",
        "orders_enabled": False,
        "preflight": {
            "would_submit_live_order": False,
            "checks": [
                {"name": "operator_api_read_only", "status": "ok"},
            ],
        },
        "request": _redact_secrets(payload),
    }


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): ("[REDACTED]" if _is_secret_key(str(key)) else _redact_secrets(item)) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def _is_secret_key(key: str) -> bool:
    normalized = key.lower()
    return any(token in normalized for token in ("secret", "token", "key", "password", "credential"))


def _normalized_weather_markets(*, source: str, limit: int) -> list[dict[str, Any]]:
    markets = [normalize_market_record(market) for market in list_weather_markets(source=source, limit=limit)]
    return markets[:limit]


def _first_query_value(query: dict[str, list[str]], field: str) -> str | None:
    values = query.get(field)
    if not values:
        return None
    return values[0]


def _coerce_source(source: Any) -> str:
    if source not in {"fixture", "live"}:
        raise ValueError("source must be 'fixture' or 'live'")
    return str(source)


def _coerce_limit(limit: Any) -> int:
    try:
        limit_value = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    if limit_value < 1:
        raise ValueError("limit must be >= 1")
    return limit_value


def score_market_request(payload: dict[str, Any]) -> dict[str, Any]:
    market_id = payload.get("market_id")
    if isinstance(market_id, str) and market_id.strip():
        source = payload.get("source", "fixture")
        if source not in {"fixture", "live"}:
            raise ValueError("source must be 'fixture' or 'live'")
        return _score_market_from_market_id(market_id.strip(), source=source)

    question = payload.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is required when market_id is absent")

    yes_price = payload.get("yes_price")
    if yes_price is None:
        raise ValueError("yes_price is required when using question")

    try:
        yes_price_value = float(yes_price)
    except (TypeError, ValueError) as exc:
        raise ValueError("yes_price must be numeric") from exc

    source = payload.get("source", "fixture")
    if source not in {"fixture", "live"}:
        raise ValueError("source must be 'fixture' or 'live'")
    infer_default_resolution = _optional_bool(payload.get("infer_default_resolution"))
    result = score_market_from_question(
        question.strip(),
        yes_price_value,
        resolution_source=_optional_string(payload.get("resolution_source")),
        description=_optional_string(payload.get("description")),
        rules=_optional_string(payload.get("rules")),
        market_data=_market_data_from_payload(payload),
        live=(source == "live"),
        infer_default_resolution=bool(infer_default_resolution),
    )
    execution_costs = _execution_quote_from_payload(payload)
    if execution_costs is not None:
        result["execution_costs"] = execution_costs
    return result


def station_history_request(payload: dict[str, Any]) -> dict[str, Any]:
    market_id = _required_string(payload, "market_id")
    source = _coerce_source(payload.get("source", "live"))
    start_date = _required_string(payload, "start_date")
    end_date = _required_string(payload, "end_date")
    return station_history_for_market_id(market_id, source=source, start_date=start_date, end_date=end_date)


def station_latest_request(payload: dict[str, Any]) -> dict[str, Any]:
    market_id = _required_string(payload, "market_id")
    source = _coerce_source(payload.get("source", "live"))
    return station_latest_for_market_id(market_id, source=source)


def station_source_plan_request(payload: dict[str, Any]) -> dict[str, Any]:
    market_id = _required_string(payload, "market_id")
    source = _coerce_source(payload.get("source", "live"))
    return station_source_plan_for_market_id(
        market_id,
        source=source,
        start_date=_optional_string(payload.get("start_date")),
        end_date=_optional_string(payload.get("end_date")),
    )


def source_coverage_request(payload: dict[str, Any]) -> dict[str, Any]:
    return build_weather_source_coverage_report().to_dict()


def resolution_status_request(payload: dict[str, Any]) -> dict[str, Any]:
    market_id = _required_string(payload, "market_id")
    source = _coerce_source(payload.get("source", "live"))
    date = _required_string(payload, "date")
    return resolution_status_for_market_id(market_id, source=source, date=date)


def monitor_paper_resolution_request(payload: dict[str, Any]) -> dict[str, Any]:
    market_id = _required_string(payload, "market_id")
    source = _coerce_source(payload.get("source", "live"))
    date = _required_string(payload, "date")
    paper_side = _required_string(payload, "paper_side")
    if paper_side not in {"yes", "no"}:
        raise ValueError("paper_side must be 'yes' or 'no'")
    return write_paper_resolution_monitor(
        market_id=market_id,
        source=source,
        settlement_date=date,
        paper_side=paper_side,
        paper_notional_usd=_optional_number(payload.get("paper_notional_usd")),
        paper_shares=_optional_number(payload.get("paper_shares")),
        output_dir=_optional_string(payload.get("output_dir")) or "/home/jul/prediction_core/data/polymarket",
    )


def paper_cycle_request(payload: dict[str, Any]) -> dict[str, Any]:
    run_id = _required_string(payload, "run_id")
    if not isinstance(payload.get("market_id"), str) or not str(payload.get("market_id", "")).strip():
        return live_paper_cycle_request(payload, run_id=run_id)

    market_id = _required_string(payload, "market_id")

    question = _optional_string(payload.get("question"))
    yes_price = payload.get("yes_price")
    if yes_price is not None and question is None:
        raise ValueError("question is required when yes_price is provided")
    score_bundle = None
    derived_yes_price = None
    if question is not None:
        if yes_price is None:
            raise ValueError("yes_price is required when question is provided")
        derived_yes_price = _coerce_unit_price(yes_price, field="yes_price")
        score_bundle = score_market_from_question(
            question,
            derived_yes_price,
            resolution_source=_optional_string(payload.get("resolution_source")),
            description=_optional_string(payload.get("description")),
            rules=_optional_string(payload.get("rules")),
            market_data=_market_data_from_payload(payload),
            live=(_coerce_source(payload.get("source", "fixture")) == "live"),
            infer_default_resolution=True,
        )
        execution_quote = _execution_quote_from_payload(payload)
        if execution_quote is not None:
            score_bundle["execution_costs"] = execution_quote

    requested_quantity = derive_requested_quantity(
        requested_quantity=_optional_number(payload.get("requested_quantity")),
        bankroll_usd=_optional_number(payload.get("bankroll_usd")),
        yes_price=derived_yes_price,
        score_bundle=score_bundle,
    )

    filled_quantity, fill_price = derive_filled_execution(
        filled_quantity=_optional_number(payload.get("filled_quantity")),
        fill_price=_optional_unit_price(payload.get("fill_price"), field="fill_price"),
        requested_quantity=requested_quantity,
        yes_price=derived_yes_price,
        score_bundle=score_bundle,
    )

    reference_price = _optional_unit_price(payload.get("reference_price"), field="reference_price")
    if reference_price is None and score_bundle is not None:
        score_info = score_bundle.get("score")
        if isinstance(score_info, dict):
            edge_theoretical = score_info.get("edge_theoretical")
            if isinstance(edge_theoretical, (int, float)):
                reference_price = round(float(edge_theoretical), 6)

    position_side = _string_with_default(payload, "position_side", default="yes")
    execution_side = _string_with_default(payload, "execution_side", default="buy")

    execution_costs = _execution_costs_from_score_bundle(score_bundle)
    explicit_fee_paid = _optional_number(payload.get("fee_paid"))
    manual_fill_requested = payload.get("filled_quantity") is not None or payload.get("fill_price") is not None
    bid_levels = _book_levels(payload.get("bids"))
    ask_levels = _book_levels(payload.get("asks"))
    has_book_liquidity = bool(bid_levels or ask_levels)
    metadata = _paper_cycle_metadata(
        question=question,
        score_bundle=score_bundle,
        auto_derived=not manual_fill_requested,
        execution_costs=execution_costs,
    )

    if has_book_liquidity and explicit_fee_paid is None and not manual_fill_requested:
        simulation = simulate_paper_trade_from_execution(
            run_id=run_id,
            market_id=market_id,
            book=OrderBookSnapshot(bids=bid_levels, asks=ask_levels),
            side=execution_side,
            size=requested_quantity,
            is_maker=False,
            trading_fees=TradingFeeSchedule(
                maker_bps=0.0,
                taker_bps=_number_with_default(payload, "transaction_fee_bps", default=_number_with_default(payload, "taker_fee_bps", default=0.0)),
                min_fee=0.0,
            ),
            transfer_fees=TransferFeeSchedule(
                deposit_fixed=_number_with_default(payload, "deposit_fee_usd", default=0.0),
                deposit_bps=_number_with_default(payload, "deposit_fee_bps", default=0.0),
                withdrawal_fixed=_number_with_default(payload, "withdrawal_fee_usd", default=0.0),
                withdrawal_bps=_number_with_default(payload, "withdrawal_fee_bps", default=0.0),
            ),
            edge_gross=0.0,
            position_side=PaperPositionSide(position_side),
            reference_price=reference_price,
            metadata=metadata,
        )
    else:
        if explicit_fee_paid is None:
            fee_paid = _derive_fee_paid_from_execution_costs(
                gross_notional=round(filled_quantity * fill_price, 6),
                filled_quantity=filled_quantity,
                execution_costs=execution_costs,
            )
        else:
            fee_paid = explicit_fee_paid
        if fee_paid < 0:
            raise ValueError("fee_paid must be >= 0")
        simulation = _manual_paper_trade_simulation(
            run_id=run_id,
            market_id=market_id,
            requested_quantity=requested_quantity,
            filled_quantity=filled_quantity,
            fill_price=fill_price,
            fee_paid=fee_paid,
            reference_price=reference_price,
            position_side=position_side,
            execution_side=execution_side,
            metadata=metadata,
        )
    postmortem = simulation.postmortem()
    return {
        "simulation": simulation.model_dump(mode="json"),
        "postmortem": postmortem.model_dump(mode="json"),
        "score_bundle": score_bundle,
    }


def live_paper_cycle_request(payload: dict[str, Any], *, run_id: str | None = None) -> dict[str, Any]:
    resolved_run_id = run_id or _required_string(payload, "run_id")
    source = _coerce_source(payload.get("source", "live"))
    limit_value = _coerce_limit(payload.get("limit", 25))
    max_impact_bps = _optional_number(payload.get("max_impact_bps")) if "max_impact_bps" in payload else None

    fetch_limit = _live_cycle_fetch_limit(limit_value)
    raw_markets = list_weather_markets(source=source, limit=fetch_limit)
    markets: list[dict[str, Any]] = []
    pre_filter_reasons: dict[str, int] = {}
    for raw_market in raw_markets:
        market = dict(raw_market)
        skip_reason = _pre_score_skip_reason(market)
        if skip_reason is not None:
            pre_filter_reasons[skip_reason] = pre_filter_reasons.get(skip_reason, 0) + 1
            continue
        markets.append(market)
        if len(markets) >= limit_value:
            break

    results: list[dict[str, Any]] = []
    scored_count = 0
    traded_count = 0
    skipped_reasons: dict[str, int] = {}
    filtered_reasons: dict[str, int] = {}

    for market in markets:
        market_id = str(market.get("id", "")).strip()
        if not market_id:
            continue
        score_bundle = _score_market_from_market_id(market_id, source=source, max_impact_bps=max_impact_bps)
        scored_count += 1
        post_score_filter_reason = _post_score_filter_reason(market, score_bundle)
        if post_score_filter_reason is not None:
            filtered_reasons[post_score_filter_reason] = filtered_reasons.get(post_score_filter_reason, 0) + 1
            skipped_reasons[post_score_filter_reason] = skipped_reasons.get(post_score_filter_reason, 0) + 1
            results.append(_paper_cycle_scored_skip_market_result(run_id=resolved_run_id, market_id=market_id, market=market, score_bundle=score_bundle, payload=payload, skip_reason=post_score_filter_reason))
            continue
        decision_status = _decision_status(score_bundle)
        if decision_status in {"trade", "trade_small"}:
            market_result = _paper_cycle_tradeable_market_result(run_id=resolved_run_id, market_id=market_id, market=market, score_bundle=score_bundle, payload=payload)
            simulation = market_result.get("simulation")
            if isinstance(simulation, dict) and simulation.get("status") in {"filled", "partial"}:
                traded_count += 1
            results.append(market_result)
        else:
            skipped_reasons["decision_not_tradeable"] = skipped_reasons.get("decision_not_tradeable", 0) + 1
            results.append(_paper_cycle_scored_skip_market_result(run_id=resolved_run_id, market_id=market_id, market=market, score_bundle=score_bundle, payload=payload))

    summary = {
        "selected": len(markets),
        "raw_candidates": len(raw_markets),
        "fetch_limit": fetch_limit,
        "scored": scored_count,
        "scoreable": scored_count,
        "traded": traded_count,
        "skipped": len(results) - traded_count,
        "skipped_reasons": dict(sorted(skipped_reasons.items())),
    }
    if pre_filter_reasons:
        summary["pre_filtered"] = sum(pre_filter_reasons.values())
        summary["pre_filter_reasons"] = dict(sorted(pre_filter_reasons.items()))
    if filtered_reasons:
        summary["filtered_out"] = sum(filtered_reasons.values())
        summary["filtered_reasons"] = dict(sorted(filtered_reasons.items()))

    return {
        "run_id": resolved_run_id,
        "source": source,
        "limit": limit_value,
        "summary": summary,
        "markets": results,
    }


def paper_cycle_opportunity_report_request(payload: dict[str, Any]) -> dict[str, Any]:
    cycle = live_paper_cycle_request(payload)
    compact_opportunities = [_compact_opportunity(item) for item in cycle.get("markets", []) if isinstance(item, dict)]
    if not _truthy(payload.get("include_skipped")) or _truthy(payload.get("tradeable_only")):
        compact_opportunities = [opportunity for opportunity in compact_opportunities if opportunity.get("decision_status") in {"trade", "trade_small"}]
    compact_opportunities = [opportunity for opportunity in compact_opportunities if _opportunity_passes_thresholds(opportunity, payload)]
    ranked = sorted(
        compact_opportunities,
        key=_opportunity_sort_key,
    )
    for index, opportunity in enumerate(ranked, start=1):
        opportunity["rank"] = index
    return {
        "run_id": cycle.get("run_id"),
        "source": cycle.get("source"),
        "limit": cycle.get("limit"),
        "summary": cycle.get("summary", {}),
        "opportunities": ranked,
    }


def _compact_opportunity(market_result: dict[str, Any]) -> dict[str, Any]:
    market = market_result.get("market") if isinstance(market_result.get("market"), dict) else {}
    score_bundle = market_result.get("score_bundle") if isinstance(market_result.get("score_bundle"), dict) else {}
    score_info = score_bundle.get("score") if isinstance(score_bundle.get("score"), dict) else {}
    edge_info = score_bundle.get("edge") if isinstance(score_bundle.get("edge"), dict) else {}
    execution_info = score_bundle.get("execution") if isinstance(score_bundle.get("execution"), dict) else {}
    decision_info = score_bundle.get("decision") if isinstance(score_bundle.get("decision"), dict) else {}
    source_route = score_bundle.get("source_route") if isinstance(score_bundle.get("source_route"), dict) else {}

    opportunity: dict[str, Any] = {
        "rank": 0,
        "market_id": str(market_result.get("market_id", market.get("id", ""))),
        "question": _optional_string(market.get("question")) or "",
        "decision_status": str(market_result.get("decision_status", "skipped")),
        "score": _rounded_optional_number(score_info.get("total_score")),
        "grade": score_info.get("grade"),
        "probability_edge": _rounded_optional_number(edge_info.get("probability_edge")),
        "spread": _rounded_optional_number(execution_info.get("spread"), market.get("spread")),
        "all_in_cost_bps": _rounded_optional_number(execution_info.get("all_in_cost_bps")),
        "order_book_depth_usd": _rounded_optional_number(execution_info.get("order_book_depth_usd")),
        "hours_to_resolution": _rounded_optional_number(execution_info.get("hours_to_resolution"), market.get("hours_to_resolution")),
    }
    if source_route:
        _add_source_route_summary(opportunity, source_route)
        opportunity["source_route"] = _compact_source_route(source_route)
    skip_reason = market_result.get("skip_reason")
    if isinstance(skip_reason, str) and skip_reason:
        opportunity["skip_reason"] = skip_reason
    reasons = decision_info.get("reasons")
    if isinstance(reasons, list) and reasons:
        opportunity["reasons"] = [str(reason) for reason in reasons]
    return opportunity


def _compact_source_route(source_route: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "provider",
        "station_code",
        "station_name",
        "source_url",
        "latest_url",
        "history_url",
        "direct",
        "supported",
        "latency_tier",
        "latency_priority",
        "polling_focus",
        "manual_review_needed",
        "reason",
    )
    return {
        key: _default_source_route_value(key, source_route)
        for key in keys
        if key in source_route or key in {"history_url", "manual_review_needed"}
    }


def _default_source_route_value(key: str, source_route: dict[str, Any]) -> Any:
    if key == "manual_review_needed":
        return bool(source_route.get("manual_review_needed"))
    return source_route.get(key)


def _add_source_route_summary(opportunity: dict[str, Any], source_route: dict[str, Any]) -> None:
    provider = source_route.get("provider")
    if provider is not None:
        opportunity["source_provider"] = str(provider)
    station_code = source_route.get("station_code")
    if station_code is not None:
        opportunity["source_station_code"] = str(station_code)
    if "direct" in source_route:
        opportunity["source_direct"] = bool(source_route.get("direct"))
    latency_tier = source_route.get("latency_tier")
    if latency_tier is not None:
        opportunity["source_latency_tier"] = str(latency_tier)
    latency_priority = source_route.get("latency_priority")
    if latency_priority is not None:
        opportunity["source_latency_priority"] = str(latency_priority)
    polling_focus = source_route.get("polling_focus")
    if polling_focus is not None:
        opportunity["source_polling_focus"] = str(polling_focus)
    latest_url = source_route.get("latest_url")
    if latest_url is not None:
        opportunity["source_latest_url"] = str(latest_url)


def _opportunity_sort_key(opportunity: dict[str, Any]) -> tuple[int, float, str]:
    status = opportunity.get("decision_status")
    tradeable = status in {"trade", "trade_small"}
    total_score = _optional_number(opportunity.get("score")) or 0.0
    probability_edge = _optional_number(opportunity.get("probability_edge")) or 0.0
    all_in_cost_bps = _optional_number(opportunity.get("all_in_cost_bps")) or 0.0
    spread = _optional_number(opportunity.get("spread")) or 0.0
    net_interest = total_score + (probability_edge * 100.0) - (all_in_cost_bps / 100.0) - (spread * 100.0)
    return (0 if tradeable else 1, -net_interest, str(opportunity.get("market_id", "")))


def _opportunity_passes_thresholds(opportunity: dict[str, Any], payload: dict[str, Any]) -> bool:
    min_edge = _optional_number(payload.get("min_edge")) if "min_edge" in payload else None
    if min_edge is not None and (_optional_number(opportunity.get("probability_edge")) or 0.0) < min_edge:
        return False

    max_cost_bps = _optional_number(payload.get("max_cost_bps")) if "max_cost_bps" in payload else None
    if max_cost_bps is not None:
        cost_bps = _optional_number(opportunity.get("all_in_cost_bps"))
        if cost_bps is None or cost_bps > max_cost_bps:
            return False

    min_depth_usd = _optional_number(payload.get("min_depth_usd")) if "min_depth_usd" in payload else None
    if min_depth_usd is not None and (_optional_number(opportunity.get("order_book_depth_usd")) or 0.0) < min_depth_usd:
        return False

    return True


def _rounded_optional_number(*values: Any) -> float | None:
    for value in values:
        number = _optional_number(value)
        if number is not None:
            return round(number, 6)
    return None


def _paper_cycle_tradeable_market_result(*, run_id: str, market_id: str, market: dict[str, Any], score_bundle: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    yes_price = _market_yes_price(market)
    requested_quantity = derive_requested_quantity(
        requested_quantity=_optional_number(payload.get("requested_quantity")),
        bankroll_usd=_optional_number(payload.get("bankroll_usd")),
        yes_price=yes_price,
        score_bundle=score_bundle,
    )
    filled_quantity, fill_price = derive_filled_execution(filled_quantity=None, fill_price=None, requested_quantity=requested_quantity, yes_price=yes_price, score_bundle=score_bundle)
    execution_costs = _execution_costs_from_score_bundle(score_bundle)
    metadata = _paper_cycle_metadata(question=_optional_string(market.get("question")), score_bundle=score_bundle, auto_derived=True, execution_costs=execution_costs)
    simulation = _manual_paper_trade_simulation(
        run_id=run_id,
        market_id=market_id,
        requested_quantity=requested_quantity,
        filled_quantity=filled_quantity,
        fill_price=fill_price,
        fee_paid=_derive_fee_paid_from_execution_costs(gross_notional=round(filled_quantity * fill_price, 6), filled_quantity=filled_quantity, execution_costs=execution_costs),
        reference_price=_reference_price_from_score_bundle(score_bundle),
        position_side=_string_with_default(payload, "position_side", default="yes"),
        execution_side=_string_with_default(payload, "execution_side", default="buy"),
        metadata=metadata,
    )
    return _paper_cycle_market_result_payload(market_id=market_id, market=market, score_bundle=score_bundle, simulation=simulation)


def _paper_cycle_scored_skip_market_result(
    *,
    run_id: str,
    market_id: str,
    market: dict[str, Any],
    score_bundle: dict[str, Any],
    payload: dict[str, Any],
    skip_reason: str = "decision_not_tradeable",
) -> dict[str, Any]:
    simulation = _skipped_paper_trade_simulation(
        run_id=run_id,
        market_id=market_id,
        market=market,
        requested_quantity=_optional_number(payload.get("requested_quantity")) or 0.0,
        score_bundle=score_bundle,
        skip_reason=skip_reason,
        payload=payload,
    )
    return _paper_cycle_market_result_payload(market_id=market_id, market=market, score_bundle=score_bundle, simulation=simulation, skip_reason=skip_reason)


def _paper_cycle_skipped_market_result(*, run_id: str, market_id: str, market: dict[str, Any], skip_reason: str, payload: dict[str, Any]) -> dict[str, Any]:
    simulation = _skipped_paper_trade_simulation(
        run_id=run_id,
        market_id=market_id,
        market=market,
        requested_quantity=_optional_number(payload.get("requested_quantity")) or 0.0,
        score_bundle=None,
        skip_reason=skip_reason,
        payload=payload,
    )
    return _paper_cycle_market_result_payload(market_id=market_id, market=market, score_bundle=None, simulation=simulation, skip_reason=skip_reason)


def _skipped_paper_trade_simulation(*, run_id: str, market_id: str, market: dict[str, Any], requested_quantity: float, score_bundle: dict[str, Any] | None, skip_reason: str, payload: dict[str, Any]):
    metadata = _paper_cycle_metadata(question=_optional_string(market.get("question")), score_bundle=score_bundle, auto_derived=True, execution_costs=_execution_costs_from_score_bundle(score_bundle))
    metadata["skip_reason"] = skip_reason
    return _manual_paper_trade_simulation(
        run_id=run_id,
        market_id=market_id,
        requested_quantity=requested_quantity,
        filled_quantity=0.0,
        fill_price=max(_market_yes_price(market), 0.0),
        fee_paid=0.0,
        reference_price=_reference_price_from_score_bundle(score_bundle),
        position_side=_string_with_default(payload, "position_side", default="yes"),
        execution_side=_string_with_default(payload, "execution_side", default="buy"),
        metadata=metadata,
    )


def _paper_cycle_market_result_payload(*, market_id: str, market: dict[str, Any], score_bundle: dict[str, Any] | None, simulation: Any, skip_reason: str | None = None) -> dict[str, Any]:
    postmortem = simulation.postmortem()
    simulation_payload = simulation.model_dump(mode="json")
    postmortem_payload = postmortem.model_dump(mode="json")
    simulation_status = str(simulation_payload.get("status", ""))
    postmortem_recommendation = str(postmortem_payload.get("recommendation", ""))
    result: dict[str, Any] = {
        "market_id": market_id,
        "market": normalize_market_record(market),
        "decision_status": _decision_status(score_bundle) or "skipped",
        "simulation_status": simulation_status,
        "postmortem_recommendation": postmortem_recommendation,
        "scoreable": score_bundle is not None,
        "traded": simulation_status in {"filled", "partial"},
        "simulation": simulation_payload,
        "postmortem": postmortem_payload,
        "score_bundle": score_bundle,
    }
    if skip_reason is not None:
        result["skip_reason"] = skip_reason
    return result


def _live_cycle_fetch_limit(limit_value: int) -> int:
    return max(limit_value, min(limit_value * 3, 250))


def _pre_score_skip_reason(market: dict[str, Any]) -> str | None:
    hours_to_resolution = _optional_number(market.get("hours_to_resolution"))
    if hours_to_resolution is not None and hours_to_resolution <= 0:
        return "market_already_resolving_or_resolved"
    best_bid = _optional_number(market.get("best_bid")) or 0.0
    best_ask = _optional_number(market.get("best_ask")) or 0.0
    yes_price = _optional_number(market.get("yes_price")) or 0.0
    if best_bid <= 0.0 and best_ask <= 0.0 and yes_price <= 0.0:
        return "missing_tradeable_quote"
    spread = _optional_number(market.get("spread"))
    if spread is None and best_bid > 0.0 and best_ask > 0.0:
        spread = round(best_ask - best_bid, 6)
    order_book_depth_usd = _optional_number(market.get("order_book_depth_usd"))
    if spread is not None and spread >= 0.95:
        return "insufficient_executable_depth"
    if order_book_depth_usd is not None and order_book_depth_usd < 1.0:
        return "insufficient_executable_depth"
    return None


def _post_score_filter_reason(market: dict[str, Any], score_bundle: dict[str, Any]) -> str | None:
    execution = score_bundle.get("execution") if isinstance(score_bundle.get("execution"), dict) else {}
    best_effort_reason = execution.get("best_effort_reason")
    if isinstance(best_effort_reason, str) and best_effort_reason:
        return best_effort_reason

    fillable_size_usd = _optional_number(execution.get("fillable_size_usd"))
    if fillable_size_usd is not None and fillable_size_usd < 25.0:
        return "tiny_fillable_size"

    slippage_risk = execution.get("slippage_risk")
    if isinstance(slippage_risk, str) and slippage_risk.lower() == "high":
        return "high_slippage_risk"

    spread = _optional_number(execution.get("spread"))
    if spread is None:
        spread = _optional_number(market.get("spread"))
    if spread is not None and spread >= 0.07:
        return "wide_spread"

    yes_price = _market_yes_price(market)
    if yes_price <= 0.01 or yes_price >= 0.99:
        return "extreme_price"

    return None


def _market_yes_price(market: dict[str, Any]) -> float:
    yes_price = _optional_unit_price(market.get("yes_price"), field="yes_price")
    if yes_price is not None and yes_price > 0.0:
        return yes_price
    best_ask = _optional_unit_price(market.get("best_ask"), field="best_ask")
    if best_ask is not None and best_ask > 0.0:
        return best_ask
    best_bid = _optional_unit_price(market.get("best_bid"), field="best_bid")
    if best_bid is not None and best_bid > 0.0:
        return best_bid
    return 0.0


def _decision_status(score_bundle: dict[str, Any] | None) -> str | None:
    if not isinstance(score_bundle, dict):
        return None
    decision_info = score_bundle.get("decision")
    if isinstance(decision_info, dict) and isinstance(decision_info.get("status"), str):
        return decision_info["status"]
    return None


def _reference_price_from_score_bundle(score_bundle: dict[str, Any] | None) -> float | None:
    if not isinstance(score_bundle, dict):
        return None
    score_info = score_bundle.get("score")
    if isinstance(score_info, dict):
        edge_theoretical = score_info.get("edge_theoretical")
        if isinstance(edge_theoretical, (int, float)):
            return round(float(edge_theoretical), 6)
    return None


def _manual_paper_trade_simulation(
    *,
    run_id: str,
    market_id: str,
    requested_quantity: float,
    filled_quantity: float,
    fill_price: float,
    fee_paid: float,
    reference_price: float | None,
    position_side: str,
    execution_side: str,
    metadata: dict[str, Any],
):
    from prediction_core.paper.simulation import PaperTradeFill, PaperTradeSimulation, PaperTradeStatus

    if filled_quantity == 0:
        status = PaperTradeStatus.skipped
    elif filled_quantity < requested_quantity:
        status = PaperTradeStatus.partial
    else:
        status = PaperTradeStatus.filled

    gross_notional = round(filled_quantity * fill_price, 6)
    fills = []
    if filled_quantity > 0:
        fills.append(
            PaperTradeFill(
                trade_id=f"paper_http_{run_id}",
                run_id=run_id,
                market_id=market_id,
                position_side=position_side,
                execution_side=execution_side,
                requested_quantity=requested_quantity,
                filled_quantity=filled_quantity,
                fill_price=fill_price,
                gross_notional=gross_notional,
                fee_paid=fee_paid,
            )
        )

    return PaperTradeSimulation(
        trade_id=f"paper_http_{run_id}",
        run_id=run_id,
        market_id=market_id,
        position_side=position_side,
        execution_side=execution_side,
        requested_quantity=requested_quantity,
        filled_quantity=filled_quantity,
        average_fill_price=fill_price if filled_quantity > 0 else None,
        reference_price=reference_price,
        gross_notional=gross_notional,
        fee_paid=fee_paid,
        stake=gross_notional,
        status=status,
        fills=fills,
        metadata=metadata,
    )


def _paper_cycle_metadata(
    *,
    question: str | None,
    score_bundle: dict[str, Any] | None,
    auto_derived: bool,
    execution_costs: dict[str, float],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"source": "http_paper_cycle", "auto_derived_fill": auto_derived}
    if question is not None:
        metadata["question"] = question
    if score_bundle is not None:
        decision_info = score_bundle.get("decision")
        if isinstance(decision_info, dict) and isinstance(decision_info.get("status"), str):
            metadata["decision_status"] = decision_info["status"]
    if execution_costs:
        metadata["execution_costs"] = execution_costs
        metadata["execution"] = execution_costs
    return metadata


def _execution_costs_from_score_bundle(score_bundle: dict[str, Any] | None) -> dict[str, float]:
    if not isinstance(score_bundle, dict):
        return {}

    result: dict[str, float] = {}
    execution_info = score_bundle.get("execution")
    if isinstance(execution_info, dict):
        for key in (
            "transaction_fee_bps",
            "deposit_fee_usd",
            "withdrawal_fee_usd",
            "order_book_depth_usd",
            "expected_slippage_bps",
            "all_in_cost_bps",
            "all_in_cost_usd",
        ):
            value = execution_info.get(key)
            if isinstance(value, (int, float)):
                result[key] = float(value)

    execution_costs = score_bundle.get("execution_costs")
    if isinstance(execution_costs, dict):
        for key, value in execution_costs.items():
            if isinstance(value, (int, float)):
                result[key] = float(value)
    return result


def _market_data_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    market_data: dict[str, Any] = {}
    for key in (
        "best_bid",
        "best_ask",
        "volume",
        "volume_usd",
        "hours_to_resolution",
        "target_order_size_usd",
        "taker_fee_bps",
        "transaction_fee_bps",
        "deposit_fee_usd",
        "withdrawal_fee_usd",
        "deposit_fee_bps",
        "withdrawal_fee_bps",
        "bids",
        "asks",
    ):
        if key in payload:
            market_data[key] = payload[key]
    return market_data


def _execution_quote_from_payload(payload: dict[str, Any]) -> dict[str, float] | None:
    best_bid = _optional_number(payload.get("best_bid"))
    best_ask = _optional_number(payload.get("best_ask"))
    bids = payload.get("bids")
    asks = payload.get("asks")
    if best_bid is None and best_ask is None and not isinstance(bids, list) and not isinstance(asks, list):
        return None

    book = OrderBookSnapshot(
        bids=_book_levels(bids),
        asks=_book_levels(asks),
    )
    target_order_size = _optional_number(payload.get("target_order_size_usd"))
    if target_order_size is None or target_order_size <= 0:
        target_order_size = _required_positive_number(payload, "yes_price")
    trading_fees = TradingFeeSchedule(
        maker_bps=0.0,
        taker_bps=_number_with_default(payload, "transaction_fee_bps", default=_number_with_default(payload, "taker_fee_bps", default=0.0)),
        min_fee=0.0,
    )
    transfer_fees = TransferFeeSchedule(
        deposit_fixed=_number_with_default(payload, "deposit_fee_usd", default=0.0),
        withdrawal_fixed=_number_with_default(payload, "withdrawal_fee_usd", default=0.0),
    )
    execution_costs = quote_execution_cost(
        book=book,
        side=_string_with_default(payload, "execution_side", default="buy"),
        size=target_order_size,
        is_maker=False,
        trading_fees=trading_fees,
        transfer_fees=transfer_fees,
        edge_gross=0.0,
    )
    return execution_costs.to_dict()



def _book_levels(levels: Any) -> list[BookLevel]:
    if not isinstance(levels, list):
        return []
    result: list[BookLevel] = []
    for level in levels:
        if not isinstance(level, dict):
            continue
        price = level.get("price")
        size = level.get("size", level.get("quantity"))
        if not isinstance(price, (int, float)) or not isinstance(size, (int, float)):
            continue
        if float(price) <= 0 or float(size) <= 0:
            continue
        result.append(BookLevel(price=float(price), quantity=float(size)))
    return result


def _derive_fee_paid_from_execution_costs(*, gross_notional: float, filled_quantity: float, execution_costs: dict[str, float]) -> float:
    if gross_notional <= 0 or filled_quantity <= 0:
        return 0.0
    transaction_fee_bps = execution_costs.get("transaction_fee_bps", 0.0)
    deposit_fee_usd = execution_costs.get("deposit_fee_usd", 0.0)
    withdrawal_fee_usd = execution_costs.get("withdrawal_fee_usd", 0.0)
    variable_fee = gross_notional * (transaction_fee_bps / 10000.0)
    total_fee = variable_fee + deposit_fee_usd + withdrawal_fee_usd
    return round(total_fee, 3)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional text fields must be strings")
    text = value.strip()
    return text or None


def _required_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _required_number(payload: dict[str, Any], field: str) -> float:
    value = payload.get(field)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc


def _required_positive_number(payload: dict[str, Any], field: str) -> float:
    value = _required_number(payload, field)
    if value <= 0:
        raise ValueError(f"{field} must be > 0")
    return value


def _required_unit_price(payload: dict[str, Any], field: str) -> float:
    value = _required_number(payload, field)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{field} must be between 0 and 1")
    return value


def _optional_unit_price(value: Any, *, field: str) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{field} must be between 0 and 1")
    return numeric


def _number_with_default(payload: dict[str, Any], field: str, *, default: float) -> float:
    if field not in payload or payload[field] is None:
        return default
    return _required_number(payload, field)


def _coerce_unit_price(value: Any, *, field: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{field} must be between 0 and 1")
    return numeric


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("optional numeric fields must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError("optional numeric fields must be finite")
    return number


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError("optional boolean fields must be booleans")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _string_with_default(payload: dict[str, Any], field: str, *, default: str) -> str:
    value = payload.get(field, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def build_server(*, host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), PredictionCoreHandler)
