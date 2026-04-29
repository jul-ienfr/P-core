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
    promoted_profiles: dict[str, Any] | None = None,
    historical_profile_rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_configs = _merge_promoted_profile_configs(profile_configs or {}, promoted_profiles or {})
    promoted_profile_ids = sorted(
        {
            str(config.get("profile_id") or "")
            for config in profile_configs.values()
            if isinstance(config, dict) and config.get("source_recommendation") == "promote_to_paper_profile" and config.get("profile_id")
        }
    )
    historical_rule_rows = [rule for rule in (historical_profile_rules or {}).get("rules", []) if isinstance(rule, dict)]
    historical_allow_orders = 0
    historical_avoid_skips = 0
    orders: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    profile_counts: dict[str, int] = {}
    for row in enriched_dataset.get("examples", []):
        if not isinstance(row, dict):
            continue
        profile_config = _profile_config_for_row(row, profile_configs) or _promoted_opportunity_profile_config(row)
        historical_rule = _historical_profile_rule_for_row(row, historical_rule_rows)
        if historical_rule and historical_rule.get("action") == "avoid_or_invert_filter":
            historical_avoid_skips += 1
            skipped.append({"market_id": row.get("market_id"), "wallet": row.get("wallet"), "reason": "historical_profile_avoid_or_invert_filter"})
            continue
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
            "handle_signal": row.get("handle"),
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
                "historical_profile_rule": _compact_historical_profile_rule(historical_rule) if historical_rule else {},
            },
            "paper_only": True,
            "live_order_allowed": False,
        }
        if profile_config:
            profile_counts[profile_id] = profile_counts.get(profile_id, 0) + 1
        if historical_rule and historical_rule.get("action") == "paper_candidate_allow":
            historical_allow_orders += 1
        orders.append(order)
    summary = {"paper_orders": len(orders), "skipped": len(skipped), "paper_only": True, "live_order_allowed": False}
    if historical_rule_rows:
        summary["historical_profile_rules"] = len(historical_rule_rows)
        summary["historical_profile_allow_orders"] = historical_allow_orders
        summary["historical_profile_avoid_skips"] = historical_avoid_skips
    if promoted_profile_ids:
        summary["promoted_profile_configs"] = len(promoted_profile_ids)
        summary["promoted_profile_ids"] = promoted_profile_ids
    if profile_counts:
        summary["profile_counts"] = profile_counts
        promoted_order_count = sum(profile_counts.get(profile_id, 0) for profile_id in promoted_profile_ids)
        if promoted_order_count:
            summary["promoted_profile_orders"] = promoted_order_count
        promoted_opportunity_order_count = sum(
            1
            for order in orders
            if order.get("metadata", {}).get("profile_config", {}).get("source_recommendation") == "promoted_profile_opportunity_watch"
        )
        if promoted_opportunity_order_count:
            summary["promoted_opportunity_orders"] = promoted_opportunity_order_count
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


def build_shadow_profile_exposure_preview(paper_orders: dict[str, Any]) -> dict[str, Any]:
    preview_orders: list[dict[str, Any]] = []
    markets: dict[str, dict[str, Any]] = {}
    for order in paper_orders.get("orders", []):
        if not isinstance(order, dict):
            continue
        notional = _to_float(order.get("requested_notional_usdc"))
        price = _to_float(order.get("strict_limit_price"))
        shares = round(notional / price, 6) if price > 0 else 0.0
        max_profit = round(shares - notional, 6)
        risk_bucket = str((order.get("stress_overlay") or {}).get("risk_bucket") or "") if isinstance(order.get("stress_overlay"), dict) else ""
        preview_order = {
            **order,
            "shares_if_filled": shares,
            "max_loss_usdc": notional,
            "max_profit_if_true_usdc": max_profit,
            "risk_bucket": risk_bucket,
            "paper_only": True,
            "live_order_allowed": False,
        }
        preview_orders.append(preview_order)
        market_id = str(order.get("market_id") or "")
        bucket = markets.setdefault(
            market_id,
            {
                "market_id": market_id,
                "orders": 0,
                "total_notional_usdc": 0.0,
                "max_loss_usdc": 0.0,
                "shares_if_filled": 0.0,
                "max_profit_if_true_usdc": 0.0,
                "risk_buckets": [],
                "questions": [],
            },
        )
        bucket["orders"] += 1
        bucket["total_notional_usdc"] = round(bucket["total_notional_usdc"] + notional, 6)
        bucket["max_loss_usdc"] = round(bucket["max_loss_usdc"] + notional, 6)
        bucket["shares_if_filled"] = round(bucket["shares_if_filled"] + shares, 6)
        bucket["max_profit_if_true_usdc"] = round(bucket["max_profit_if_true_usdc"] + max_profit, 6)
        if risk_bucket and risk_bucket not in bucket["risk_buckets"]:
            bucket["risk_buckets"].append(risk_bucket)
        question = str(order.get("question") or "")
        if question and question not in bucket["questions"]:
            bucket["questions"].append(question)
    summary = {
        "orders": len(preview_orders),
        "markets": len(markets),
        "total_notional_usdc": round(sum(order["max_loss_usdc"] for order in preview_orders), 6),
        "max_loss_usdc": round(sum(order["max_loss_usdc"] for order in preview_orders), 6),
        "shares_if_filled": round(sum(order["shares_if_filled"] for order in preview_orders), 6),
        "max_profit_if_true_usdc": round(sum(order["max_profit_if_true_usdc"] for order in preview_orders), 6),
        "paper_only": True,
        "live_order_allowed": False,
    }
    return {
        "source": "shadow_profile_paper_exposure_preview",
        "paper_only": True,
        "live_order_allowed": False,
        "summary": summary,
        "markets": markets,
        "orders": preview_orders,
    }



def apply_stress_overlay_to_paper_orders(paper_orders: dict[str, Any], stress_overlay: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        str(row.get("market_id")): row
        for row in stress_overlay.get("rows", [])
        if isinstance(row, dict) and row.get("action") == "PAPER_MICRO_STRICT_LIMIT" and row.get("market_id")
    }
    filtered: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for order in paper_orders.get("orders", []):
        if not isinstance(order, dict):
            continue
        market_id = str(order.get("market_id") or "")
        stress_row = allowed.get(market_id)
        if not stress_row:
            rejected.append(
                {
                    "market_id": order.get("market_id"),
                    "profile_id": order.get("profile_id"),
                    "reason": "not_in_stressed_micro_candidates",
                    "question": order.get("question"),
                }
            )
            continue
        capped_order = dict(order)
        capped_order["strict_limit_price"] = float(stress_row.get("strict_limit_max"))
        capped_order["requested_notional_usdc"] = min(
            float(order.get("requested_notional_usdc") or 0.0),
            float(stress_row.get("paper_notional_usdc") or 0.0),
        )
        capped_order["stress_overlay"] = {
            key: stress_row[key]
            for key in (
                "risk_bucket",
                "good_scenarios",
                "total_scenarios",
                "worst_edge",
                "median_edge",
                "base_edge",
                "station_max_c",
                "threshold_c",
                "direction",
            )
            if key in stress_row
        }
        capped_order["paper_only"] = True
        capped_order["live_order_allowed"] = False
        filtered.append(capped_order)
    market_counts: dict[str, int] = {}
    notional_by_market: dict[str, float] = {}
    for order in filtered:
        market_id = str(order.get("market_id") or "")
        market_counts[market_id] = market_counts.get(market_id, 0) + 1
        notional_by_market[market_id] = round(notional_by_market.get(market_id, 0.0) + float(order.get("requested_notional_usdc") or 0.0), 6)
    summary = {
        "source_orders": len([order for order in paper_orders.get("orders", []) if isinstance(order, dict)]),
        "stress_allowed_markets": len(allowed),
        "paper_orders": len(filtered),
        "rejected_orders": len(rejected),
        "paper_only": True,
        "live_order_allowed": False,
        "market_counts": market_counts,
        "notional_by_market": notional_by_market,
        "max_total_notional_usdc": round(sum(float(order.get("requested_notional_usdc") or 0.0) for order in filtered), 6),
    }
    return {
        "source": "shadow_profile_stress_overlay_paper_orders",
        "paper_only": True,
        "live_order_allowed": False,
        "summary": summary,
        "orders": filtered,
        "rejected": rejected,
    }


def run_shadow_profile_exposure_preview_artifact(
    *,
    paper_orders_json: str | Path,
    output_json: str | Path,
    output_md: str | Path | None = None,
) -> dict[str, Any]:
    payload = json.loads(Path(paper_orders_json).read_text(encoding="utf-8"))
    result = build_shadow_profile_exposure_preview(payload)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.setdefault("artifacts", {})["output_json"] = str(output_path)
    if output_md:
        md_path = Path(output_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_shadow_profile_exposure_preview_markdown(result), encoding="utf-8")
        result["artifacts"]["output_md"] = str(md_path)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"summary": result["summary"], "artifacts": result["artifacts"]}



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
    promoted_profiles_json: str | Path | None = None,
    stress_overlay_json: str | Path | None = None,
    max_order_usdc: float = 5.0,
) -> dict[str, Any]:
    dataset = json.loads(Path(dataset_json).read_text(encoding="utf-8"))
    orderbooks = _load_optional_object(orderbooks_json)
    forecasts = _load_optional_object(forecasts_json)
    historical_forecasts = _load_optional_object(historical_forecasts_json)
    resolutions = _load_optional_object(resolutions_json)
    profile_configs = _load_optional_object(profile_configs_json)
    promoted_profiles = _load_optional_object(promoted_profiles_json)
    stress_overlay = _load_optional_object(stress_overlay_json)
    enriched = enrich_shadow_dataset_features(dataset, orderbooks=orderbooks, forecasts=forecasts, historical_forecasts=historical_forecasts, resolutions=resolutions)
    result = build_shadow_profile_paper_orders(enriched, run_id=run_id, max_order_usdc=max_order_usdc, profile_configs=profile_configs, promoted_profiles=promoted_profiles)
    if stress_overlay:
        result = apply_stress_overlay_to_paper_orders(result, stress_overlay)
        result["run_id"] = run_id
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
        handle = str(order.get("handle_signal") or order.get("handle") or "")
        if wallet:
            wallet_to_profile[wallet.lower()] = profile_id
        if handle:
            wallet_to_profile[handle.lower()] = profile_id
        bucket = buckets.setdefault(profile_id, _empty_profile_bucket(profile_id, str(order.get("profile_role") or "")))
        metadata = order.get("metadata") if isinstance(order.get("metadata"), dict) else {}
        profile_config = metadata.get("profile_config") if isinstance(metadata.get("profile_config"), dict) else {}
        source_recommendation = str(profile_config.get("source_recommendation") or "")
        if source_recommendation:
            bucket["source_recommendation"] = source_recommendation
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
        bucket = buckets.setdefault(profile_id, _empty_profile_bucket(profile_id))
        if skipped.get("profile_role") and not bucket.get("profile_role"):
            bucket["profile_role"] = str(skipped.get("profile_role") or "")
        bucket["skipped_counts"][reason] = bucket["skipped_counts"].get(reason, 0) + 1
    trade_summary = _merge_trade_resolution_dataset(buckets, trade_resolution_dataset, wallet_to_profile=wallet_to_profile) if trade_resolution_dataset else {}
    profiles = [_finalize_profile_evaluation(bucket) for bucket in buckets.values() if bucket["orders"] or bucket["skipped_counts"] or bucket.get("historical_trades")]
    profiles.sort(key=lambda item: (item["estimated_pnl_usdc"] + item.get("historical_estimated_pnl_usdc", 0.0), item.get("resolved_trades", 0), item["resolved_orders"], item["orders"]), reverse=True)
    promoted_opportunity_profiles = [
        profile
        for profile in profiles
        if profile.get("profile_role") == "promoted_opportunity_watch" or profile.get("source_recommendation") == "promoted_profile_opportunity_watch"
    ]
    summary = {
        "profiles": len(profiles),
        "orders": sum(profile["orders"] for profile in profiles),
        "resolved_orders": sum(profile["resolved_orders"] for profile in profiles),
        "wins": sum(profile["wins"] for profile in profiles),
        "losses": sum(profile["losses"] for profile in profiles),
        "unresolved_orders": sum(profile["unresolved_orders"] for profile in profiles),
    }
    if promoted_opportunity_profiles:
        summary.update(
            {
                "promoted_opportunity_profiles": len(promoted_opportunity_profiles),
                "promoted_opportunity_orders": sum(profile["orders"] for profile in promoted_opportunity_profiles),
                "promoted_opportunity_skipped": sum(sum(profile.get("skipped_counts", {}).values()) for profile in promoted_opportunity_profiles),
            }
        )
    summary.update(trade_summary)
    return {"paper_only": True, "live_order_allowed": False, "summary": summary, "profiles": profiles}




def build_historical_profile_rule_candidates(trade_resolution_dataset: dict[str, Any]) -> dict[str, Any]:
    """Aggregate resolved account trades into paper-only profile gating rules."""
    rows = [row for row in trade_resolution_dataset.get("trades", []) if isinstance(row, dict)]
    resolved_rows = [row for row in rows if _trade_row_is_resolved(row)]
    buckets: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for row in resolved_rows:
        handle = str(row.get("handle") or row.get("wallet") or "unknown")
        city = str(row.get("city") or "").strip()
        market_type = str(row.get("weather_market_type") or "unknown")
        position = str(row.get("effective_position") or _effective_trade_position(row) or "").strip().title()
        slice_specs = [("handle_weather_type_position", "", 8)]
        if city:
            slice_specs.append(("handle_city_weather_type_position", city, 5))
        for slice_type, slice_city, min_trades in slice_specs:
            key = (handle, slice_type, slice_city, market_type, position)
            bucket = buckets.setdefault(
                key,
                {
                    "handle": handle,
                    "wallets": set(),
                    "slice_type": slice_type,
                    "city": slice_city,
                    "weather_market_type": market_type,
                    "effective_position": position,
                    "min_trades": min_trades,
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "estimated_pnl_usdc": 0.0,
                    "notional_usd": 0.0,
                    "examples": [],
                },
            )
            _accumulate_rule_bucket(bucket, row)
    rules = [_finalize_rule_bucket(bucket) for bucket in buckets.values()]
    rules = [rule for rule in rules if _rule_action(rule)]
    for rule in rules:
        rule["action"] = _rule_action(rule)
        rule["confidence"] = _rule_confidence(rule)
        rule["paper_only"] = True
        rule["live_order_allowed"] = False
    rules.sort(key=lambda rule: (rule["action"] != "paper_candidate_allow", rule["handle"], rule["slice_type"], rule.get("city") or "", -abs(rule["estimated_pnl_usdc"])))
    profile_rule_configs = _profile_rule_configs_from_rules(rules)
    summary = {
        "input_trades": len(rows),
        "resolved_trades": len(resolved_rows),
        "rules": len(rules),
        "allow_rules": sum(1 for rule in rules if rule["action"] == "paper_candidate_allow"),
        "avoid_rules": sum(1 for rule in rules if rule["action"] == "avoid_or_invert_filter"),
        "profile_count": len(profile_rule_configs),
        "paper_only": True,
        "live_order_allowed": False,
    }
    return {
        "source": "historical_profile_rule_candidates",
        "paper_only": True,
        "live_order_allowed": False,
        "summary": summary,
        "rules": rules,
        "profile_rule_configs": profile_rule_configs,
    }


def run_historical_profile_rule_candidates_artifact(
    *,
    trade_resolution_json: str | Path,
    output_json: str | Path,
    output_md: str | Path | None = None,
) -> dict[str, Any]:
    payload = json.loads(Path(trade_resolution_json).read_text(encoding="utf-8"))
    result = build_historical_profile_rule_candidates(payload)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.setdefault("artifacts", {})["output_json"] = str(output_path)
    if output_md:
        md_path = Path(output_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_historical_profile_rule_candidates_markdown(result), encoding="utf-8")
        result["artifacts"]["output_md"] = str(md_path)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"summary": result["summary"], "artifacts": result["artifacts"]}

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
    handoff_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = json.loads(Path(paper_orders_json).read_text(encoding="utf-8"))
    trade_resolution_dataset = _load_optional_object(trade_resolution_json)
    result = build_shadow_profile_evaluation(payload, trade_resolution_dataset=trade_resolution_dataset)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.setdefault("artifacts", {})["output_json"] = str(output_path)
    if handoff_overrides:
        result["handoff"] = {key: value for key, value in handoff_overrides.items() if value}
    if output_md:
        md_path = Path(output_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_shadow_profile_evaluation_markdown(result), encoding="utf-8")
        result["artifacts"]["output_md"] = str(md_path)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"summary": result["summary"], "artifacts": result["artifacts"]}



def _trade_row_is_resolved(row: dict[str, Any]) -> bool:
    result = str(row.get("trade_result") or "").strip().lower()
    if result in {"win", "loss"}:
        return True
    resolution = row.get("resolution") if isinstance(row.get("resolution"), dict) else {}
    return bool(resolution.get("available")) and result != "unresolved"


def _accumulate_rule_bucket(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    bucket["trades"] += 1
    result = str(row.get("trade_result") or "").strip().lower()
    if result == "win":
        bucket["wins"] += 1
    elif result == "loss":
        bucket["losses"] += 1
    bucket["estimated_pnl_usdc"] += _to_float(row.get("estimated_pnl_usdc"))
    bucket["notional_usd"] += _to_float(row.get("notional_usd") or row.get("account_trade_notional_usd"))
    wallet = str(row.get("wallet") or "").strip()
    if wallet:
        bucket["wallets"].add(wallet)
    if len(bucket["examples"]) < 3:
        bucket["examples"].append(
            {
                "title": row.get("title") or row.get("question") or "",
                "price": _to_float(row.get("price") or row.get("account_trade_price")),
                "side": row.get("side") or "",
                "effective_position": row.get("effective_position") or _effective_trade_position(row),
                "trade_result": row.get("trade_result") or "",
                "estimated_pnl_usdc": round(_to_float(row.get("estimated_pnl_usdc")), 6),
            }
        )


def _finalize_rule_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    notional = round(float(bucket["notional_usd"]), 6)
    pnl = round(float(bucket["estimated_pnl_usdc"]), 6)
    trades = int(bucket["trades"])
    wins = int(bucket["wins"])
    rule = {
        "handle": bucket["handle"],
        "wallets": sorted(bucket["wallets"]),
        "slice_type": bucket["slice_type"],
        "weather_market_type": bucket["weather_market_type"],
        "effective_position": bucket["effective_position"],
        "trades": trades,
        "wins": wins,
        "losses": int(bucket["losses"]),
        "winrate": round(wins / trades, 6) if trades else 0.0,
        "estimated_pnl_usdc": pnl,
        "notional_usd": notional,
        "roi": round(pnl / notional, 6) if notional else 0.0,
        "examples": bucket["examples"],
        "min_trades": int(bucket["min_trades"]),
    }
    if bucket.get("city"):
        rule["city"] = bucket["city"]
    return rule


def _rule_action(rule: dict[str, Any]) -> str:
    enough_sample = int(rule.get("trades") or 0) >= int(rule.get("min_trades") or 0)
    enough_notional = _to_float(rule.get("notional_usd")) >= 50.0
    pnl = _to_float(rule.get("estimated_pnl_usdc"))
    roi = _to_float(rule.get("roi"))
    if enough_sample and enough_notional and pnl > 20.0 and roi > 0.03:
        return "paper_candidate_allow"
    if enough_sample and enough_notional and pnl < -20.0 and roi < -0.03:
        return "avoid_or_invert_filter"
    return ""


def _rule_confidence(rule: dict[str, Any]) -> str:
    if rule.get("action") == "avoid_or_invert_filter":
        return "medium" if int(rule.get("trades") or 0) >= 8 else "low"
    if int(rule.get("trades") or 0) >= 15 and _to_float(rule.get("roi")) >= 0.10 and _to_float(rule.get("estimated_pnl_usdc")) >= 100.0:
        return "high"
    return "medium"


def _profile_rule_configs_from_rules(rules: list[dict[str, Any]]) -> dict[str, Any]:
    profiles: dict[str, dict[str, Any]] = {}
    for rule in rules:
        handle = str(rule.get("handle") or "unknown")
        profile = profiles.setdefault(
            handle,
            {
                "handle": handle,
                "wallets": [],
                "allow_rules": [],
                "avoid_rules": [],
                "paper_only": True,
                "live_order_allowed": False,
            },
        )
        profile["wallets"] = sorted(set(profile["wallets"]) | set(rule.get("wallets") or []))
        compact = {key: rule[key] for key in ("slice_type", "weather_market_type", "effective_position", "trades", "winrate", "estimated_pnl_usdc", "roi", "confidence") if key in rule}
        if rule.get("city"):
            compact["city"] = rule["city"]
        compact["paper_only"] = True
        compact["live_order_allowed"] = False
        if rule.get("action") == "paper_candidate_allow":
            profile["allow_rules"].append(compact)
        elif rule.get("action") == "avoid_or_invert_filter":
            profile["avoid_rules"].append(compact)
    return profiles


def _historical_profile_rule_candidates_markdown(result: dict[str, Any]) -> str:
    summary = result.get("summary", {})
    lines = [
        "# Historical profile rule candidates",
        "",
        "Paper-only profile gates from resolved account trade slices.",
        "",
        f"- Resolved trades: {summary.get('resolved_trades', 0)} / {summary.get('input_trades', 0)}",
        f"- Allow rules: {summary.get('allow_rules', 0)}",
        f"- Avoid / invert filters: {summary.get('avoid_rules', 0)}",
        "",
        "| Action | Handle | Slice | City | Type | Side | Trades | Winrate | PnL | ROI | Confidence |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for rule in result.get("rules", []):
        lines.append(
            f"| {rule.get('action')} | {rule.get('handle')} | {rule.get('slice_type')} | {rule.get('city', '')} | "
            f"{rule.get('weather_market_type')} | {rule.get('effective_position')} | {rule.get('trades')} | "
            f"{rule.get('winrate'):.2f} | {rule.get('estimated_pnl_usdc'):.2f} | {rule.get('roi'):.3f} | {rule.get('confidence')} |"
        )
    lines.append("")
    lines.append("Safety: paper_only=true, live_order_allowed=false. These gates do not authorize live orders.")
    return "\n".join(lines) + "\n"

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
    if is_closed and outcome_prices and outcomes and len(outcome_prices) == len(outcomes):
        best_idx = max(range(len(outcome_prices)), key=lambda idx: outcome_prices[idx])
        confidence = outcome_prices[best_idx]
        inferred = outcomes[best_idx] if best_idx < len(outcomes) else ""
        if inferred in {"Yes", "No"} and confidence >= 0.99:
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
    terminal_orderbook_resolution = _resolution_from_terminal_orderbook(market)
    if terminal_orderbook_resolution:
        return {**base, **terminal_orderbook_resolution}
    return None


def _resolution_from_terminal_orderbook(market: dict[str, Any]) -> dict[str, Any] | None:
    best_bid = _to_float(market.get("best_bid"))
    best_ask = _to_float(market.get("best_ask"))
    candidate_prices = [best_bid, best_ask]
    for level in [*_jsonish_list(market.get("bids") or market.get("bid_levels")), *_jsonish_list(market.get("asks") or market.get("ask_levels"))]:
        if isinstance(level, dict):
            candidate_prices.append(_to_float(level.get("price")))
    prices = [price for price in candidate_prices if price > 0]
    if not prices:
        return None
    low = min(prices)
    high = max(prices)
    if low <= 0.01 and high >= 0.99:
        return {
            "resolved_outcome": "No" if best_ask and best_ask <= 0.01 else "Yes",
            "status": "terminal_orderbook_price_resolved_proxy",
            "source": "clob_terminal_orderbook_proxy",
            "confidence": round(1.0 - best_ask, 6) if best_ask > 0 else round(1.0 - low, 6),
            "market_closed": False,
        }
    return None


def _market_resolution_aliases(market: dict[str, Any], *, market_id: str, resolution: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    values: list[Any] = [
        market_id,
        market.get("market_id"),
        market.get("conditionId"),
        market.get("condition_id"),
        market.get("clobTokenId"),
        market.get("token_id"),
        market.get("asset"),
        market.get("slug"),
        resolution.get("slug"),
        market.get("question"),
        market.get("title"),
        resolution.get("question"),
        resolution.get("title"),
    ]
    for key in ("clobTokenIds", "clob_token_ids", "tokenIds", "token_ids", "assets", "asset_ids"):
        values.extend(_jsonish_list(market.get(key)))
    for value in values:
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
        handle = str(trade.get("handle") or "")
        profile_id = str(trade.get("profile_id") or wallet_to_profile.get(wallet.lower()) or wallet_to_profile.get(handle.lower()) or wallet or handle or "shadow_profile_default")
        bucket = buckets.setdefault(profile_id, _empty_profile_bucket(profile_id, str(trade.get("profile_role") or "")))
        if wallet:
            wallets = bucket.setdefault("wallets", [])
            if wallet not in wallets:
                wallets.append(wallet)
        if handle:
            handles = bucket.setdefault("handles", [])
            if handle not in handles:
                handles.append(handle)
        if handle and not bucket.get("handle"):
            bucket["handle"] = handle
        if wallet and not bucket.get("wallet"):
            bucket["wallet"] = wallet
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
    if bucket.get("source_recommendation"):
        result["source_recommendation"] = bucket["source_recommendation"]
    if bucket.get("historical_trades"):
        resolved_trades = int(bucket.get("resolved_trades", 0))
        trade_wins = int(bucket.get("trade_wins", 0))
        historical_notional = round(float(bucket.get("historical_notional_usdc", 0.0)), 6)
        if bucket.get("handle"):
            result["handle"] = bucket["handle"]
        if bucket.get("wallet"):
            result["wallet"] = bucket["wallet"]
        if bucket.get("handles"):
            result["handles"] = list(bucket["handles"])
        if bucket.get("wallets"):
            result["wallets"] = list(bucket["wallets"])
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
    historical_resolved = int(profile.get("resolved_trades", 0))
    if profile["orders"] and not profile["resolved_orders"]:
        if historical_resolved >= 5 and profile.get("historical_roi", 0.0) > 0.05 and profile.get("trade_winrate", 0.0) >= 0.55:
            return "promote_to_paper_profile"
        return "needs_resolution_data"
    if profile["resolved_orders"] < 5:
        if historical_resolved >= 5 and profile.get("historical_roi", 0.0) > 0.05 and profile.get("trade_winrate", 0.0) >= 0.55:
            return "promote_to_paper_profile"
        return "observe_more"
    if profile["roi"] > 0.05 and profile["winrate"] >= 0.55:
        return "promote_to_paper_profile"
    if profile["roi"] < -0.05:
        return "reduce_or_disable"
    return "observe_more"


def _shadow_profile_exposure_preview_markdown(result: dict[str, Any]) -> str:
    summary = result.get("summary", {}) if isinstance(result.get("summary"), dict) else {}
    lines = [
        "# Shadow profile exposure preview",
        "",
        "paper_only: true",
        "live_order_allowed: false",
        "",
        "This is theoretical exposure, not expected value or executable profit; fill realism matters, especially for ultra-cheap convexity tickets.",
        "",
        f"orders: {summary.get('orders', 0)}",
        f"markets: {summary.get('markets', 0)}",
        f"max_loss_usdc: {float(summary.get('max_loss_usdc', 0.0)):.4f}",
        f"shares_if_filled: {float(summary.get('shares_if_filled', 0.0)):.4f}",
        f"max_profit_if_true_usdc: {float(summary.get('max_profit_if_true_usdc', 0.0)):.4f}",
        "",
        "| market | orders | notional | shares_if_filled | max_profit_if_true | risk_buckets | questions |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    markets = result.get("markets", {}) if isinstance(result.get("markets"), dict) else {}
    for market_id, market in markets.items():
        if not isinstance(market, dict):
            continue
        lines.append(
            f"| {market_id} | {market.get('orders', 0)} | {float(market.get('total_notional_usdc', 0.0)):.4f} | "
            f"{float(market.get('shares_if_filled', 0.0)):.4f} | {float(market.get('max_profit_if_true_usdc', 0.0)):.4f} | "
            f"{', '.join(market.get('risk_buckets', []))} | {'; '.join(market.get('questions', []))} |"
        )
    return "\n".join(lines) + "\n"



def _shadow_profile_evaluation_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Shadow profile evaluation",
        "",
        "paper_only: true",
        "live_order_allowed: false",
        "",
        "| profile | orders | resolved | winrate | pnl | historical trades | trade winrate | historical pnl | recommendation |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    promoted: list[dict[str, Any]] = []
    for profile in result.get("profiles", []):
        lines.append(
            f"| {profile['profile_id']} | {profile['orders']} | {profile['resolved_orders']} | {profile['winrate']:.2f} | {profile['estimated_pnl_usdc']:.4f} | "
            f"{profile.get('historical_trades', 0)} | {profile.get('trade_winrate', 0.0):.2f} | {profile.get('historical_estimated_pnl_usdc', 0.0):.4f} | {profile['recommendation']} |"
        )
        if profile.get("recommendation") == "promote_to_paper_profile":
            promoted.append(profile)
    promoted_opportunities = [
        profile
        for profile in result.get("profiles", [])
        if profile.get("profile_role") == "promoted_opportunity_watch" or profile.get("source_recommendation") == "promoted_profile_opportunity_watch"
    ]
    if promoted_opportunities:
        summary = result.get("summary", {}) if isinstance(result.get("summary"), dict) else {}
        lines.extend(
            [
                "",
                "## Promoted opportunity watch summary",
                "",
                f"profiles: {summary.get('promoted_opportunity_profiles', len(promoted_opportunities))}",
                f"orders: {summary.get('promoted_opportunity_orders', sum(profile.get('orders', 0) for profile in promoted_opportunities))}",
                f"skipped: {summary.get('promoted_opportunity_skipped', sum(sum(profile.get('skipped_counts', {}).values()) for profile in promoted_opportunities))}",
                "",
                "| profile | source_recommendation | skipped_counts | recommendation |",
                "|---|---|---|---|",
            ]
        )
        for profile in promoted_opportunities:
            skipped_counts = ", ".join(f"{reason}={count}" for reason, count in profile.get("skipped_counts", {}).items())
            lines.append(
                f"| {profile['profile_id']} | {profile.get('source_recommendation', '')} | {skipped_counts} | {profile['recommendation']} |"
            )
        handoff = result.get("handoff", {}) if isinstance(result.get("handoff"), dict) else {}
        output_json = str(result.get("artifacts", {}).get("output_json") or "<shadow-profile-evaluation.json>")
        dataset_json = str(handoff.get("dataset_json") or "<trade-no-trade-dataset.json>")
        orderbooks_json = str(handoff.get("orderbooks_json") or "<orderbooks.json>")
        forecasts_json = str(handoff.get("forecasts_json") or "<forecasts.json>")
        stress_overlay_json = str(handoff.get("stress_overlay_json") or "<candidate-stress-overlay.json>")
        run_id = str(handoff.get("run_id") or "<next-promoted-opportunity-run>")
        paper_orders_json = str(handoff.get("paper_orders_json") or "<stress-overlay-paper-orders.json>")
        exposure_json = str(handoff.get("exposure_json") or "<paper-exposure-preview.json>")
        exposure_md = str(handoff.get("exposure_md") or "<paper-exposure-preview.md>")
        lines.extend(
            [
                "",
                "Suggested paper replay command:",
                "",
                "```bash",
                f"python -m weather_pm.cli shadow-paper-runner --dataset-json {dataset_json} --orderbooks-json {orderbooks_json} --forecasts-json {forecasts_json} "
                f"--promoted-profiles-json {output_json} --stress-overlay-json {stress_overlay_json} --run-id {run_id} --output-json {paper_orders_json}",
                "```",
                "",
                "Suggested exposure preview command:",
                "",
                "```bash",
                f"python -m weather_pm.cli shadow-profile-exposure-preview --paper-orders-json {paper_orders_json} "
                f"--output-json {exposure_json} --output-md {exposure_md}",
                "```",
            ]
        )
    if promoted:
        lines.extend(
            [
                "",
                "## Promoted paper profile suggestions",
                "",
                "Pass the JSON evaluation artifact back to `shadow-paper-runner --promoted-profiles-json` to apply these paper-only profile configs.",
                "",
                "| profile | suggested_max_order_usdc | suggested_min_edge | handles | wallets |",
                "|---|---:|---:|---|---|",
            ]
        )
        for profile in promoted:
            lines.append(
                f"| {profile['profile_id']} | {profile.get('suggested_max_order_usdc', 0.0):.2f} | {profile.get('suggested_min_edge', 0.0):.4f} | "
                f"{', '.join(profile.get('handles', []))} | {', '.join(profile.get('wallets', []))} |"
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
    for key_name in ("market_id", "conditionId", "condition_id", "token_id", "tokenId", "asset", "asset_id", "clobTokenId", "clob_token_id", "slug", "surface_key", "title", "question"):
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


def _historical_profile_rule_for_row(row: dict[str, Any], rules: list[dict[str, Any]]) -> dict[str, Any]:
    handle = str(row.get("handle") or "").strip().lower()
    wallet = str(row.get("wallet") or "").strip().lower()
    city = str(row.get("city") or "").strip().lower()
    market_type = str(row.get("weather_market_type") or "").strip().lower()
    position = str(row.get("effective_position") or _effective_trade_position(row) or "Yes").strip().title()
    candidates: list[tuple[int, dict[str, Any]]] = []
    for rule in rules:
        if rule.get("action") not in {"paper_candidate_allow", "avoid_or_invert_filter"}:
            continue
        rule_handle = str(rule.get("handle") or "").strip().lower()
        rule_wallets = {str(value or "").strip().lower() for value in rule.get("wallets", []) if value}
        if rule_handle and rule_handle != handle and wallet not in rule_wallets:
            continue
        if str(rule.get("weather_market_type") or "").strip().lower() != market_type:
            continue
        if str(rule.get("effective_position") or "").strip().title() != position:
            continue
        score = 1
        if rule.get("slice_type") == "handle_city_weather_type_position":
            if str(rule.get("city") or "").strip().lower() != city:
                continue
            score = 2
        candidates.append((score, rule))
    candidates.sort(key=lambda item: (item[0], item[1].get("confidence") == "high", _to_float(item[1].get("trades"))), reverse=True)
    return dict(candidates[0][1]) if candidates else {}


def _compact_historical_profile_rule(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        key: rule[key]
        for key in ("action", "handle", "slice_type", "city", "weather_market_type", "effective_position", "trades", "winrate", "estimated_pnl_usdc", "roi", "confidence")
        if key in rule
    }


def _profile_config_for_row(row: dict[str, Any], profile_configs: dict[str, Any]) -> dict[str, Any]:
    wallet = str(row.get("wallet") or "").lower()
    handle = str(row.get("handle") or "").lower()
    for key in (wallet, handle):
        config = profile_configs.get(key)
        if isinstance(config, dict):
            return dict(config)
    return {}


def _promoted_opportunity_profile_config(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("shadow_signal_source") != "promoted_profile_opportunity_watch":
        return {}
    profile_id = str(row.get("profile_id") or row.get("wallet") or row.get("handle") or "promoted_opportunity_watch")
    max_order = _to_float(row.get("suggested_max_order_usdc")) or 1.0
    min_edge = _to_float(row.get("suggested_min_edge"))
    if min_edge <= 0:
        min_edge = 0.10
    return {
        "profile_id": profile_id,
        "role": "promoted_opportunity_watch",
        "max_order_usdc": max_order,
        "min_edge": min_edge,
        "source_recommendation": "promoted_profile_opportunity_watch",
    }


def _merge_promoted_profile_configs(profile_configs: dict[str, Any], promoted_profiles: dict[str, Any]) -> dict[str, Any]:
    merged = dict(profile_configs)
    profiles = promoted_profiles.get("profiles") if isinstance(promoted_profiles.get("profiles"), list) else []
    for profile in profiles:
        if not isinstance(profile, dict) or profile.get("recommendation") != "promote_to_paper_profile":
            continue
        config = _config_from_promoted_profile(profile)
        for key in _promoted_profile_keys(profile):
            merged.setdefault(key, config)
    return merged


def _config_from_promoted_profile(profile: dict[str, Any]) -> dict[str, Any]:
    profile_id = str(profile.get("profile_id") or "promoted_shadow_profile")
    max_order = _to_float(profile.get("suggested_max_order_usdc")) or 1.0
    min_edge = _to_float(profile.get("suggested_min_edge"))
    if min_edge <= 0:
        min_edge = 0.10
    return {
        "profile_id": profile_id,
        "role": "promoted_historical_shadow_profile",
        "max_order_usdc": max_order,
        "min_edge": min_edge,
        "source_recommendation": "promote_to_paper_profile",
    }


def _promoted_profile_keys(profile: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for name in ("wallet", "handle"):
        raw = str(profile.get(name) or "").strip().lower()
        if raw:
            keys.append(raw)
    for name in ("wallets", "handles"):
        values = profile.get(name) if isinstance(profile.get(name), list) else []
        for value in values:
            raw = str(value or "").strip().lower()
            if raw:
                keys.append(raw)
    return keys


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
