from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from prediction_core.paper import (
    PaperTradeFill,
    PaperTradeSimulation,
    PaperTradeStatus,
    derive_filled_execution,
    derive_requested_quantity,
)
from weather_pm.cli import _score_market_from_market_id
from weather_pm.market_parser import parse_market_question
from weather_pm.pipeline import score_market_from_question


class PredictionCoreHandler(BaseHTTPRequestHandler):
    server_version = "prediction_core_python/0.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json_response(200, {"status": "ok", "service": "prediction_core_python"})
            return
        self._json_response(404, {"status": "error", "message": f"unknown path: {self.path}"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self._read_json_body()
        except ValueError as exc:
            self._json_response(400, {"status": "error", "message": str(exc)})
            return

        try:
            if self.path == "/weather/parse-market":
                question = self._require_string(payload, "question")
                result = parse_market_question(question).to_dict()
                self._json_response(200, result)
                return

            if self.path == "/weather/score-market":
                result = score_market_request(payload)
                self._json_response(200, result)
                return

            if self.path == "/weather/paper-cycle":
                result = paper_cycle_request(payload)
                self._json_response(200, result)
                return

            self._json_response(404, {"status": "error", "message": f"unknown path: {self.path}"})
        except ValueError as exc:
            self._json_response(400, {"status": "error", "message": str(exc)})
        except Exception as exc:  # pragma: no cover - defensive boundary
            self._json_response(500, {"status": "error", "message": f"internal error: {exc}"})

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

    return score_market_from_question(
        question.strip(),
        yes_price_value,
        resolution_source=_optional_string(payload.get("resolution_source")),
        description=_optional_string(payload.get("description")),
        rules=_optional_string(payload.get("rules")),
        market_data=_market_data_from_payload(payload),
    )


def paper_cycle_request(payload: dict[str, Any]) -> dict[str, Any]:
    run_id = _required_string(payload, "run_id")
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
        )

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

    position_side = _string_with_default(payload, "position_side", default="yes")
    execution_side = _string_with_default(payload, "execution_side", default="buy")

    execution_costs = _execution_costs_from_score_bundle(score_bundle)
    explicit_fee_paid = _optional_number(payload.get("fee_paid"))
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

    if reference_price is None and score_bundle is not None:
        score_info = score_bundle.get("score")
        if isinstance(score_info, dict):
            edge_theoretical = score_info.get("edge_theoretical")
            if isinstance(edge_theoretical, (int, float)):
                reference_price = round(float(edge_theoretical), 6)

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

    simulation = PaperTradeSimulation(
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
        metadata=_paper_cycle_metadata(
            question=question,
            score_bundle=score_bundle,
            auto_derived=(payload.get("filled_quantity") is None and payload.get("fill_price") is None),
            execution_costs=execution_costs,
        ),
    )
    postmortem = simulation.postmortem()
    return {
        "simulation": simulation.model_dump(mode="json"),
        "postmortem": postmortem.model_dump(mode="json"),
        "score_bundle": score_bundle,
    }


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
    return metadata


def _execution_costs_from_score_bundle(score_bundle: dict[str, Any] | None) -> dict[str, float]:
    if not isinstance(score_bundle, dict):
        return {}
    execution_info = score_bundle.get("execution")
    if not isinstance(execution_info, dict):
        return {}
    result: dict[str, float] = {}
    for key in ("transaction_fee_bps", "deposit_fee_usd", "withdrawal_fee_usd", "order_book_depth_usd", "expected_slippage_bps", "all_in_cost_bps", "all_in_cost_usd"):
        value = execution_info.get(key)
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
        "bids",
        "asks",
    ):
        if key in payload:
            market_data[key] = payload[key]
    return market_data


def _derive_fee_paid_from_execution_costs(*, gross_notional: float, filled_quantity: float, execution_costs: dict[str, float]) -> float:
    if gross_notional <= 0 or filled_quantity <= 0:
        return 0.0
    transaction_fee_bps = execution_costs.get("transaction_fee_bps", 0.0)
    deposit_fee_usd = execution_costs.get("deposit_fee_usd", 0.0)
    withdrawal_fee_usd = execution_costs.get("withdrawal_fee_usd", 0.0)
    variable_fee = gross_notional * (transaction_fee_bps / 10000.0)
    total_fee = variable_fee + deposit_fee_usd + withdrawal_fee_usd
    return float(int(total_fee * 1000.0)) / 1000.0


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
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("optional numeric fields must be numeric") from exc


def _string_with_default(payload: dict[str, Any], field: str, *, default: str) -> str:
    value = payload.get(field, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def build_server(*, host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), PredictionCoreHandler)
