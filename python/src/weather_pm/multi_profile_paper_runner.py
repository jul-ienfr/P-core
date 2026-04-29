from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json

from weather_pm.paper_ledger import paper_ledger_place
from weather_pm.strategy_profiles import get_strategy_profile, list_strategy_profiles, strategy_id_for_profile

_ALLOWED_MODES = {"shadow", "paper", "live_dry_run"}
_TRADEABLE_STATUSES = {"trade", "trade_small", "enter"}


class MultiProfilePaperRunnerError(ValueError):
    pass


def run_multi_profile_paper_batch(
    shortlist_payload: dict[str, Any],
    *,
    profile_ids: Iterable[str] | None = None,
    run_id: str | None = None,
    mode: str = "paper",
) -> dict[str, Any]:
    if mode not in _ALLOWED_MODES:
        raise MultiProfilePaperRunnerError("mode must be one of: shadow, paper, live_dry_run")
    run_id = str(run_id or shortlist_payload.get("run_id") or _default_run_id())
    rows = _shortlist_rows(shortlist_payload)
    selected_profile_ids = [str(profile_id) for profile_id in (profile_ids or [profile["id"] for profile in list_strategy_profiles()])]

    ledgers: dict[str, dict[str, Any]] = {}
    profile_summaries: list[dict[str, Any]] = []
    for profile_id in selected_profile_ids:
        profile = get_strategy_profile(profile_id)
        strategy_id = strategy_id_for_profile(profile_id)
        ledger_run_id = f"{run_id}:{strategy_id}:{profile_id}"
        ledger: dict[str, Any] = {
            "run_id": ledger_run_id,
            "parent_run_id": run_id,
            "strategy_id": strategy_id,
            "profile_id": profile_id,
            "mode": mode,
            "paper_only": True,
            "live_order_allowed": False,
            "orders": [],
        }
        skipped = Counter()
        for index, row in enumerate(rows):
            candidate = _candidate_for_profile(row, profile=profile, run_id=ledger_run_id, strategy_id=strategy_id, profile_id=profile_id, mode=mode, index=index)
            if candidate is None:
                skipped["not_tradeable_or_missing_orderbook"] += 1
                continue
            ledger = paper_ledger_place(candidate, ledger=ledger)
            _assert_order_guardrails(ledger["orders"][-1], run_id=ledger_run_id, strategy_id=strategy_id, profile_id=profile_id)
        ledger["summary"] = {**ledger.get("summary", {}), "profile_id": profile_id, "strategy_id": strategy_id, "run_id": ledger_run_id, "mode": mode, "paper_only": True, "live_order_allowed": False, "skipped_counts": dict(skipped)}
        ledgers[profile_id] = ledger
        profile_summaries.append(_profile_summary(ledger))

    return {
        "run_id": run_id,
        "mode": mode,
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_orders": True,
        "shortlist_count": len(rows),
        "profile_count": len(selected_profile_ids),
        "profile_ids": selected_profile_ids,
        "ledgers": ledgers,
        "comparison": _comparison(profile_summaries),
    }


def load_shortlist_payload(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise MultiProfilePaperRunnerError("shortlist JSON must be an object")
    return payload


def write_multi_profile_paper_artifacts(result: dict[str, Any], *, output_dir: str | Path = "data/polymarket") -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    run_id = _safe_name(str(result.get("run_id") or "multi-profile-paper"))
    json_path = output / f"weather_multi_profile_paper_{run_id}.json"
    md_path = output / f"weather_multi_profile_paper_{run_id}.md"
    payload = json.loads(json.dumps(result))
    payload["artifacts"] = {"json": str(json_path), "markdown": str(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_multi_profile_paper_markdown(payload), encoding="utf-8")
    return payload


def render_multi_profile_paper_markdown(result: dict[str, Any]) -> str:
    rows = result.get("comparison", {}).get("profiles", []) if isinstance(result.get("comparison"), dict) else []
    lines = [
        "# Weather multi-profile paper runner",
        "",
        f"Run: {result.get('run_id')}",
        f"Mode: {result.get('mode')}",
        "Safety: paper_only=true, live_order_allowed=false, no_real_orders=true",
        "",
        "| Profile | Strategy | Orders | Filled USDC | PnL | Statuses |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        statuses = ", ".join(f"{key}: {value}" for key, value in sorted((row.get("status_counts") or {}).items()))
        lines.append(f"| {row.get('profile_id')} | {row.get('strategy_id')} | {row.get('orders')} | {float(row.get('filled_usdc') or 0.0):.2f} | {float(row.get('pnl_usdc') or 0.0):.2f} | {statuses} |")
    lines.append("")
    return "\n".join(lines)


def _shortlist_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("shortlist") or payload.get("watchlist") or payload.get("opportunities") or []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _candidate_for_profile(row: dict[str, Any], *, profile: dict[str, Any], run_id: str, strategy_id: str, profile_id: str, mode: str, index: int) -> dict[str, Any] | None:
    if str(row.get("decision_status") or row.get("decision") or "").lower() not in _TRADEABLE_STATUSES:
        return None
    orderbook = row.get("orderbook") or row.get("execution_orderbook")
    if not isinstance(orderbook, dict):
        return None
    strict_limit = _number(row.get("strict_limit", row.get("limit_price", row.get("market_price"))))
    if strict_limit is None:
        return None
    risk_caps = profile.get("risk_caps") if isinstance(profile.get("risk_caps"), dict) else {}
    spend = _number(row.get("spend_usdc", row.get("requested_spend_usdc", row.get("capped_spend_usdc"))))
    max_order = _number(risk_caps.get("max_order_usdc"), 1.0) or 1.0
    spend_usdc = min(spend if spend is not None else max_order, max_order)
    side = str(row.get("side") or row.get("paper_side") or row.get("entry_side") or "YES").upper()
    return {
        **row,
        "order_id": str(row.get("order_id") or f"{run_id}:{index}:{row.get('market_id', '')}:{row.get('token_id', '')}:{side}"),
        "run_id": run_id,
        "strategy_id": strategy_id,
        "profile_id": profile_id,
        "strategy_profile_id": profile_id,
        "mode": mode,
        "paper_only": True,
        "live_order_allowed": False,
        "orderbook": orderbook,
        "side": side,
        "strict_limit": strict_limit,
        "spend_usdc": spend_usdc,
        "probability_edge": _number(row.get("probability_edge", row.get("edge"))),
    }


def _assert_order_guardrails(order: dict[str, Any], *, run_id: str, strategy_id: str, profile_id: str) -> None:
    expected = {"run_id": run_id, "strategy_id": strategy_id, "profile_id": profile_id, "paper_only": True, "live_order_allowed": False}
    mismatches = [key for key, value in expected.items() if order.get(key) != value]
    if mismatches:
        raise MultiProfilePaperRunnerError(f"paper order missing guardrails: {', '.join(mismatches)}")


def _profile_summary(ledger: dict[str, Any]) -> dict[str, Any]:
    summary = ledger.get("summary") if isinstance(ledger.get("summary"), dict) else {}
    return {
        "run_id": ledger.get("run_id"),
        "strategy_id": ledger.get("strategy_id"),
        "profile_id": ledger.get("profile_id"),
        "mode": ledger.get("mode"),
        "orders": summary.get("orders", 0),
        "filled_usdc": summary.get("filled_usdc", 0.0),
        "pnl_usdc": summary.get("pnl_usdc", 0.0),
        "status_counts": dict(summary.get("status_counts") or {}),
        "skipped_counts": dict(summary.get("skipped_counts") or {}),
        "paper_only": True,
        "live_order_allowed": False,
    }


def _comparison(profile_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "profiles": profile_summaries,
        "total_orders": sum(int(row.get("orders") or 0) for row in profile_summaries),
        "total_filled_usdc": round(sum(float(row.get("filled_usdc") or 0.0) for row in profile_summaries), 6),
        "total_pnl_usdc": round(sum(float(row.get("pnl_usdc") or 0.0) for row in profile_summaries), 6),
        "paper_only": True,
        "live_order_allowed": False,
    }


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _default_run_id() -> str:
    return "weather-multiprofile-paper-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)[:120]
