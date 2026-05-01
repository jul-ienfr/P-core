from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from weather_pm.paper_ledger import PaperLedgerError, paper_ledger_place, paper_ledger_refresh

PAPER_AUTOPILOT_GATES = {"PAPER_STRICT", "PAPER_MICRO"}
MICRO_NOTIONAL_USDC = 1.0


class PaperAutopilotBridgeError(ValueError):
    """Raised when an autopilot artifact asks the bridge to do anything non-paper."""


def build_paper_autopilot_ledger(
    operator_artifact: dict[str, Any],
    *,
    ledger: dict[str, Any] | None = None,
    run_id: str | None = None,
    allow_unknown_gate: bool = True,
) -> dict[str, Any]:
    """Append PAPER_STRICT/PAPER_MICRO rows to a derived strict-limit paper ledger.

    This bridge is intentionally one-way and paper-only: it reads live/operator rows,
    simulates strict-limit fills via :func:`paper_ledger_place`, and appends derived
    ledger orders. It never emits a live execution payload or places real orders.
    """
    if not isinstance(operator_artifact, dict):
        raise PaperAutopilotBridgeError("paper autopilot bridge requires an operator artifact object")

    rows = _live_rows(operator_artifact)
    result = _initial_ledger(ledger)
    skipped: list[dict[str, Any]] = []
    appended = 0
    gates: Counter[str] = Counter()

    for row in rows:
        gate = _gate(row)
        if gate not in PAPER_AUTOPILOT_GATES:
            if gate and not allow_unknown_gate:
                raise PaperAutopilotBridgeError(f"refuses non-paper autopilot gate: {gate}")
            skipped.append(_skip(row, gate=gate, reason="non_paper_gate" if gate else "missing_paper_gate"))
            continue

        reason = _ineligible_reason(row)
        if reason:
            skipped.append(_skip(row, gate=gate, reason=reason))
            continue

        candidate = _candidate_from_row(row, gate=gate, run_id=run_id)
        try:
            placed = paper_ledger_place(candidate, ledger=result)
        except PaperLedgerError as exc:
            skipped.append(_skip(row, gate=gate, reason=str(exc).replace(" ", "_")))
            continue
        order = placed["orders"][-1]
        order.update(
            {
                "source": "paper_autopilot_strict_limit_bridge",
                "append_only": True,
                "idempotency_key": candidate.get("idempotency_key"),
                "would_place_order": True,
                "can_micro_live": False,
                "micro_live_allowed": False,
                "source_autopilot_gate": gate,
                "source_orderbook": candidate["orderbook"],
                "portfolio_risk": row.get("portfolio_risk", {}),
                "risk_controls": _risk_controls(row),
                "live_execution_payload": None,
                "paper_only": True,
                "live_order_allowed": False,
            }
        )
        result = paper_ledger_refresh({**placed, "orders": placed["orders"]}, refreshes={}, settlements={})
        appended += 1
        gates[gate] += 1

    result = paper_ledger_refresh(result, refreshes={}, settlements={})
    result["paper_only"] = True
    result["live_order_allowed"] = False
    result["paper_autopilot_summary"] = {
        "source_rows": len(rows),
        "eligible_rows": sum(gates.values()),
        "appended_orders": appended,
        "skipped_rows": len(skipped),
        "gates": dict(sorted(gates.items())),
        "paper_only": True,
        "live_order_allowed": False,
    }
    result["paper_autopilot_skipped"] = skipped
    return result


def _live_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("live_rows", "rows", "top_current_candidates", "candidates", "paper_candidates"):
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(row) for row in value if isinstance(row, dict)]
    nested = payload.get("operator_report")
    if isinstance(nested, dict):
        return _live_rows(nested)
    return []


def _gate(row: dict[str, Any]) -> str:
    for key in ("autopilot_gate", "gate", "readiness_gate", "paper_gate", "execution_gate", "decision"):
        value = row.get(key)
        if value is not None:
            return str(value).strip().upper()
    return ""


def _ineligible_reason(row: dict[str, Any]) -> str | None:
    if not isinstance(row.get("orderbook"), dict):
        execution = row.get("execution") if isinstance(row.get("execution"), dict) else {}
        if not isinstance(execution.get("orderbook"), dict):
            return "missing_orderbook"
    if _num(row.get("strict_limit", row.get("strict_limit_price"))) is None:
        return "missing_strict_limit"
    if _approved_notional(row, gate=_gate(row)) <= 0.0:
        return "risk_or_size_blocked"
    risk = row.get("portfolio_risk") if isinstance(row.get("portfolio_risk"), dict) else {}
    if str(risk.get("cap_status") or "").lower() == "blocked":
        return "risk_or_size_blocked"
    if row.get("execution_blocker"):
        return "execution_blocked"
    return None


def _candidate_from_row(row: dict[str, Any], *, gate: str, run_id: str | None) -> dict[str, Any]:
    side = str(row.get("side") or row.get("candidate_side") or "YES").upper()
    orderbook = row.get("orderbook") if isinstance(row.get("orderbook"), dict) else (row.get("execution") or {}).get("orderbook")
    return {
        "run_id": run_id or row.get("run_id"),
        "strategy_id": row.get("strategy_id") or "paper_autopilot_strict_limit_bridge",
        "profile_id": row.get("profile_id"),
        "surface_id": row.get("surface_id") or row.get("correlated_surface_id"),
        "market_id": row.get("market_id") or row.get("id") or row.get("condition_id"),
        "token_id": row.get("token_id") or row.get("asset_id"),
        "side": side,
        "strict_limit": _num(row.get("strict_limit", row.get("strict_limit_price"))),
        "spend_usdc": _approved_notional(row, gate=gate),
        "probability_edge": _num(row.get("probability_edge")),
        "source_status": row.get("source_status"),
        "station_status": row.get("station_status"),
        "station": row.get("station") or row.get("source_station_code"),
        "source_url": row.get("source_url"),
        "account_consensus": row.get("account_consensus", {}),
        "model_reason": row.get("model_reason") or row.get("reason"),
        "inconsistency_reason": row.get("inconsistency_reason"),
        "orderbook": orderbook,
        "actual_refresh_price": row.get("actual_refresh_price") or (row.get("execution") or {}).get("top_ask"),
        "order_id": row.get("paper_order_id") or row.get("order_id"),
        "idempotency_key": row.get("idempotency_key") or _idempotency_key(row, gate=gate, run_id=run_id),
    }


def _approved_notional(row: dict[str, Any], *, gate: str) -> float:
    risk = row.get("portfolio_risk") if isinstance(row.get("portfolio_risk"), dict) else {}
    value = _num(risk.get("approved_size_usdc"))
    if value is None:
        value = _num(row.get("paper_notional_usdc", row.get("requested_notional_usdc")))
    if value is None:
        value = MICRO_NOTIONAL_USDC if gate == "PAPER_MICRO" else 0.0
    value = max(value, 0.0)
    if gate == "PAPER_MICRO":
        value = min(value, MICRO_NOTIONAL_USDC)
    return round(value, 6)


def _idempotency_key(row: dict[str, Any], *, gate: str, run_id: str | None) -> str:
    parts = [
        str(run_id or row.get("run_id") or ""),
        str(row.get("market_id") or row.get("id") or row.get("condition_id") or ""),
        str(row.get("token_id") or row.get("asset_id") or ""),
        str(row.get("side") or row.get("candidate_side") or "YES").upper(),
        str(row.get("strict_limit", row.get("strict_limit_price")) or ""),
        str(_approved_notional(row, gate=gate)),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


def _risk_controls(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "portfolio_risk": row.get("portfolio_risk", {}),
        "strict_next_action": row.get("strict_next_action"),
        "execution_blocker": row.get("execution_blocker"),
        "paper_size_label": row.get("paper_size_label"),
    }


def _initial_ledger(ledger: dict[str, Any] | None) -> dict[str, Any]:
    if not ledger:
        return {"orders": []}
    return paper_ledger_refresh(ledger, refreshes={}, settlements={})


def _skip(row: dict[str, Any], *, gate: str, reason: str) -> dict[str, Any]:
    return {"market_id": row.get("market_id") or row.get("id"), "token_id": row.get("token_id") or row.get("asset_id"), "gate": gate, "reason": reason}


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
