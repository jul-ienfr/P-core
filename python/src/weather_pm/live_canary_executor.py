from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from weather_pm.live_canary_gate import LiveCanaryConfig, config_from_env
from weather_pm.polymarket_live_order_client import PolymarketLiveOrderClient, build_order_client_config_from_env


class LiveOrderClient(Protocol):
    def submit_limit_order(self, payload: dict[str, Any]) -> dict[str, Any]: ...


def execute_live_canary_preflight(
    preflight: dict[str, Any],
    *,
    config: LiveCanaryConfig | None = None,
    client: LiveOrderClient | None = None,
    output_json: str | Path | None = None,
) -> dict[str, Any]:
    cfg = config or config_from_env()
    execution_mode = cfg.mode if cfg.mode in {"shadow", "live"} else "shadow"
    results: list[dict[str, Any]] = []
    live_submitted = False
    for decision in _decisions(preflight):
        payload = decision.get("live_execution_payload") if isinstance(decision, dict) else None
        result_base = {
            "market_id": decision.get("market_id"),
            "token_id": decision.get("token_id"),
            "idempotency_key": decision.get("idempotency_key"),
            "paper_only": execution_mode != "live",
            "live_order_allowed": execution_mode == "live" and bool(payload),
        }
        if not payload:
            results.append({**result_base, "status": "skipped_not_armed"})
            continue
        if execution_mode != "live":
            results.append({**result_base, "status": "skipped_shadow_mode", "payload_preview": _payload_preview(payload)})
            continue
        if client is None:
            results.append({**result_base, "status": "skipped_client_not_configured", "payload_preview": _payload_preview(payload)})
            continue
        response = client.submit_limit_order(dict(payload))
        live_submitted = True
        results.append({**result_base, "status": "submitted", "response": response})
    submitted_count = sum(1 for item in results if item.get("status") == "submitted")
    payload = {
        "mode": "LIVE_CANARY_EXECUTOR",
        "execution_mode": execution_mode,
        "paper_only": execution_mode != "live" or submitted_count == 0,
        "orders_allowed": execution_mode == "live",
        "live_order_allowed": execution_mode == "live",
        "live_order_submitted": live_submitted,
        "submitted_count": submitted_count,
        "skipped_count": len(results) - submitted_count,
        "no_real_order_placed": not live_submitted,
        "results": results,
    }
    if output_json:
        path = Path(output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload["artifacts"] = {"live_canary_execute_json": str(path)}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def execute_live_canary_preflight_from_env(preflight: dict[str, Any], *, output_json: str | Path | None = None) -> dict[str, Any]:
    cfg = config_from_env()
    client: LiveOrderClient | None = None
    if cfg.mode == "live":
        client_config = build_order_client_config_from_env()
        if client_config.configured:
            client = PolymarketLiveOrderClient(client_config)
    return execute_live_canary_preflight(preflight, config=cfg, client=client, output_json=output_json)


def compact_live_canary_execution(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": payload.get("mode"),
        "execution_mode": payload.get("execution_mode"),
        "paper_only": payload.get("paper_only"),
        "orders_allowed": payload.get("orders_allowed"),
        "live_order_allowed": payload.get("live_order_allowed"),
        "live_order_submitted": payload.get("live_order_submitted"),
        "submitted_count": payload.get("submitted_count", 0),
        "skipped_count": payload.get("skipped_count", 0),
        "no_real_order_placed": payload.get("no_real_order_placed", True),
        "artifacts": payload.get("artifacts", {}),
    }


def _decisions(preflight: dict[str, Any]) -> list[dict[str, Any]]:
    decisions = preflight.get("decisions")
    return [item for item in decisions if isinstance(item, dict)] if isinstance(decisions, list) else []


def _payload_preview(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "market_id": payload.get("market_id"),
        "token_id": payload.get("token_id"),
        "side": payload.get("side"),
        "order_type": payload.get("order_type"),
        "limit_price": payload.get("limit_price"),
        "notional_usdc": payload.get("notional_usdc"),
        "time_in_force": payload.get("time_in_force"),
        "client_order_id": payload.get("client_order_id"),
    }
