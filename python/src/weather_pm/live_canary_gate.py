from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIRMATION_PHRASE = "I_ACCEPT_MICRO_LIVE_WEATHER_RISK"


class LiveCanaryGateError(ValueError):
    """Raised when live-canary preflight would arm orders without explicit proof."""


@dataclass(frozen=True)
class LiveCanaryConfig:
    enabled: bool = False
    kill_switch: bool = True
    dry_run: bool = True
    allowlist_market_ids: set[str] = field(default_factory=set)
    max_order_usdc: float = 1.0
    max_daily_usdc: float = 1.0
    min_live_quality_score: float = 85.0
    max_spread: float = 0.04
    min_depth_usdc: float = 25.0
    run_id: str | None = None
    confirmation_phrase: str | None = None


def build_live_canary_preflight(
    operator_artifact: dict[str, Any],
    *,
    config: LiveCanaryConfig | None = None,
    output_json: str | Path | None = None,
) -> dict[str, Any]:
    cfg = config or LiveCanaryConfig()
    if cfg.enabled and not cfg.kill_switch and not cfg.dry_run and cfg.confirmation_phrase != CONFIRMATION_PHRASE:
        raise LiveCanaryGateError("live canary requires exact confirmation phrase before any non-dry-run order is armed")
    rows = _live_rows(operator_artifact)
    decisions = [evaluate_live_canary_row(row, config=cfg) for row in rows]
    eligible = [decision for decision in decisions if decision.get("eligible") is True]
    payload: dict[str, Any] = {
        "mode": "LIVE_CANARY_PREFLIGHT",
        "paper_only": not bool(eligible),
        "live_order_allowed": bool(eligible),
        "orders_allowed": bool(eligible),
        "dry_run": cfg.dry_run or not bool(eligible),
        "kill_switch_active": cfg.kill_switch,
        "enabled": cfg.enabled,
        "source_rows": len(rows),
        "eligible_count": len(eligible),
        "blocked_count": len(decisions) - len(eligible),
        "max_order_usdc": cfg.max_order_usdc,
        "max_daily_usdc": cfg.max_daily_usdc,
        "total_armed_notional_usdc": round(sum(_num((d.get("live_execution_payload") or {}).get("notional_usdc")) or 0.0 for d in eligible), 6),
        "confirmation_required": CONFIRMATION_PHRASE,
        "no_real_order_placed": True,
        "decisions": decisions,
    }
    if output_json:
        path = Path(output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload["artifacts"] = {"live_canary_preflight_json": str(path)}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def evaluate_live_canary_row(row: dict[str, Any], *, config: LiveCanaryConfig | None = None) -> dict[str, Any]:
    cfg = config or LiveCanaryConfig()
    blockers = _canary_blockers(row, cfg)
    eligible = not blockers
    notional = min(_requested_notional(row), cfg.max_order_usdc)
    limit_price = _limit_price(row)
    market_id = str(row.get("market_id") or row.get("id") or row.get("condition_id") or "")
    token_id = str(row.get("token_id") or row.get("asset_id") or "")
    side = str(row.get("side") or row.get("candidate_side") or "YES").upper()
    key = _idempotency_key(row, cfg=cfg, notional=notional, limit_price=limit_price)
    payload = None
    if eligible:
        payload = {
            "market_id": market_id,
            "token_id": token_id,
            "side": side,
            "order_type": "limit",
            "limit_price": limit_price,
            "notional_usdc": round(notional, 6),
            "time_in_force": "IOC",
            "client_order_id": key,
            "dry_run": cfg.dry_run,
        }
    return {
        "mode": "LIVE_CANARY",
        "market_id": market_id,
        "token_id": token_id,
        "side": side,
        "eligible": eligible,
        "canary_action": "MICRO_LIVE_LIMIT_ORDER_ALLOWED" if eligible else "DRY_RUN_ONLY",
        "paper_only": not eligible,
        "live_order_allowed": eligible,
        "orders_allowed": eligible,
        "dry_run": cfg.dry_run or not eligible,
        "kill_switch_active": cfg.kill_switch,
        "idempotency_key": key,
        "blockers": blockers,
        "risk_caps": {
            "max_order_usdc": cfg.max_order_usdc,
            "max_daily_usdc": cfg.max_daily_usdc,
            "min_live_quality_score": cfg.min_live_quality_score,
            "max_spread": cfg.max_spread,
            "min_depth_usdc": cfg.min_depth_usdc,
        },
        "live_execution_payload": payload,
    }


def config_from_env(*, run_id: str | None = None) -> LiveCanaryConfig:
    allowlist_raw = os.environ.get("WEATHER_LIVE_CANARY_ALLOWLIST", "")
    allowlist = {item.strip() for item in allowlist_raw.replace(";", ",").split(",") if item.strip()}
    return LiveCanaryConfig(
        enabled=_env_bool("WEATHER_LIVE_CANARY_ENABLED", False),
        kill_switch=_env_bool("WEATHER_LIVE_CANARY_KILL_SWITCH", True),
        dry_run=_env_bool("WEATHER_LIVE_CANARY_DRY_RUN", True),
        allowlist_market_ids=allowlist,
        max_order_usdc=_env_float("WEATHER_LIVE_CANARY_MAX_ORDER_USDC", 1.0),
        max_daily_usdc=_env_float("WEATHER_LIVE_CANARY_MAX_DAILY_USDC", 1.0),
        min_live_quality_score=_env_float("WEATHER_LIVE_CANARY_MIN_QUALITY", 85.0),
        max_spread=_env_float("WEATHER_LIVE_CANARY_MAX_SPREAD", 0.04),
        min_depth_usdc=_env_float("WEATHER_LIVE_CANARY_MIN_DEPTH_USDC", 25.0),
        run_id=run_id or os.environ.get("WEATHER_LIVE_CANARY_RUN_ID"),
        confirmation_phrase=os.environ.get("WEATHER_LIVE_CANARY_CONFIRM"),
    )


def compact_live_canary_preflight(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": payload.get("mode"),
        "paper_only": payload.get("paper_only"),
        "live_order_allowed": payload.get("live_order_allowed"),
        "orders_allowed": payload.get("orders_allowed"),
        "dry_run": payload.get("dry_run"),
        "kill_switch_active": payload.get("kill_switch_active"),
        "enabled": payload.get("enabled"),
        "source_rows": payload.get("source_rows", 0),
        "eligible_count": payload.get("eligible_count", 0),
        "blocked_count": payload.get("blocked_count", 0),
        "total_armed_notional_usdc": payload.get("total_armed_notional_usdc", 0.0),
        "no_real_order_placed": True,
        "artifacts": payload.get("artifacts", {}),
    }


def _canary_blockers(row: dict[str, Any], cfg: LiveCanaryConfig) -> list[str]:
    blockers: list[str] = []
    if not cfg.enabled:
        _append(blockers, "canary_disabled")
    if cfg.kill_switch:
        _append(blockers, "kill_switch_active")
    if cfg.dry_run:
        _append(blockers, "dry_run_only")
    market_id = str(row.get("market_id") or row.get("id") or row.get("condition_id") or "")
    if cfg.allowlist_market_ids and market_id not in cfg.allowlist_market_ids:
        _append(blockers, "market_not_allowlisted")
    if not market_id:
        _append(blockers, "missing_market_id")
    if not (row.get("token_id") or row.get("asset_id")):
        _append(blockers, "missing_token_id")
    gate = str(row.get("autopilot_gate") or row.get("readiness_gate") or row.get("paper_gate") or "").upper()
    if gate not in {"PAPER_MICRO", "PAPER_STRICT", "MICRO_LIVE_CANDIDATE"}:
        _append(blockers, "not_micro_paper_vetted")
    normal_gate = row.get("normal_size_gate") if isinstance(row.get("normal_size_gate"), dict) else {}
    if normal_gate.get("live_ready") is not True:
        _append(blockers, "operator_gate_not_live_ready")
    if _live_quality_score(row) < cfg.min_live_quality_score:
        _append(blockers, "live_quality_below_threshold")
    snapshot = row.get("execution_snapshot") if isinstance(row.get("execution_snapshot"), dict) else {}
    if not snapshot:
        _append(blockers, "missing_execution_snapshot")
    spread = _spread(snapshot)
    if spread is None:
        _append(blockers, "missing_spread")
    elif spread > cfg.max_spread:
        _append(blockers, "wide_spread")
    depth = _depth(snapshot)
    if depth < cfg.min_depth_usdc:
        _append(blockers, "insufficient_depth")
    price = _limit_price(row)
    if price is None:
        _append(blockers, "missing_limit_price")
    elif price <= 0.05 or price >= 0.95:
        _append(blockers, "extreme_price")
    notional = _requested_notional(row)
    if notional <= 0:
        _append(blockers, "missing_notional")
    if notional > cfg.max_order_usdc:
        _append(blockers, "order_cap_exceeded")
    if notional > cfg.max_daily_usdc:
        _append(blockers, "daily_cap_exceeded")
    risk = row.get("portfolio_risk") if isinstance(row.get("portfolio_risk"), dict) else {}
    if str(risk.get("cap_status") or "").lower() == "blocked":
        _append(blockers, "portfolio_risk_blocked")
    if row.get("execution_blocker"):
        _append(blockers, "execution_blocked")
    return blockers


def _live_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("live_rows", "rows", "top_current_candidates", "candidates", "paper_candidates", "live_watchlist"):
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(row) for row in value if isinstance(row, dict)]
    nested = payload.get("operator_report") or payload.get("operator")
    if isinstance(nested, dict):
        return _live_rows(nested)
    return []


def _idempotency_key(row: dict[str, Any], *, cfg: LiveCanaryConfig, notional: float, limit_price: float | None) -> str:
    parts = [
        str(cfg.run_id or row.get("run_id") or ""),
        str(row.get("market_id") or row.get("id") or row.get("condition_id") or ""),
        str(row.get("token_id") or row.get("asset_id") or ""),
        str(row.get("side") or row.get("candidate_side") or "YES").upper(),
        str(limit_price or ""),
        str(round(notional, 6)),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


def _live_quality_score(row: dict[str, Any]) -> float:
    quality = row.get("live_quality") if isinstance(row.get("live_quality"), dict) else {}
    return _num(quality.get("live_quality_score") or row.get("live_quality_score")) or 0.0


def _requested_notional(row: dict[str, Any]) -> float:
    explicit = _num(row.get("requested_notional_usdc"))
    if explicit is not None:
        return explicit
    explicit = _num(row.get("paper_notional_usdc"))
    if explicit is not None:
        return explicit
    risk = row.get("portfolio_risk") if isinstance(row.get("portfolio_risk"), dict) else {}
    return _num(risk.get("approved_size_usdc")) or 0.0


def _limit_price(row: dict[str, Any]) -> float | None:
    return _num(row.get("strict_limit", row.get("strict_limit_price")))


def _spread(snapshot: dict[str, Any]) -> float | None:
    values = [_num(snapshot.get("spread_yes")), _num(snapshot.get("spread_no")), _num(snapshot.get("yes_spread")), _num(snapshot.get("no_spread"))]
    present = [value for value in values if value is not None]
    return min(present) if present else None


def _depth(snapshot: dict[str, Any]) -> float:
    values = [
        _num(snapshot.get(key))
        for key in ("yes_ask_depth_usd", "no_ask_depth_usd", "yes_bid_depth_usd", "no_bid_depth_usd", "order_book_depth_usd", "depth_usd")
    ]
    return max([value for value in values if value is not None] or [0.0])


def _env_bool(key: str, default: bool) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(key: str, default: float) -> float:
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _append(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
