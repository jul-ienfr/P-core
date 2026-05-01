#!/usr/bin/env python3
"""Paper-only shadow wrapper for cron-style operator refresh/readiness/autopilot dry-runs.

This script is safe to invoke from cron, but intentionally does not install a cron
entry, send messages, or place real orders. It runs the existing operator refresh
and profitable-account bridge, derives a compact live-readiness gate, then runs a
local paper-autopilot adapter in dry-run/shadow mode and writes compact
state-change artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(os.environ.get("PCORE_REPO", "/home/jul/P-core"))
PYTHON_SRC = REPO / "python" / "src"
DATA = REPO / "data" / "polymarket"
DEFAULT_CLASSIFIED_CSV = DATA / "weather_profitable_accounts_classified_top5000.csv"
DEFAULT_REVERSE_JSON = DATA / "weather_heavy_trader_registry_full.json"
sys.path.insert(0, str(PYTHON_SRC))
from weather_pm.live_canary_executor import compact_live_canary_execution, execute_live_canary_preflight_from_env  # noqa: E402
from weather_pm.live_canary_gate import build_live_canary_preflight, compact_live_canary_preflight, config_from_env  # noqa: E402
from weather_pm.paper_autopilot_bridge import build_paper_autopilot_ledger  # noqa: E402
from weather_pm.paper_ledger import PaperLedgerError, load_paper_ledger, write_paper_ledger_artifacts  # noqa: E402


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()



def micro_live_marker(data_root: Path) -> Path:
    return data_root / "shadow-cron" / "MICRO_LIVE_DISABLED.paper_only"


def micro_live_safety(data_root: Path) -> dict[str, Any]:
    marker = micro_live_marker(data_root)
    marker.parent.mkdir(parents=True, exist_ok=True)
    if not marker.exists():
        marker.write_text(
            "micro_live_allowed=false\n"
            "paper_only=true\n"
            "live_order_allowed=false\n"
            "created_by=weather_shadow_cron_wrapper\n",
            encoding="utf-8",
        )
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "can_micro_live": False,
        "micro_live_allowed": False,
        "kill_switch": "forced_disabled",
        "marker": str(marker),
    }


def shadow_idempotency_key(row: dict[str, Any], *, stamp: str | None = None) -> str:
    parts = [
        str(row.get("market_id") or row.get("condition_id") or ""),
        str(row.get("token_id") or row.get("asset_id") or ""),
        str(row.get("side") or row.get("action") or ""),
        str(row.get("strict_limit") or row.get("strict_limit_price") or ""),
        str(stamp or row.get("run_id") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]

def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_file(root: Path, patterns: list[str]) -> Path:
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(root.glob(pattern))
        candidates.extend(root.rglob(pattern))
    candidates = [path for path in candidates if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"no artifact matching {patterns} under {root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def operator_input_default(data_root: Path) -> Path:
    return latest_file(
        data_root,
        [
            "operator-refresh/weather_operator_refresh_*.json",
            "strategy-shortlists/weather_strategy_shortlist_*.json",
            "weather_strategy_shortlist_*.json",
        ],
    )


def run_json(cmd: list[str], *, repo: Path, timeout: int = 300) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "python" / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    proc = subprocess.run(cmd, cwd=repo, env=env, text=True, capture_output=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed rc={proc.returncode}: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        return {"stdout": proc.stdout, "stderr": proc.stderr}
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"command did not end with JSON: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}") from exc


def compact_counts(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _gate(row: dict[str, Any]) -> dict[str, Any]:
    gate = row.get("normal_size_gate")
    return gate if isinstance(gate, dict) else {}


def build_live_readiness(summary_payload: dict[str, Any], *, output_json: Path | None = None) -> dict[str, Any]:
    """Derive a compact live-readiness artifact from the account bridge output."""

    rollup = summary_payload.get("daily_operator_rollup") if isinstance(summary_payload.get("daily_operator_rollup"), dict) else {}
    rows = [row for row in summary_payload.get("live_watchlist", []) if isinstance(row, dict)]
    ready_rows = [row for row in rows if _gate(row).get("live_ready") is True]
    blocked_rows = [row for row in rows if _gate(row).get("live_ready") is not True]
    blocked_reasons: list[str] = []
    for row in blocked_rows:
        reasons = _gate(row).get("reasons")
        if isinstance(reasons, list):
            blocked_reasons.extend(str(reason) for reason in reasons if reason)
        elif row.get("operator_verdict"):
            blocked_reasons.append(str(row["operator_verdict"]))
    payload: dict[str, Any] = {
        "ok": True,
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "status": "READY" if bool(rollup.get("live_ready")) else "NOT_READY",
        "live_ready": bool(rollup.get("live_ready")),
        "live_ready_count": int(rollup.get("live_ready_count") or len(ready_rows)),
        "watchlist_count": int(rollup.get("watchlist_count") or len(rows)),
        "normal_size_blocked_count": int(rollup.get("normal_size_blocked_count") or len(blocked_rows)),
        "global_recommendation": rollup.get("global_recommendation") or "watch_only",
        "not_ready_reason_counts": rollup.get("not_ready_reason_counts") if isinstance(rollup.get("not_ready_reason_counts"), dict) else compact_counts(blocked_reasons),
        "ready_market_ids": [str(row.get("market_id") or row.get("condition_id") or "") for row in ready_rows if row.get("market_id") or row.get("condition_id")],
    }
    if output_json:
        payload["artifacts"] = {"live_readiness_json": str(output_json)}
        write_json(output_json, payload)
    return payload


def build_shadow_autopilot_bridge(
    *,
    readiness: dict[str, Any],
    account_summary: dict[str, Any],
    max_actions: int = 10,
    output_json: Path | None = None,
) -> dict[str, Any]:
    """Local adapter for the paper-autopilot bridge in dry-run/shadow mode.

    No external bridge is required and no order APIs are called. The adapter turns
    readiness and watchlist rows into proposed paper-only actions.
    """

    rows = [row for row in account_summary.get("live_watchlist", []) if isinstance(row, dict)]
    actions: list[dict[str, Any]] = []
    for row in rows:
        gate = _gate(row)
        reasons = gate.get("reasons") if isinstance(gate.get("reasons"), list) else []
        market_id = str(row.get("market_id") or row.get("condition_id") or "")
        label = " ".join(str(part) for part in [row.get("city"), row.get("temp"), row.get("unit"), row.get("side")] if part not in (None, ""))
        if gate.get("live_ready") is True:
            action = "PAPER_AUTOPILOT_SHADOW_REVIEW"
            rationale = "normal_size_gate live_ready=true; still dry-run/shadow only"
        else:
            action = "WATCH_ONLY"
            rationale = ", ".join(str(reason) for reason in reasons) or str(row.get("operator_verdict") or "not_live_ready")
        would_place_order = action == "PAPER_AUTOPILOT_SHADOW_REVIEW"
        actions.append(
            {
                "market_id": market_id,
                "label": label or market_id or "unknown_market",
                "action": action,
                "would_place_order": would_place_order,
                "idempotency_key": shadow_idempotency_key(row, stamp=str(readiness.get("timestamp") or "")),
                "dry_run": True,
                "shadow": True,
                "paper_only": True,
                "can_micro_live": False,
                "micro_live_allowed": False,
                "live_order_allowed": False,
                "no_real_order_placed": True,
                "live_execution_payload": None,
                "rationale": rationale,
            }
        )
    selected = actions[: max(int(max_actions), 0)]
    payload: dict[str, Any] = {
        "ok": True,
        "mode": "dry-run/shadow",
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "messages_allowed": False,
        "orders_allowed": False,
        "can_micro_live": False,
        "micro_live_allowed": False,
        "would_place_order_count": sum(1 for action in selected if action.get("would_place_order") is True),
        "status": readiness.get("status", "NOT_READY"),
        "proposed_action_count": len(selected),
        "action_counts": compact_counts([str(action["action"]) for action in selected]),
        "actions": selected,
    }
    if output_json:
        payload["artifacts"] = {"shadow_autopilot_bridge_json": str(output_json)}
        write_json(output_json, payload)
    return payload


def compact_state(payload: dict[str, Any]) -> dict[str, Any]:
    readiness = payload.get("live_readiness") if isinstance(payload.get("live_readiness"), dict) else {}
    bridge = payload.get("shadow_autopilot_bridge") if isinstance(payload.get("shadow_autopilot_bridge"), dict) else {}
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "can_micro_live": False,
        "micro_live_allowed": False,
        "readiness_status": readiness.get("status"),
        "live_ready_count": readiness.get("live_ready_count", 0),
        "watchlist_count": readiness.get("watchlist_count", 0),
        "normal_size_blocked_count": readiness.get("normal_size_blocked_count", 0),
        "global_recommendation": readiness.get("global_recommendation"),
        "not_ready_reason_counts": readiness.get("not_ready_reason_counts", {}),
        "shadow_action_counts": bridge.get("action_counts", {}),
        "proposed_action_count": bridge.get("proposed_action_count", 0),
        "would_place_order_count": bridge.get("would_place_order_count", 0),
    }


def diff_state(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    if previous is None:
        return {"changed": True, "initial": True, "fields": sorted(current.keys())}
    changed = sorted(key for key, value in current.items() if previous.get(key) != value)
    return {"changed": bool(changed), "initial": False, "fields": changed}


def latest_previous_state(data_root: Path, current_path: Path) -> dict[str, Any] | None:
    candidates = sorted(
        [path for path in (data_root / "shadow-cron").glob("weather_shadow_state_*.json") if path.is_file() and path != current_path],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            payload = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        state = payload.get("state") if isinstance(payload, dict) else None
        if isinstance(state, dict):
            return state
    return None


def assert_safety(payload: Any) -> None:
    if isinstance(payload, dict):
        if payload.get("live_order_allowed") is True:
            raise RuntimeError("safety violation: live_order_allowed=true")
        if payload.get("orders_allowed") is True:
            raise RuntimeError("safety violation: orders_allowed=true")
        if payload.get("can_micro_live") is True or payload.get("micro_live_allowed") is True:
            raise RuntimeError("safety violation: micro live enabled")
        if payload.get("messages_sent") or payload.get("message_sent"):
            raise RuntimeError("safety violation: message sent flag present")
        for value in payload.values():
            assert_safety(value)
    elif isinstance(payload, list):
        for value in payload:
            assert_safety(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run paper-only shadow cron wrapper without scheduling cron, messages, or real orders.")
    parser.add_argument("--repo", default=str(REPO))
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--timestamp", default=utc_stamp())
    parser.add_argument("--resolution-date", default=today_utc())
    parser.add_argument("--input-json", default=None, help="Saved operator refresh or strategy shortlist JSON. Defaults to latest compatible artifact.")
    parser.add_argument("--classified-csv", default=None)
    parser.add_argument("--reverse-engineering-json", default=None)
    parser.add_argument("--operator-limit", type=int, default=10)
    parser.add_argument("--max-shadow-actions", type=int, default=10)
    parser.add_argument("--source", choices=("fixture", "live"), default="live")
    parser.add_argument("--ledger-json", default=None, help="Append-only derived paper ledger JSON. Defaults under shadow-cron.")
    parser.add_argument("--skip-paper-ledger", action="store_true", help="Skip append-only paper ledger derivation for fixture/debug runs.")
    parser.add_argument("--skip-resolution-status", action="store_true", help="Do not refresh direct/latest resolution status; useful for fixture tests.")
    parser.add_argument("--skip-orderbook", action="store_true", help="Do not refresh orderbook metrics; useful for fixture tests.")
    args = parser.parse_args(argv)

    repo = Path(args.repo)
    data_root = Path(args.data_root) if args.data_root else repo / "data" / "polymarket"
    stamp = args.timestamp
    input_path = Path(args.input_json) if args.input_json else operator_input_default(data_root)
    classified_csv = Path(args.classified_csv) if args.classified_csv else data_root / DEFAULT_CLASSIFIED_CSV.relative_to(DATA)
    reverse_json = Path(args.reverse_engineering_json) if args.reverse_engineering_json else data_root / DEFAULT_REVERSE_JSON.relative_to(DATA)

    out_dir = data_root / "shadow-cron"
    refresh_path = out_dir / f"weather_operator_refresh_{stamp}.json"
    account_summary_path = out_dir / f"weather_account_bridge_{stamp}.json"
    readiness_path = out_dir / f"weather_live_readiness_{stamp}.json"
    autopilot_path = out_dir / f"weather_shadow_autopilot_bridge_{stamp}.json"
    live_canary_path = out_dir / f"weather_live_canary_preflight_{stamp}.json"
    live_canary_execute_path = out_dir / f"weather_live_canary_execute_{stamp}.json"
    state_path = out_dir / f"weather_shadow_state_{stamp}.json"
    change_path = out_dir / f"weather_shadow_state_change_{stamp}.json"
    ledger_path = Path(args.ledger_json) if args.ledger_json else out_dir / "weather_paper_autopilot_ledger_latest.json"
    ledger_artifact_dir = out_dir / "paper-autopilot-ledger"

    refresh_cmd = [
        sys.executable,
        "-m",
        "weather_pm.cli",
        "operator-refresh",
        "--input-json",
        str(input_path),
        "--source",
        args.source,
        "--resolution-date",
        args.resolution_date,
        "--operator-limit",
        str(args.operator_limit),
        "--output-json",
        str(refresh_path),
        "--storage-backend",
        "noop",
        "--storage-dry-run",
    ]
    if args.skip_resolution_status:
        refresh_cmd.append("--skip-resolution-status")
    if args.skip_orderbook:
        refresh_cmd.append("--skip-orderbook")
    refresh_compact = run_json(refresh_cmd, repo=repo, timeout=300)

    summary_compact = run_json(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "profitable-accounts-operator-summary",
            "--classified-csv",
            str(classified_csv),
            "--reverse-engineering-json",
            str(reverse_json),
            "--operator-report-json",
            str(refresh_path),
            "--output-json",
            str(account_summary_path),
        ],
        repo=repo,
        timeout=180,
    )

    account_summary = load_json(account_summary_path)
    if not isinstance(account_summary, dict):
        raise RuntimeError("account bridge output must be a JSON object")
    safety = micro_live_safety(data_root)
    readiness = build_live_readiness(account_summary, output_json=readiness_path)
    readiness["micro_live_safety"] = safety
    readiness["can_micro_live"] = False
    readiness["micro_live_allowed"] = False
    write_json(readiness_path, readiness)
    autopilot = build_shadow_autopilot_bridge(
        readiness=readiness,
        account_summary=account_summary,
        max_actions=args.max_shadow_actions,
        output_json=autopilot_path,
    )
    live_canary = build_live_canary_preflight(
        account_summary,
        config=config_from_env(run_id=stamp),
        output_json=live_canary_path,
    )
    live_canary_execution = execute_live_canary_preflight_from_env(live_canary, output_json=live_canary_execute_path)
    paper_ledger_payload: dict[str, Any] = {
        "paper_only": True,
        "live_order_allowed": False,
        "skipped": True,
        "reason": "skip_paper_ledger_requested" if args.skip_paper_ledger else "no_eligible_rows_or_bridge_error",
        "ledger_json": str(ledger_path),
    }
    if not args.skip_paper_ledger:
        try:
            existing_ledger = load_paper_ledger(ledger_path) if ledger_path.exists() else {"orders": []}
            derived = build_paper_autopilot_ledger(account_summary, ledger=existing_ledger, run_id=stamp)
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            ledger_path.write_text(json.dumps(derived, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
            artifact = write_paper_ledger_artifacts(derived, output_dir=ledger_artifact_dir)
            paper_ledger_payload = {
                "paper_only": True,
                "live_order_allowed": False,
                "append_only": True,
                "ledger_json": str(ledger_path),
                "summary": derived.get("summary", {}),
                "paper_autopilot_summary": derived.get("paper_autopilot_summary", {}),
                "paper_autopilot_skipped": derived.get("paper_autopilot_skipped", []),
                "artifacts": artifact.get("artifacts", {}),
            }
        except (OSError, json.JSONDecodeError, PaperLedgerError, ValueError) as exc:
            paper_ledger_payload = {
                "paper_only": True,
                "live_order_allowed": False,
                "append_only": True,
                "ledger_json": str(ledger_path),
                "error": str(exc),
                "paper_autopilot_summary": {"appended_orders": 0},
            }

    state_payload = {
        "timestamp": stamp,
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "messages_sent": False,
        "cron_created": False,
        "can_micro_live": False,
        "micro_live_allowed": False,
        "micro_live_safety": safety,
        "input_json": str(input_path),
        "operator_refresh": refresh_compact,
        "account_bridge": summary_compact,
        "live_readiness": readiness,
        "shadow_autopilot_bridge": autopilot,
        "live_canary_preflight": live_canary,
        "live_canary_execution": live_canary_execution,
        "paper_autopilot_ledger": paper_ledger_payload,
        "artifacts": {
            "operator_refresh_json": str(refresh_path),
            "account_bridge_json": str(account_summary_path),
            "live_readiness_json": str(readiness_path),
            "shadow_autopilot_bridge_json": str(autopilot_path),
            "live_canary_preflight_json": str(live_canary_path),
            "live_canary_execute_json": str(live_canary_execute_path),
            "paper_autopilot_ledger_json": str(ledger_path),
            "state_json": str(state_path),
            "state_change_json": str(change_path),
        },
    }
    state_payload["state"] = compact_state(state_payload)
    previous = latest_previous_state(data_root, state_path)
    state_payload["state_change"] = diff_state(previous, state_payload["state"])
    assert_safety(state_payload)
    write_json(state_path, state_payload)
    write_json(
        change_path,
        {
            "timestamp": stamp,
            "paper_only": True,
            "live_order_allowed": False,
            "no_real_order_placed": True,
            "changed": state_payload["state_change"]["changed"],
            "state_change": state_payload["state_change"],
            "state": state_payload["state"],
            "artifacts": state_payload["artifacts"],
        },
    )

    print(
        json.dumps(
            {
                "ok": True,
                "paper_only": True,
                "live_order_allowed": False,
                "no_real_order_placed": True,
                "messages_sent": False,
                "cron_created": False,
                "status": readiness["status"],
                "changed": state_payload["state_change"]["changed"],
                "state_json": str(state_path),
                "state_change_json": str(change_path),
                "paper_autopilot_ledger": paper_ledger_payload,
                "live_canary_preflight": compact_live_canary_preflight(live_canary),
                "live_canary_execution": compact_live_canary_execution(live_canary_execution),
                "artifacts": state_payload["artifacts"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
