from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def enrich_shadow_dataset_features(
    dataset: dict[str, Any],
    *,
    orderbooks: dict[str, Any] | None = None,
    forecasts: dict[str, Any] | None = None,
    historical_forecasts: dict[str, Any] | None = None,
    resolutions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    orderbooks = orderbooks or {}
    forecasts = forecasts or {}
    historical_forecasts = historical_forecasts or {}
    resolutions = resolutions or {}
    rows = []
    for row in dataset.get("examples", []):
        if not isinstance(row, dict):
            continue
        enriched = dict(row)
        forecast_payload = _match_context_payload(forecasts, row)
        forecast_context_payload = _match_context_payload(historical_forecasts, row) or forecast_payload
        enriched["features"] = {
            "orderbook": _orderbook_features(_match_context_payload(orderbooks, row)),
            "forecast": _forecast_features(forecast_payload),
            "forecast_context": _forecast_context_features(forecast_context_payload),
            "resolution": _resolution_features(_match_context_payload(resolutions, row)),
        }
        rows.append(enriched)
    summary = {**dict(dataset.get("summary") or {}), "feature_rows": len(rows), "paper_only": True, "live_order_allowed": False}
    resolved_orders = sum(1 for row in rows if row.get("features", {}).get("resolution", {}).get("available"))
    if resolved_orders:
        summary["resolved_orders"] = resolved_orders
    return {
        **dataset,
        "paper_only": True,
        "live_order_allowed": False,
        "summary": summary,
        "examples": rows,
    }


def build_shadow_profile_paper_orders(
    enriched_dataset: dict[str, Any],
    *,
    run_id: str,
    max_order_usdc: float = 5.0,
    profile_configs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_configs = profile_configs or {}
    orders: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    profile_counts: dict[str, int] = {}
    for row in enriched_dataset.get("examples", []):
        if not isinstance(row, dict):
            continue
        profile_config = _profile_config_for_row(row, profile_configs)
        reason = _skip_reason(row, profile_config=profile_config)
        if reason:
            skipped.append({"market_id": row.get("market_id"), "wallet": row.get("wallet"), "reason": reason})
            continue
        orderbook = row["features"]["orderbook"]
        profile_id = str(profile_config.get("profile_id") or "shadow_profile_default") if profile_config else "shadow_profile_default"
        profile_role = str(profile_config.get("role") or "") if profile_config else ""
        order_notional = _profile_order_notional(max_order_usdc, profile_config)
        order = {
            "run_id": run_id,
            "source": "shadow_profile_replay",
            "wallet_signal": row.get("wallet"),
            "market_id": row.get("market_id"),
            "question": row.get("question"),
            "side": "BUY",
            "outcome": "Yes",
            "requested_notional_usdc": order_notional,
            "strict_limit_price": orderbook["best_ask"],
            "shadow_profile_label": row.get("label"),
            "profile_id": profile_id,
            "profile_role": profile_role,
            "weather_market_type": row.get("weather_market_type"),
            "features": row.get("features"),
            "metadata": {
                "resolution": row.get("features", {}).get("resolution", {}) if isinstance(row.get("features"), dict) else {},
                "forecast_context": row.get("features", {}).get("forecast_context", {}) if isinstance(row.get("features"), dict) else {},
                "profile_config": dict(profile_config) if profile_config else {},
            },
            "paper_only": True,
            "live_order_allowed": False,
        }
        if profile_config:
            profile_counts[profile_id] = profile_counts.get(profile_id, 0) + 1
        orders.append(order)
    summary = {"paper_orders": len(orders), "skipped": len(skipped), "paper_only": True, "live_order_allowed": False}
    if profile_counts:
        summary["profile_counts"] = profile_counts
    resolved_orders = sum(1 for order in orders if order.get("features", {}).get("resolution", {}).get("available"))
    if resolved_orders:
        summary["resolved_orders"] = resolved_orders
    return {
        "run_id": run_id,
        "source": "shadow_profile_paper_runner",
        "paper_only": True,
        "live_order_allowed": False,
        "summary": summary,
        "orders": orders,
        "skipped": skipped,
    }


def run_shadow_paper_runner_artifact(
    *,
    dataset_json: str | Path,
    orderbooks_json: str | Path | None,
    forecasts_json: str | Path | None,
    run_id: str,
    output_json: str | Path,
    resolutions_json: str | Path | None = None,
    historical_forecasts_json: str | Path | None = None,
    profile_configs_json: str | Path | None = None,
    max_order_usdc: float = 5.0,
) -> dict[str, Any]:
    dataset = json.loads(Path(dataset_json).read_text(encoding="utf-8"))
    orderbooks = _load_optional_object(orderbooks_json)
    forecasts = _load_optional_object(forecasts_json)
    historical_forecasts = _load_optional_object(historical_forecasts_json)
    resolutions = _load_optional_object(resolutions_json)
    profile_configs = _load_optional_object(profile_configs_json)
    enriched = enrich_shadow_dataset_features(dataset, orderbooks=orderbooks, forecasts=forecasts, historical_forecasts=historical_forecasts, resolutions=resolutions)
    result = build_shadow_profile_paper_orders(enriched, run_id=run_id, max_order_usdc=max_order_usdc, profile_configs=profile_configs)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.setdefault("artifacts", {})["output_json"] = str(output_path)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"summary": result["summary"], "artifacts": {"output_json": str(output_path)}}


def build_market_metadata_resolution_dataset(markets_payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
    markets = _extract_market_metadata_rows(markets_payload)
    resolutions: dict[str, dict[str, Any]] = {}
    unresolved = 0
    for market in markets:
        if not isinstance(market, dict):
            continue
        resolution = _resolution_from_market_metadata(market)
        if not resolution:
            unresolved += 1
            continue
        market_id = str(market.get("id") or market.get("market_id") or market.get("conditionId") or market.get("slug") or "").strip()
        if not market_id:
            unresolved += 1
            continue
        aliases = _market_resolution_aliases(market, market_id=market_id, resolution=resolution)
        resolution["primary_key"] = market_id
        resolution["matched_key"] = market_id
        resolution["aliases"] = aliases
        for alias in aliases:
            alias_resolution = dict(resolution)
            alias_resolution["matched_key"] = alias
            resolutions[alias] = alias_resolution
    summary = {
        "markets": len(markets),
        "resolved_markets": len({item.get("primary_key") for item in resolutions.values() if isinstance(item, dict) and item.get("primary_key")}),
        "unresolved_markets": unresolved,
        "paper_only": True,
        "live_order_allowed": False,
    }
    return {
        "source": "market_metadata_resolution_dataset",
        "paper_only": True,
        "live_order_allowed": False,
        "summary": summary,
        "resolutions": resolutions,
    }


def run_market_metadata_resolution_artifact(*, markets_json: str | Path, output_json: str | Path) -> dict[str, Any]:
    markets_payload = json.loads(Path(markets_json).read_text(encoding="utf-8"))
    result = build_market_metadata_resolution_dataset(markets_payload)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.setdefault("artifacts", {})["output_json"] = str(output_path)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"summary": result["summary"], "artifacts": result["artifacts"]}


def build_account_trade_resolution_dataset(trades_payload: dict[str, Any], *, resolutions: dict[str, Any] | None = None) -> dict[str, Any]:
    resolutions = resolutions or {}
    rows: list[dict[str, Any]] = []
    wins = 0
    losses = 0
    unresolved = 0
    for trade in trades_payload.get("trades", []):
        if not isinstance(trade, dict):
            continue
        row = dict(trade)
        resolution = _match_trade_resolution(resolutions, trade)
        row["resolution"] = _resolution_features(resolution)
        row["effective_position"] = _effective_trade_position(trade)
        result, pnl = _trade_result_and_pnl(trade, row["effective_position"], row["resolution"])
        row["trade_result"] = result
        row["estimated_pnl_usdc"] = pnl
        row["paper_only"] = True
        row["live_order_allowed"] = False
        if result == "win":
            wins += 1
        elif result == "loss":
            losses += 1
        else:
            unresolved += 1
        rows.append(row)
    summary = {
        "trades": len(rows),
        "resolved_trades": wins + losses,
        "wins": wins,
        "losses": losses,
        "unresolved_trades": unresolved,
        "paper_only": True,
        "live_order_allowed": False,
    }
    return {"source": "shadow_account_trade_resolution_dataset", "paper_only": True, "live_order_allowed": False, "summary": summary, "trades": rows}


def build_shadow_profile_evaluation(paper_orders: dict[str, Any], *, trade_resolution_dataset: dict[str, Any] | None = None) -> dict[str, Any]:
    buckets: dict[str, dict[str, Any]] = {}
    wallet_to_profile: dict[str, str] = {}
    for order in paper_orders.get("orders", []):
        if not isinstance(order, dict):
            continue
        profile_id = str(order.get("profile_id") or "shadow_profile_default")
        wallet = str(order.get("wallet_signal") or "")
        if wallet:
            wallet_to_profile[wallet.lower()] = profile_id
        bucket = buckets.setdefault(
            profile_id,
            {
                "profile_id": profile_id,
                "profile_role": str(order.get("profile_role") or ""),
                "orders": 0,
                "resolved_orders": 0,
                "wins": 0,
                "losses": 0,
                "unresolved_orders": 0,
                "requested_notional_usdc": 0.0,
                "estimated_pnl_usdc": 0.0,
                "skipped_counts": {},
            },
        )
        bucket["orders"] += 1
        notional = _to_float(order.get("requested_notional_usdc"))
        price = _to_float(order.get("strict_limit_price"))
        bucket["requested_notional_usdc"] += notional
        outcome = _resolved_outcome(order)
        if outcome == "Yes":
            bucket["resolved_orders"] += 1
            bucket["wins"] += 1
            bucket["estimated_pnl_usdc"] += _profit_for_yes_win(notional, price)
        elif outcome == "No":
            bucket["resolved_orders"] += 1
            bucket["losses"] += 1
            bucket["estimated_pnl_usdc"] -= notional
        else:
            bucket["unresolved_orders"] += 1
    for skipped in paper_orders.get("skipped", []):
        if not isinstance(skipped, dict):
            continue
        wallet = str(skipped.get("wallet") or "").lower()
        profile_id = wallet_to_profile.get(wallet, "shadow_profile_default")
        reason = str(skipped.get("reason") or "unknown")
        bucket = buckets.setdefault(
            profile_id,
            {
                "profile_id": profile_id,
                "profile_role": "",
                "orders": 0,
                "resolved_orders": 0,
                "wins": 0,
                "losses": 0,
                "unresolved_orders": 0,
                "requested_notional_usdc": 0.0,
                "estimated_pnl_usdc": 0.0,
                "skipped_counts": {},
            },
        )
        bucket["skipped_counts"][reason] = bucket["skipped_counts"].get(reason, 0) + 1
    trade_summary = _merge_trade_resolution_dataset(buckets, trade_resolution_dataset, wallet_to_profile=wallet_to_profile) if trade_resolution_dataset else {}
    profiles = [_finalize_profile_evaluation(bucket) for bucket in buckets.values() if bucket["orders"] or bucket["skipped_counts"] or bucket.get("historical_trades")]
    profiles.sort(key=lambda item: (item["estimated_pnl_usdc"] + item.get("historical_estimated_pnl_usdc", 0.0), item.get("resolved_trades", 0), item["resolved_orders"], item["orders"]), reverse=True)
    summary = {
        "profiles": len(profiles),
        "orders": sum(profile["orders"] for profile in profiles),
        "resolved_orders": sum(profile["resolved_orders"] for profile in profiles),
        "wins": sum(profile["wins"] for profile in profiles),
        "losses": sum(profile["losses"] for profile in profiles),
        "unresolved_orders": sum(profile["unresolved_orders"] for profile in profiles),
    }
    summary.update(trade_summary)
    return {"paper_only": True, "live_order_allowed": False, "summary": summary, "profiles": profiles}


def run_account_trade_resolution_artifact(
    *,
    trades_json: str | Path,
    resolutions_json: str | Path,
    output_json: str | Path,
) -> dict[str, Any]:
    trades_payload = json.loads(Path(trades_json).read_text(encoding="utf-8"))
    resolutions = _load_optional_object(resolutions_json)
    result = build_account_trade_resolution_dataset(trades_payload, resolutions=resolutions)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.setdefault("artifacts", {})["output_json"] = str(output_path)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"summary": result["summary"], "artifacts": result["artifacts"]}


def run_shadow_profile_evaluator_artifact(
    *,
    paper_orders_json: str | Path,
    output_json: str | Path,
    output_md: str | Path | None = None,
    trade_resolution_json: str | Path | None = None,
) -> dict[str, Any]:
    payload = json.loads(Path(paper_orders_json).read_text(encoding="utf-8"))
    trade_resolution_dataset = _load_optional_object(trade_resolution_json)
    result = build_shadow_profile_evaluation(payload, trade_resolution_dataset=trade_resolution_dataset)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.setdefault("artifacts", {})["output_json"] = str(output_path)
    if output_md:
        md_path = Path(output_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_shadow_profile_evaluation_markdown(result), encoding="utf-8")
        result["artifacts"]["output_md"] = str(md_path)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"summary": result["summary"], "artifacts": result["artifacts"]}


def _extract_market_metadata_rows(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("markets", "events", "data", "results"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [item for item in rows if isinstance(item, dict)]
    return [payload]


def _resolution_from_market_metadata(market: dict[str, Any]) -> dict[str, Any] | None:
    explicit_outcome = _explicit_resolved_outcome(market)
    outcome_prices = [_to_float(value) for value in _jsonish_list(market.get("outcomePrices") or market.get("outcome_prices"))]
    outcomes = [str(value).strip().title() for value in _jsonish_list(market.get("outcomes"))]
    is_closed = _truthy(market.get("closed")) or _truthy(market.get("archived")) or not _truthy(market.get("active"), default=True)
    question = str(market.get("question") or market.get("title") or "")
    slug = str(market.get("slug") or "")
    base = {
        "question": question,
        "title": question,
        "slug": slug,
        "observed_value": 0.0,
    }
    source_hint = str(market.get("source") or "")
    status_hint = str(market.get("status") or "")
    has_proxy_hint = "proxy" in source_hint.lower() or "proxy" in status_hint.lower()
    if explicit_outcome in {"Yes", "No"} and (is_closed or has_proxy_hint):
        return {
            **base,
            "resolved_outcome": explicit_outcome,
            "status": "resolved" if is_closed else status_hint or "market_metadata_proxy_unfinalized",
            "source": "gamma_closed_market_metadata" if is_closed else source_hint or "gamma_market_metadata_proxy",
            "confidence": _to_float(market.get("confidence")) or 1.0,
            "outcome_prices": outcome_prices,
            "outcomes": outcomes,
            "market_closed": is_closed,
        }
    if not is_closed or not outcome_prices or not outcomes or len(outcome_prices) != len(outcomes):
        return None
    best_idx = max(range(len(outcome_prices)), key=lambda idx: outcome_prices[idx])
    confidence = outcome_prices[best_idx]
    inferred = outcomes[best_idx] if best_idx < len(outcomes) else ""
    if inferred not in {"Yes", "No"} or confidence < 0.99:
        return None
    return {
        **base,
        "resolved_outcome": inferred,
        "status": "closed_price_resolved_proxy",
        "source": "gamma_closed_outcomePrices_proxy",
        "confidence": round(confidence, 6),
        "outcome_prices": outcome_prices,
        "outcomes": outcomes,
        "market_closed": True,
    }


def _market_resolution_aliases(market: dict[str, Any], *, market_id: str, resolution: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    for value in (
        market_id,
        market.get("market_id"),
        market.get("conditionId"),
        market.get("condition_id"),
        market.get("clobTokenId"),
        market.get("token_id"),
        market.get("slug"),
        resolution.get("slug"),
        market.get("question"),
        market.get("title"),
        resolution.get("question"),
        resolution.get("title"),
    ):
        raw = str(value or "").strip()
        if raw and raw not in aliases:
            aliases.append(raw)
        normalized = _normalize_resolution_lookup_key(raw)
        if normalized and normalized not in aliases:
            aliases.append(normalized)
    return aliases


def _explicit_resolved_outcome(market: dict[str, Any]) -> str:
    for key in ("resolvedOutcome", "resolved_outcome", "resolution", "winner", "winningOutcome", "winning_outcome"):
        value = str(market.get(key) or "").strip().title()
        if value in {"Yes", "No"}:
            return value
    return ""


def _jsonish_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return parsed
    return []


def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n", ""}:
            return False
    return bool(value)


def _resolved_outcome(order: dict[str, Any]) -> str:
    features = order.get("features") if isinstance(order.get("features"), dict) else {}
    resolution = features.get("resolution") if isinstance(features.get("resolution"), dict) else {}
    if not resolution.get("available"):
        return ""
    outcome = str(resolution.get("resolved_outcome") or resolution.get("outcome") or "")
    return outcome.strip().title()


def _profit_for_yes_win(notional: float, price: float) -> float:
    if notional <= 0 or price <= 0:
        return 0.0
    shares = notional / price
    return shares - notional


def _merge_trade_resolution_dataset(
    buckets: dict[str, dict[str, Any]],
    trade_resolution_dataset: dict[str, Any],
    *,
    wallet_to_profile: dict[str, str] | None = None,
) -> dict[str, int]:
    wallet_to_profile = wallet_to_profile or {}
    summary = {"historical_trades": 0, "resolved_trades": 0, "trade_wins": 0, "trade_losses": 0, "unresolved_trades": 0}
    for trade in trade_resolution_dataset.get("trades", []):
        if not isinstance(trade, dict):
            continue
        wallet = str(trade.get("wallet") or "")
        profile_id = str(trade.get("profile_id") or wallet_to_profile.get(wallet.lower()) or wallet or "shadow_profile_default")
        bucket = buckets.setdefault(profile_id, _empty_profile_bucket(profile_id, str(trade.get("profile_role") or "")))
        bucket["historical_trades"] = bucket.get("historical_trades", 0) + 1
        bucket["historical_notional_usdc"] = bucket.get("historical_notional_usdc", 0.0) + _to_float(trade.get("notional_usd") or trade.get("account_trade_notional_usd"))
        bucket["historical_estimated_pnl_usdc"] = bucket.get("historical_estimated_pnl_usdc", 0.0) + _to_float(trade.get("estimated_pnl_usdc"))
        city = str(trade.get("city") or "")
        if city:
            top_cities = bucket.setdefault("top_cities", {})
            top_cities[city] = top_cities.get(city, 0) + 1
        market_type = str(trade.get("weather_market_type") or "")
        if market_type:
            type_counts = bucket.setdefault("weather_market_type_counts", {})
            type_counts[market_type] = type_counts.get(market_type, 0) + 1
        result = str(trade.get("trade_result") or "")
        summary["historical_trades"] += 1
        if result == "win":
            bucket["resolved_trades"] = bucket.get("resolved_trades", 0) + 1
            bucket["trade_wins"] = bucket.get("trade_wins", 0) + 1
            summary["resolved_trades"] += 1
            summary["trade_wins"] += 1
        elif result == "loss":
            bucket["resolved_trades"] = bucket.get("resolved_trades", 0) + 1
            bucket["trade_losses"] = bucket.get("trade_losses", 0) + 1
            summary["resolved_trades"] += 1
            summary["trade_losses"] += 1
        else:
            bucket["unresolved_trades"] = bucket.get("unresolved_trades", 0) + 1
            summary["unresolved_trades"] += 1
    return summary


def _empty_profile_bucket(profile_id: str, profile_role: str = "") -> dict[str, Any]:
    return {
        "profile_id": profile_id,
        "profile_role": profile_role,
        "orders": 0,
        "resolved_orders": 0,
        "wins": 0,
        "losses": 0,
        "unresolved_orders": 0,
        "requested_notional_usdc": 0.0,
        "estimated_pnl_usdc": 0.0,
        "skipped_counts": {},
    }


def _finalize_profile_evaluation(bucket: dict[str, Any]) -> dict[str, Any]:
    resolved = int(bucket["resolved_orders"])
    wins = int(bucket["wins"])
    notional = round(float(bucket["requested_notional_usdc"]), 6)
    pnl = round(float(bucket["estimated_pnl_usdc"]), 6)
    result = {
        "profile_id": bucket["profile_id"],
        "profile_role": bucket["profile_role"],
        "orders": int(bucket["orders"]),
        "resolved_orders": resolved,
        "wins": wins,
        "losses": int(bucket["losses"]),
        "unresolved_orders": int(bucket["unresolved_orders"]),
        "winrate": round(wins / resolved, 6) if resolved else 0.0,
        "requested_notional_usdc": notional,
        "estimated_pnl_usdc": pnl,
        "roi": round(pnl / notional, 6) if notional else 0.0,
        "skipped_counts": dict(sorted(bucket["skipped_counts"].items())),
    }
    if bucket.get("historical_trades"):
        resolved_trades = int(bucket.get("resolved_trades", 0))
        trade_wins = int(bucket.get("trade_wins", 0))
        historical_notional = round(float(bucket.get("historical_notional_usdc", 0.0)), 6)
        historical_pnl = round(float(bucket.get("historical_estimated_pnl_usdc", 0.0)), 6)
        result.update(
            {
                "historical_trades": int(bucket.get("historical_trades", 0)),
                "resolved_trades": resolved_trades,
                "trade_wins": trade_wins,
                "trade_losses": int(bucket.get("trade_losses", 0)),
                "unresolved_trades": int(bucket.get("unresolved_trades", 0)),
                "trade_winrate": round(trade_wins / resolved_trades, 6) if resolved_trades else 0.0,
                "historical_notional_usdc": historical_notional,
                "historical_estimated_pnl_usdc": historical_pnl,
                "historical_roi": round(historical_pnl / historical_notional, 6) if historical_notional else 0.0,
                "top_cities": dict(sorted(bucket.get("top_cities", {}).items())),
                "weather_market_type_counts": dict(sorted(bucket.get("weather_market_type_counts", {}).items())),
            }
        )
    result["recommendation"] = _profile_recommendation(result)
    return result


def _profile_recommendation(profile: dict[str, Any]) -> str:
    if profile["orders"] and not profile["resolved_orders"]:
        return "needs_resolution_data"
    if profile["resolved_orders"] < 5:
        return "observe_more"
    if profile["roi"] > 0.05 and profile["winrate"] >= 0.55:
        return "promote_to_paper_profile"
    if profile["roi"] < -0.05:
        return "reduce_or_disable"
    return "observe_more"


def _shadow_profile_evaluation_markdown(result: dict[str, Any]) -> str:
    lines = ["# Shadow profile evaluation", "", "paper_only: true", "live_order_allowed: false", "", "| profile | orders | resolved | winrate | pnl | recommendation |", "|---|---:|---:|---:|---:|---|"]
    for profile in result.get("profiles", []):
        lines.append(
            f"| {profile['profile_id']} | {profile['orders']} | {profile['resolved_orders']} | {profile['winrate']:.2f} | {profile['estimated_pnl_usdc']:.4f} | {profile['recommendation']} |"
        )
    return "\n".join(lines) + "\n"


def _orderbook_features(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"best_bid": 0.0, "best_ask": 0.0, "spread_bps": 0.0, "depth_usd": 0.0, "available": False}
    best_bid = _to_float(payload.get("best_bid"))
    best_ask = _to_float(payload.get("best_ask"))
    mid = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else 0.0
    spread_bps = round(((best_ask - best_bid) / mid) * 10000, 5) if mid else 0.0
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread_bps": spread_bps,
        "depth_usd": _to_float(payload.get("depth_usd")),
        "available": best_bid > 0 and best_ask > 0,
    }


def _forecast_features(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"forecast_high_c": 0.0, "source": "", "freshness_minutes": 0.0, "available": False}
    return {
        "forecast_high_c": _to_float(payload.get("forecast_high_c")),
        "source": str(payload.get("source") or ""),
        "freshness_minutes": _to_float(payload.get("freshness_minutes")),
        "available": True,
    }


def _forecast_context_features(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"available": False, "source": "", "freshness_minutes": 0.0, "model_probability_at_trade": 0.0}
    return {
        "available": True,
        "source": str(payload.get("source") or ""),
        "freshness_minutes": _to_float(payload.get("freshness_minutes")),
        "model_probability_at_trade": _to_float(payload.get("model_probability_at_trade", payload.get("model_probability"))),
    }


def _resolution_features(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"available": False, "resolved_outcome": "", "status": "", "observed_value": 0.0, "source": "", "confidence": 0.0}
    result = {
        "available": True,
        "resolved_outcome": str(payload.get("resolved_outcome") or payload.get("outcome") or ""),
        "status": str(payload.get("status") or ""),
        "observed_value": _to_float(payload.get("observed_value")),
        "source": str(payload.get("source") or ""),
        "confidence": _to_float(payload.get("confidence")),
    }
    if payload.get("matched_key"):
        result["matched_key"] = str(payload.get("matched_key") or "")
    if payload.get("primary_key"):
        result["primary_key"] = str(payload.get("primary_key") or "")
    return result


def _match_context_payload(mapping: dict[str, Any], row: dict[str, Any]) -> Any:
    for key_name in ("market_id", "surface_key"):
        key = str(row.get(key_name) or "")
        if key and key in mapping:
            return mapping[key]
    return None


def _match_trade_resolution(mapping: dict[str, Any], trade: dict[str, Any]) -> Any:
    resolution_mapping = mapping.get("resolutions") if isinstance(mapping.get("resolutions"), dict) else mapping
    direct_keys: list[str] = []
    for key_name in ("market_id", "conditionId", "condition_id", "token_id", "clobTokenId", "slug", "surface_key", "title", "question"):
        raw = str(trade.get(key_name) or "").strip()
        if not raw:
            continue
        direct_keys.append(raw)
        normalized = _normalize_resolution_lookup_key(raw)
        if normalized:
            direct_keys.append(normalized)
    for key in direct_keys:
        if key in resolution_mapping:
            return resolution_mapping[key]
    trade_question_key = _normalize_resolution_lookup_key(trade.get("question") or trade.get("title"))
    trade_slug_key = _normalize_resolution_lookup_key(trade.get("slug"))
    trade_keys = {key for key in [*direct_keys, trade_question_key, trade_slug_key] if key}
    for payload in resolution_mapping.values():
        if not isinstance(payload, dict):
            continue
        aliases = [_normalize_resolution_lookup_key(alias) for alias in payload.get("aliases", []) if alias]
        if trade_keys.intersection(alias for alias in aliases if alias):
            return payload
        for value_name in ("question", "title", "slug", "primary_key", "matched_key"):
            payload_key = _normalize_resolution_lookup_key(payload.get(value_name))
            if payload_key and payload_key in trade_keys:
                return {**payload, "matched_key": value_name if value_name not in {"question", "title", "slug"} else str(payload.get(value_name) or "")}
    return None


def _normalize_resolution_lookup_key(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _effective_trade_position(trade: dict[str, Any]) -> str:
    outcome = str(trade.get("outcome") or "").strip().title()
    side = str(trade.get("side") or "").strip().upper()
    if side == "SELL":
        if outcome == "Yes":
            return "No"
        if outcome == "No":
            return "Yes"
    return outcome


def _trade_result_and_pnl(trade: dict[str, Any], effective_position: str, resolution: dict[str, Any]) -> tuple[str, float]:
    if not resolution.get("available"):
        return "unresolved", 0.0
    resolved = str(resolution.get("resolved_outcome") or "").strip().title()
    if resolved not in {"Yes", "No"} or effective_position not in {"Yes", "No"}:
        return "unresolved", 0.0
    notional = _to_float(trade.get("notional_usd") or trade.get("account_trade_notional_usd"))
    price = _to_float(trade.get("price") or trade.get("account_trade_price"))
    side = str(trade.get("side") or "").strip().upper()
    if resolved == effective_position:
        if side == "SELL":
            return "win", round(notional, 6)
        return "win", round(_profit_for_yes_win(notional, price), 6)
    if side == "SELL":
        size = _to_float(trade.get("size") or trade.get("account_trade_size"))
        return "loss", round(notional - size, 6)
    return "loss", -notional


def _profile_config_for_row(row: dict[str, Any], profile_configs: dict[str, Any]) -> dict[str, Any]:
    wallet = str(row.get("wallet") or "").lower()
    handle = str(row.get("handle") or "").lower()
    for key in (wallet, handle):
        config = profile_configs.get(key)
        if isinstance(config, dict):
            return dict(config)
    return {}


def _profile_order_notional(max_order_usdc: float, profile_config: dict[str, Any]) -> float:
    configured = _to_float(profile_config.get("max_order_usdc")) if profile_config else 0.0
    if configured > 0:
        return min(float(max_order_usdc), configured)
    return float(max_order_usdc)


def _skip_reason(row: dict[str, Any], *, profile_config: dict[str, Any] | None = None) -> str | None:
    if row.get("label") != "trade":
        return "account_no_trade_label"
    features = row.get("features") if isinstance(row.get("features"), dict) else {}
    orderbook = features.get("orderbook") if isinstance(features.get("orderbook"), dict) else {}
    forecast = features.get("forecast") if isinstance(features.get("forecast"), dict) else {}
    forecast_context = features.get("forecast_context") if isinstance(features.get("forecast_context"), dict) else {}
    if not orderbook.get("available"):
        return "missing_orderbook_features"
    if not forecast.get("available"):
        return "missing_forecast_features"
    replay_probability = _to_float(forecast_context.get("model_probability_at_trade")) if forecast_context.get("available") else 0.0
    model_probability = replay_probability or _to_float(row.get("model_probability"))
    model_edge = model_probability - _to_float(row.get("yes_price"))
    if model_edge <= 0:
        return "no_independent_model_edge"
    min_edge = _to_float((profile_config or {}).get("min_edge"))
    if min_edge > 0 and model_edge < min_edge:
        return "profile_min_edge_not_met"
    return None


def _load_optional_object(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("profiles"), dict):
        return payload["profiles"]
    return payload if isinstance(payload, dict) else {}


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
