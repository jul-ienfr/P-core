from __future__ import annotations

import hashlib
import json
import shlex
from pathlib import Path
from typing import Any


def build_learning_cycle_contract(
    run_id: str,
    output_dir: str | Path,
    max_accounts: int,
    trades_per_account: int,
    lookback_days: int,
) -> dict[str, Any]:
    return {
        "run_id": str(run_id),
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "output_dir": str(output_dir),
        "limits": {
            "max_accounts": int(max_accounts),
            "trades_per_account": int(trades_per_account),
            "lookback_days": int(lookback_days),
        },
    }


def _canonical_experiment_hash(experiment: dict[str, Any]) -> str:
    canonical = {
        "profile_id": experiment.get("profile_id"),
        "hypothesis": experiment.get("hypothesis"),
        "market_id": experiment.get("market_id"),
        "inputs": experiment.get("inputs"),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _case_inputs(case: dict[str, Any]) -> dict[str, Any]:
    if isinstance(case.get("inputs"), dict):
        return case["inputs"]
    ignored = {
        "profile_id",
        "hypothesis",
        "market_id",
        "paper_only",
        "live_order_allowed",
        "no_real_order_placed",
        "information_score",
        "components",
        "experiment_hash",
        "deduplicated",
    }
    return {key: case[key] for key in sorted(case) if key not in ignored}


def _case_experiment(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile_id": case.get("profile_id", "unknown-profile"),
        "hypothesis": case.get("hypothesis", case.get("reason", "high-information-weather-case")),
        "market_id": case.get("market_id", case.get("slug", "unknown-market")),
        "inputs": _case_inputs(case),
    }


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_number(case: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key in case:
            return _as_float(case[key])
        inputs = case.get("inputs")
        if isinstance(inputs, dict) and key in inputs:
            return _as_float(inputs[key])
    return None


def score_high_information_case(case: dict[str, Any]) -> dict[str, Any]:
    threshold = _first_number(case, ("threshold", "threshold_f", "line"))
    observed = _first_number(case, ("observed", "forecast", "forecast_f", "value", "last_value"))
    if threshold is None or observed is None:
        near_threshold = 0.0
    else:
        distance = abs(threshold - observed)
        scale = max(abs(threshold) * 0.05, 1.0)
        near_threshold = max(0.0, 1.0 - min(distance / scale, 1.0))

    source_gap = min(_as_float(case.get("source_gap", _case_inputs(case).get("source_gap", 0.0))) / 5.0, 1.0)

    probabilities = case.get("profile_probabilities", _case_inputs(case).get("profile_probabilities", {}))
    if isinstance(probabilities, dict) and probabilities:
        values = [_as_float(value) for value in probabilities.values()]
        profile_disagreement = min((max(values) - min(values)) / 0.5, 1.0)
    else:
        profile_disagreement = min(_as_float(case.get("profile_disagreement", 0.0)) / 0.5, 1.0)

    liquidity = min(_as_float(case.get("liquidity", _case_inputs(case).get("liquidity", 0.0))) / 1000.0, 1.0)
    unresolved = case.get("unresolved_uncertainty", case.get("uncertainty", _case_inputs(case).get("uncertainty", 0.0)))
    unresolved_uncertainty = min(_as_float(unresolved), 1.0)

    components = {
        "near_threshold": round(near_threshold * 35.0, 6),
        "source_gap": round(source_gap * 25.0, 6),
        "profile_disagreement": round(profile_disagreement * 20.0, 6),
        "liquidity": round(liquidity * 10.0, 6),
        "unresolved_uncertainty": round(unresolved_uncertainty * 10.0, 6),
    }
    score = round(sum(components.values()), 6)
    experiment = _case_experiment(case)
    return {
        **case,
        "profile_id": experiment["profile_id"],
        "hypothesis": experiment["hypothesis"],
        "market_id": experiment["market_id"],
        "inputs": experiment["inputs"],
        "experiment_hash": _canonical_experiment_hash(experiment),
        "information_score": score,
        "components": components,
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
    }


def build_learning_backfill_plan(
    report: dict[str, Any],
    ledger_path: str | Path,
    max_cases: int = 10,
) -> dict[str, Any]:
    safety = validate_learning_cycle_safety(report)
    if not safety["ok"]:
        raise ValueError(f"unsafe learning report: {', '.join(safety['violations'])}")

    cases = report.get("high_information_cases", [])
    if not isinstance(cases, list):
        cases = []

    existing_hashes: set[str] = set()
    path = Path(ledger_path)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            existing = json.loads(line)
            if existing.get("experiment_hash"):
                existing_hashes.add(str(existing["experiment_hash"]))

    deduplicated = 0
    selected: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            continue
        scored = score_high_information_case(case)
        experiment_hash = scored["experiment_hash"]
        if experiment_hash in existing_hashes or experiment_hash in seen_hashes:
            deduplicated += 1
            continue
        seen_hashes.add(experiment_hash)
        selected.append(scored)

    selected.sort(key=lambda item: (-_as_float(item.get("information_score")), str(item.get("market_id"))))
    limited = selected[: max(0, int(max_cases))]
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "cases": limited,
        "summary": {
            "input_cases": len(cases),
            "deduplicated_cases": deduplicated,
            "selected_cases": len(limited),
            "max_cases": int(max_cases),
        },
        "command_hints": [
            "PYTHONPATH=python/src python3 -m weather_pm.cli learning-cycle --dry-run --no-network"
        ],
    }


def _first_present_number(source: dict[str, Any], keys: tuple[str, ...], default: float = 0.0) -> float:
    for key in keys:
        if key in source:
            return _as_float(source[key], default)
    return default


def build_learning_policy_actions(
    report: dict[str, Any],
    min_resolved_for_promotion: int = 8,
    min_roi_for_promotion: float = 0.05,
    min_winrate_for_promotion: float = 0.55,
) -> dict[str, Any]:
    safety = validate_learning_cycle_safety(report)
    if not safety["ok"]:
        raise ValueError(f"unsafe learning report: {', '.join(safety['violations'])}")

    profile_actions = report.get("profile_actions", [])
    if not isinstance(profile_actions, list):
        profile_actions = []

    action_map = {
        "disable_or_reduce_shadow_profile": "reduce_or_disable_shadow_profile",
        "collect_more_resolutions": "request_resolution_backfill",
    }
    actions: list[dict[str, Any]] = []
    ignored_unknown_actions = 0
    blocked_promotions = 0

    for profile_action in profile_actions:
        if not isinstance(profile_action, dict):
            ignored_unknown_actions += 1
            continue

        source_action = str(profile_action.get("action", profile_action.get("profile_action", "")))
        resolved_count = int(_first_present_number(profile_action, ("resolved_count", "resolved", "sample_size")))
        roi = _first_present_number(profile_action, ("roi", "return_on_investment"))
        winrate = _first_present_number(profile_action, ("winrate", "win_rate"))
        base_action = {
            "profile_id": str(profile_action.get("profile_id", "unknown-profile")),
            "source_action": source_action,
            "resolved_count": resolved_count,
            "roi": roi,
            "winrate": winrate,
            "paper_only": True,
            "live_order_allowed": False,
            "no_real_order_placed": True,
        }

        if source_action == "promote_candidate_paper_only":
            blocked_reason = None
            if resolved_count < int(min_resolved_for_promotion):
                blocked_reason = "insufficient_resolved_sample"
            elif roi < float(min_roi_for_promotion):
                blocked_reason = "roi_below_threshold"
            elif winrate < float(min_winrate_for_promotion):
                blocked_reason = "winrate_below_threshold"

            if blocked_reason is None:
                actions.append({**base_action, "policy_action": "promote_shadow_profile_paper_only"})
            else:
                blocked_promotions += 1
                actions.append(
                    {
                        **base_action,
                        "policy_action": "request_resolution_backfill",
                        "blocked_promotion_reason": blocked_reason,
                    }
                )
            continue

        policy_action = action_map.get(source_action)
        if policy_action is None:
            ignored_unknown_actions += 1
            continue
        actions.append({**base_action, "policy_action": policy_action})

    return {
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "actions": actions,
        "summary": {
            "input_profile_actions": len(profile_actions),
            "policy_actions": len(actions),
            "ignored_unknown_actions": ignored_unknown_actions,
            "blocked_promotions": blocked_promotions,
        },
    }


def _norm_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def _row_match_keys(row: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for key in ("profile_id", "handle", "wallet", "address", "account", "username", "slug"):
        normalized = _norm_key(row.get(key))
        if normalized:
            keys.add(normalized)
    return keys


def _action_priority(action: str) -> int:
    priorities = {
        "collect_more_resolutions": 300,
        "request_resolution_backfill": 300,
        "promote_candidate_paper_only": 200,
        "promote_shadow_profile_paper_only": 200,
        "disable_or_reduce_shadow_profile": 200,
        "reduce_or_disable_shadow_profile": 200,
    }
    return priorities.get(action, 0)


def _best_numeric_score(source: dict[str, Any]) -> float:
    return max(
        _first_present_number(
            source,
            (
                "score",
                "learning_score",
                "information_score",
                "priority_score",
                "roi",
                "pnl",
                "weather_pnl",
                "resolved_count",
                "winrate",
                "win_rate",
            ),
        ),
        0.0,
    )


def select_learning_accounts(
    followlist: list[dict[str, Any]],
    report: dict[str, Any],
    max_accounts: int,
) -> list[dict[str, Any]]:
    safety = validate_learning_cycle_safety(report)
    if not safety["ok"]:
        raise ValueError(f"unsafe learning report: {', '.join(safety['violations'])}")
    limit = max(0, int(max_accounts))
    if limit == 0:
        return []

    profile_actions = report.get("profile_actions", [])
    if not isinstance(profile_actions, list):
        profile_actions = []

    best_action_by_key: dict[str, dict[str, Any]] = {}
    for action_row in profile_actions:
        if not isinstance(action_row, dict):
            continue
        action = str(action_row.get("action", action_row.get("profile_action", action_row.get("policy_action", ""))))
        priority = _action_priority(action)
        if priority <= 0:
            continue
        enriched = {
            "learning_action": action,
            "action_priority": priority,
            "action_score": _best_numeric_score(action_row),
        }
        for key in _row_match_keys(action_row):
            previous = best_action_by_key.get(key)
            candidate_sort = (priority, enriched["action_score"], str(action_row.get("profile_id", "")))
            previous_sort = (
                int(previous.get("action_priority", 0)) if previous else -1,
                _as_float(previous.get("action_score")) if previous else -1.0,
                "",
            )
            if previous is None or candidate_sort > previous_sort:
                best_action_by_key[key] = enriched

    selected: list[dict[str, Any]] = []
    for index, row in enumerate(followlist):
        if not isinstance(row, dict):
            continue
        match_keys = _row_match_keys(row)
        matches = [best_action_by_key[key] for key in match_keys if key in best_action_by_key]
        if not matches:
            continue
        best = max(matches, key=lambda item: (int(item["action_priority"]), _as_float(item["action_score"])))
        numeric_score = _best_numeric_score(row)
        learning_priority = int(best["action_priority"]) + _as_float(best["action_score"]) + numeric_score
        selected.append(
            {
                **row,
                "learning_action": best["learning_action"],
                "learning_priority": round(learning_priority, 6),
                "paper_only": True,
                "live_order_allowed": False,
                "no_real_order_placed": True,
                "_selection_index": index,
                "_numeric_score": numeric_score,
            }
        )

    selected.sort(
        key=lambda row: (
            -_as_float(row.get("learning_priority")),
            str(row.get("profile_id", row.get("handle", row.get("wallet", "")))).casefold(),
            int(row.get("_selection_index", 0)),
        )
    )
    limited = selected[:limit]
    for row in limited:
        row.pop("_selection_index", None)
        row.pop("_numeric_score", None)
    return limited


def build_bounded_backfill_commands(
    output_dir: str | Path,
    followlist_csv: str | Path,
    max_accounts: int,
    trades_per_account: int,
    lookback_days: int = 30,
) -> list[str]:
    if int(max_accounts) <= 0:
        raise ValueError("max_accounts must be positive and bounded")
    if int(trades_per_account) <= 0:
        raise ValueError("trades_per_account must be positive and bounded")
    if int(lookback_days) <= 0:
        raise ValueError("lookback_days must be positive and bounded")

    output = Path(output_dir)
    followlist = Path(followlist_csv)
    raw_trades = output / "raw_account_trades.json"
    weather_trades = output / "weather_account_trades.json"
    profiles = output / "historical_account_profiles.json"
    dataset = output / "shadow_profile_dataset.json"
    report = output / "shadow_profile_report.json"
    paper_orders = output / "shadow_paper_orders.json"
    skips = output / "shadow_paper_skips.json"
    evaluation = output / "shadow_profile_evaluation.json"
    learning_report = output / "shadow_profile_learning_report.json"
    learning_md = output / "shadow_profile_learning_report.md"

    def command(surface: str, *args: str) -> str:
        safety_comment = "# plan-only paper/shadow no-network paper_only=true live_order_allowed=false no_real_order_placed=true"
        return " ".join(
            ["PYTHONPATH=python/src", "python3", "-m", "weather_pm.cli", surface, *[shlex.quote(str(arg)) for arg in args], safety_comment]
        )

    return [
        command(
            "backfill-account-trades",
            "--followlist",
            followlist,
            "--out-json",
            raw_trades,
            "--limit-accounts",
            str(int(max_accounts)),
            "--trades-per-account",
            str(int(trades_per_account)),
        ),
        command(
            "import-account-trades",
            "--trades-json",
            raw_trades,
            "--trades-out",
            weather_trades,
            "--profiles-out",
            profiles,
        ),
        command(
            "shadow-profile-report",
            "--weather-trades-json",
            weather_trades,
            "--markets-json",
            output / "weather_markets_snapshot.json",
            "--dataset-out",
            dataset,
            "--report-out",
            report,
            "--limit",
            str(int(max_accounts)),
            "--accounts-csv",
            followlist,
            "--limit-accounts",
            str(int(max_accounts)),
            "--max-accounts",
            str(int(max_accounts)),
        ),
        command(
            "shadow-paper-runner",
            "--dataset-json",
            dataset,
            "--run-id",
            f"bounded-backfill-{int(max_accounts)}x{int(trades_per_account)}-{int(lookback_days)}d",
            "--output-json",
            paper_orders,
            "--skip-diagnostics-json",
            skips,
            "--max-order-usdc",
            "0",
            "--max-accounts",
            str(int(max_accounts)),
            "--trades-per-account",
            str(int(trades_per_account)),
            "--lookback-days",
            str(int(lookback_days)),
            "--no-network",
        ),
        command(
            "shadow-profile-evaluator",
            "--paper-orders-json",
            paper_orders,
            "--output-json",
            evaluation,
            "--output-md",
            output / "shadow_profile_evaluation.md",
            "--max-accounts",
            str(int(max_accounts)),
        ),
        command(
            "shadow-profile-learning-report",
            "--evaluation-json",
            evaluation,
            "--paper-orders-json",
            paper_orders,
            "--output-json",
            learning_report,
            "--output-md",
            learning_md,
            "--max-accounts",
            str(int(max_accounts)),
            "--trades-per-account",
            str(int(trades_per_account)),
            "--lookback-days",
            str(int(lookback_days)),
        ),
    ]



def append_learning_experiment(
    ledger_path: str | Path,
    experiment: dict[str, Any],
    run_id: str,
    force: bool = False,
) -> dict[str, Any]:
    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    experiment_hash = _canonical_experiment_hash(experiment)

    if path.exists() and not force:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            existing = json.loads(line)
            if existing.get("experiment_hash") == experiment_hash:
                return {**existing, "deduplicated": True}

    row = {
        "run_id": str(run_id),
        "experiment_hash": experiment_hash,
        "status": "awaiting_resolution",
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        **experiment,
        "deduplicated": False,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
    return row


def assemble_learning_cycle_result(
    run_id: str,
    output_dir: str | Path,
    learning_report: dict[str, Any],
    max_accounts: int,
    trades_per_account: int,
    lookback_days: int,
    ledger_path: str | Path | None = None,
    max_cases: int = 10,
) -> dict[str, Any]:
    report_safety = validate_learning_cycle_safety(learning_report)
    if not report_safety["ok"]:
        raise ValueError(f"unsafe learning report: {', '.join(report_safety['violations'])}")

    output_path = Path(output_dir)
    resolved_ledger_path = Path(ledger_path) if ledger_path is not None else output_path / "learning_experiments.jsonl"
    contract = build_learning_cycle_contract(
        run_id=run_id,
        output_dir=output_path,
        max_accounts=max_accounts,
        trades_per_account=trades_per_account,
        lookback_days=lookback_days,
    )
    policy = build_learning_policy_actions(learning_report)
    backfill_plan = build_learning_backfill_plan(learning_report, resolved_ledger_path, max_cases=max_cases)

    ledger_rows: list[dict[str, Any]] = []
    for case in backfill_plan.get("cases", []):
        if not isinstance(case, dict):
            continue
        experiment = {
            "profile_id": case.get("profile_id", "unknown-profile"),
            "hypothesis": case.get("hypothesis", "high-information-weather-case"),
            "market_id": case.get("market_id", "unknown-market"),
            "inputs": case.get("inputs", {}),
        }
        ledger_rows.append(append_learning_experiment(resolved_ledger_path, experiment, run_id=run_id))

    summary = {
        "policy_count": len(policy.get("actions", [])),
        "backfill_count": len(backfill_plan.get("cases", [])),
        "ledger_appended": sum(1 for row in ledger_rows if not row.get("deduplicated")),
        "safety_ok": True,
    }
    result: dict[str, Any] = {
        "ok": True,
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "contract": contract,
        "learning_report": learning_report,
        "policy": policy,
        "backfill_plan": backfill_plan,
        "ledger_path": str(resolved_ledger_path),
        "ledger_rows": ledger_rows,
        "summary": summary,
    }
    safety = validate_learning_cycle_safety(result)
    result["safety"] = safety
    result["ok"] = bool(
        safety["ok"]
        and result["paper_only"] is True
        and result["live_order_allowed"] is False
        and result["no_real_order_placed"] is True
    )
    result["summary"]["safety_ok"] = result["ok"]
    return result


def render_learning_cycle_summary_markdown(result: dict[str, Any]) -> str:
    summary = result.get("summary", {}) if isinstance(result.get("summary"), dict) else {}
    return "\n".join(
        [
            "# Learning Cycle Summary",
            "",
            f"ok: {str(result.get('ok') is True).lower()}",
            f"paper_only: {str(result.get('paper_only') is True).lower()}",
            f"live_order_allowed: {str(result.get('live_order_allowed') is True).lower()}",
            f"no_real_order_placed: {str(result.get('no_real_order_placed') is True).lower()}",
            f"safety_ok: {str(summary.get('safety_ok') is True).lower()}",
            f"policy_count: {int(summary.get('policy_count', 0))}",
            f"backfill_count: {int(summary.get('backfill_count', 0))}",
            f"ledger_appended: {int(summary.get('ledger_appended', 0))}",
            "",
        ]
    )


def validate_learning_cycle_safety(payload: Any) -> dict[str, Any]:
    violations: list[str] = []

    if not isinstance(payload, dict):
        return {"ok": False, "violations": ["payload"]}
    if payload.get("paper_only") is not True:
        violations.append("paper_only")
    if payload.get("live_order_allowed") is not False:
        violations.append("live_order_allowed")

    def scan(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if key == "live_order_allowed" and child is True:
                    violations.append(child_path)
                scan(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                scan(child, f"{path}[{index}]")

    scan(payload, "")
    unique_violations = list(dict.fromkeys(violations))
    return {"ok": not unique_violations, "violations": unique_violations}
