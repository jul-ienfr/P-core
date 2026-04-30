#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path("/home/jul/P-core")
PYTHON_SRC = REPO / "python" / "src"
DATA = REPO / "data" / "polymarket"
DEFAULT_CLASSIFIED_CSV = DATA / "weather_profitable_accounts_classified_top5000.csv"
DEFAULT_REVERSE_JSON = DATA / "weather_heavy_trader_registry_full.json"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def run_json(cmd: list[str], *, timeout: int = 300) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PYTHON_SRC) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    proc = subprocess.run(cmd, cwd=REPO, env=env, text=True, capture_output=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed rc={proc.returncode}: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        return {"stdout": proc.stdout, "stderr": proc.stderr}
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"command did not end with JSON: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}") from exc


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_file(patterns: list[str]) -> Path:
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(DATA.glob(pattern))
        candidates.extend(DATA.rglob(pattern))
    candidates = [path for path in candidates if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"no artifact matching {patterns}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def operator_input_default() -> Path:
    return latest_file([
        "operator-refresh/weather_operator_refresh_*.json",
        "strategy-shortlists/weather_strategy_shortlist_*.json",
        "weather_strategy_shortlist_*.json",
    ])


def monitor_json_from_result(result: dict[str, Any]) -> Path:
    json_path = result.get("json")
    if json_path:
        return Path(str(json_path))
    return latest_file(["weather_paper_cron_monitor_*.json"])


def _contains_live_order_allowed_true(payload: Any) -> bool:
    if isinstance(payload, dict):
        if payload.get("live_order_allowed") is True:
            return True
        return any(_contains_live_order_allowed_true(value) for value in payload.values())
    if isinstance(payload, list):
        return any(_contains_live_order_allowed_true(value) for value in payload)
    return False


def _is_safe_shadow_skip_diagnostics(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return payload.get("paper_only") is True and payload.get("live_order_allowed") is False and not _contains_live_order_allowed_true(payload)


def latest_shadow_skip_diagnostics(data_root: Path = DATA) -> dict[str, Any] | None:
    candidates = sorted(
        [path for path in data_root.rglob("shadow_profile_skip_diagnostics*.json") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            payload = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if not _is_safe_shadow_skip_diagnostics(payload):
            continue
        payload = dict(payload)
        artifacts = dict(payload.get("artifacts", {}) if isinstance(payload.get("artifacts"), dict) else {})
        artifacts["shadow_skip_diagnostics_json"] = str(path)
        payload["artifacts"] = artifacts
        return payload
    return None


def _market_label(row: dict[str, Any]) -> str:
    city = str(row.get("city") or "").strip()
    temp = row.get("temp", row.get("temperature", ""))
    unit = str(row.get("unit") or "").strip()
    side = str(row.get("side") or "").strip()
    pieces = [piece for piece in [city, f"{temp}{unit}" if temp != "" else "", side] if piece]
    return " ".join(pieces) or str(row.get("question") or row.get("market_id") or "unknown market")


def _normal_size_gate(row: dict[str, Any]) -> dict[str, Any]:
    gate = row.get("normal_size_gate")
    return gate if isinstance(gate, dict) else {}


def build_actionable_only_summary(account_summary: dict[str, Any], paper_watchlist: dict[str, Any]) -> dict[str, Any]:
    rollup = account_summary.get("daily_operator_rollup") if isinstance(account_summary.get("daily_operator_rollup"), dict) else {}
    not_ready = rollup.get("not_ready_reason_counts") if isinstance(rollup.get("not_ready_reason_counts"), dict) else {}
    watchlist = paper_watchlist.get("watchlist") if isinstance(paper_watchlist.get("watchlist"), list) else []
    live_watchlist = account_summary.get("live_watchlist") if isinstance(account_summary.get("live_watchlist"), list) else []
    actionable: list[dict[str, Any]] = []
    monitor: list[dict[str, Any]] = []
    why_not_actionable: list[dict[str, Any]] = []
    for row in watchlist:
        if not isinstance(row, dict):
            continue
        action = str(row.get("operator_action") or row.get("action") or "")
        is_add = bool(row.get("add_allowed")) or (action == "ADD" and float(row.get("max_add_usdc") or 0) > 0)
        if is_add:
            actionable.append(row)
        elif action.startswith("HOLD"):
            monitor.append(row)
        gate = _normal_size_gate(row)
        reasons = gate.get("reasons") if isinstance(gate.get("reasons"), list) else []
        live_ready = gate.get("live_ready")
        if reasons and live_ready is not True:
            why_not_actionable.append(
                {
                    "market_id": row.get("market_id") or row.get("condition_id") or row.get("id") or "",
                    "label": _market_label(row),
                    "reasons": [str(reason) for reason in reasons],
                    "verdict": gate.get("verdict") or row.get("normal_size_verdict") or "blocked",
                }
            )
    for row in live_watchlist:
        if not isinstance(row, dict):
            continue
        gate = _normal_size_gate(row)
        reasons = gate.get("reasons") if isinstance(gate.get("reasons"), list) else []
        live_ready = gate.get("live_ready")
        if reasons and live_ready is not True:
            why_not_actionable.append(
                {
                    "market_id": row.get("market_id") or row.get("condition_id") or row.get("id") or "",
                    "label": _market_label(row),
                    "reasons": [str(reason) for reason in reasons],
                    "verdict": gate.get("recommended_action") or row.get("decision_status") or "blocked",
                }
            )
    diag = account_summary.get("shadow_skip_diagnostics") if isinstance(account_summary.get("shadow_skip_diagnostics"), dict) else {}
    diag_summary = diag.get("summary") if isinstance(diag.get("summary"), dict) else {}
    cpr_markets = len(diag.get("market_unlocks") or []) if isinstance(diag.get("market_unlocks"), list) else 0
    wait_for_quote_or_depth = max(int(not_ready.get("missing_tradeable_quote") or 0), int(not_ready.get("insufficient_depth") or 0))
    return {
        "ACTIONABLE_NOW": len(actionable),
        "MONITOR_EXISTING": len(monitor),
        "WAIT_FOR_QUOTE_OR_DEPTH": wait_for_quote_or_depth,
        "CPR_SIGNAL_ONLY_MARKETS": cpr_markets,
        "CPR_SIGNAL_ONLY_SKIPS": int(diag_summary.get("skipped") or 0),
        "actionable_rows": actionable,
        "monitor_rows": monitor,
        "why_not_actionable_rows": why_not_actionable,
        "paper_only": True,
        "live_order_allowed": False,
    }


def render_actionable_only_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "## Actionable-only",
        "",
        f"- ACTIONABLE_NOW: {summary.get('ACTIONABLE_NOW', 0)}",
        f"- MONITOR_EXISTING: {summary.get('MONITOR_EXISTING', 0)}",
        f"- WAIT_FOR_QUOTE_OR_DEPTH: {summary.get('WAIT_FOR_QUOTE_OR_DEPTH', 0)}",
        f"- CPR_SIGNAL_ONLY: {summary.get('CPR_SIGNAL_ONLY_MARKETS', 0)} markets / {summary.get('CPR_SIGNAL_ONLY_SKIPS', 0)} skips",
        "- Safety: paper_only=true; live_order_allowed=false",
        "",
    ]
    actionable = summary.get("actionable_rows") if isinstance(summary.get("actionable_rows"), list) else []
    if actionable:
        lines.append("### Paper-actionable now")
        for row in actionable[:5]:
            lines.append(f"- {row.get('city', '')} {row.get('temp', '')}{row.get('unit', '')} {row.get('side', '')} — max_add={row.get('max_add_usdc', 0)} USDC — EV={row.get('paper_ev_now_usdc', 0)}")
    monitor = summary.get("monitor_rows") if isinstance(summary.get("monitor_rows"), list) else []
    if monitor:
        lines.append("### Monitor existing")
        for row in monitor[:5]:
            lines.append(f"- {row.get('city', '')} {row.get('temp', '')}{row.get('unit', '')} {row.get('side', '')} — {row.get('operator_action', '')} — EV={row.get('paper_ev_now_usdc', 0)}")
    why_not = summary.get("why_not_actionable_rows") if isinstance(summary.get("why_not_actionable_rows"), list) else []
    if why_not:
        lines.append("### Why not actionable")
        for row in why_not[:8]:
            reasons = row.get("reasons") if isinstance(row.get("reasons"), list) else []
            reasons_text = ", ".join(str(reason) for reason in reasons) or "manual_review_required"
            lines.append(f"- `{row.get('market_id', '')}` — {row.get('label', '')} — {row.get('verdict', 'blocked')} — {reasons_text}")
    lines.append("")
    return "\n".join(lines)


def render_shadow_skip_diagnostics_markdown(diagnostics: dict[str, Any]) -> str:
    if not isinstance(diagnostics, dict) or not diagnostics:
        return ""
    summary = diagnostics.get("summary") if isinstance(diagnostics.get("summary"), dict) else {}
    lines = [
        "## Diagnostics replay CPR",
        "",
        f"- Paper orders: {summary.get('paper_orders', 0)}",
        f"- Skipped: {summary.get('skipped', 0)}",
        f"- Skip reasons: {summary.get('skip_reasons', {})}",
        f"- Unlock reasons: {summary.get('unlock_reasons', {})}",
        "- Safety: paper_only=true; live_order_allowed=false",
        "- Décision: CPR reste signal-only tant qu’un compte cible ne trade pas réellement le marché ou qu’un dataset promoted-profile explicite n’est pas utilisé.",
        "",
    ]
    market_unlocks = diagnostics.get("market_unlocks") if isinstance(diagnostics.get("market_unlocks"), list) else []
    if market_unlocks:
        lines.append("### Marchés bloqués / conditions d’unlock")
        for row in market_unlocks[:10]:
            if not isinstance(row, dict):
                continue
            handles = row.get("handles") if isinstance(row.get("handles"), list) else []
            handle_text = ", ".join(str(handle) for handle in handles)
            lines.extend(
                [
                    f"- `{row.get('market_id', '')}` — {row.get('question', '')}",
                    f"  - City: {row.get('city', '')}",
                    f"  - Handles: {handle_text}",
                    f"  - Skipped: {row.get('skipped', 0)}",
                    f"  - Unlock: `{row.get('unlock_condition', 'manual_review_required')}`",
                    f"  - Action: {row.get('operator_action', 'Manual paper-only review required.')}",
                ]
            )
    next_actions = diagnostics.get("operator_next_actions") if isinstance(diagnostics.get("operator_next_actions"), list) else []
    if next_actions:
        lines.extend(["", "### Next actions"])
        lines.extend(f"- `{action}`" for action in next_actions)
    lines.append("")
    return "\n".join(lines)



def render_daily_markdown(
    *,
    stamp: str,
    refresh_path: Path,
    account_summary_path: Path,
    paper_monitor_path: Path,
    paper_watchlist_path: Path,
    paper_watchlist_md: Path,
    daily_json_path: Path,
) -> str:
    account_summary = load_json(account_summary_path)
    paper_watchlist = load_json(paper_watchlist_path)
    rollup = account_summary.get("daily_operator_rollup") if isinstance(account_summary, dict) else {}
    paper_summary = paper_watchlist.get("summary") if isinstance(paper_watchlist, dict) else {}
    ready = bool(rollup.get("live_ready")) if isinstance(rollup, dict) else False
    status = "READY" if ready else "NOT READY"
    actionable_summary = build_actionable_only_summary(account_summary if isinstance(account_summary, dict) else {}, paper_watchlist if isinstance(paper_watchlist, dict) else {})
    actionable_md = render_actionable_only_markdown(actionable_summary)
    skip_diagnostics_md = render_shadow_skip_diagnostics_markdown(account_summary.get("shadow_skip_diagnostics", {}) if isinstance(account_summary, dict) else {})
    lines = [
        f"# Daily operator Polymarket météo — {stamp}",
        "",
        "Mode: **paper-only / dry-run**. Aucun ordre réel placé.",
        "",
        "## Décision",
        f"- Statut live normal-size: **{status}** ({rollup.get('live_ready_count', 0)}/{rollup.get('watchlist_count', 0)} marchés prêts)",
        f"- Recommandation: `{rollup.get('global_recommendation', 'watch_only')}`",
        f"- Normal-size bloqués: {rollup.get('normal_size_blocked_count', 0)}/{rollup.get('watchlist_count', 0)}",
        f"- Raisons NOT READY: {rollup.get('not_ready_reason_counts', {})}",
        "- Garde-fou: live désactivé; paper micro/strict-limit seulement si candidat explicite.",
        "",
        "## Watchlist papier",
        f"- Positions: {paper_summary.get('positions', 0)}",
        f"- Spend: {paper_summary.get('total_spend', 0)} USDC",
        f"- EV now: {paper_summary.get('total_ev_now', 0)} USDC",
        f"- Actions: {paper_summary.get('action_counts', {})}",
        "",
        actionable_md,
        "",
        "## Signaux live READY/NOT READY",
        account_summary.get("daily_operator_markdown", "_daily_operator_markdown missing_"),
        "",
    ]
    if skip_diagnostics_md:
        lines.extend([skip_diagnostics_md, ""])
    lines.extend([
        "## Artifacts",
        f"- Daily JSON: `{daily_json_path}`",
        f"- Operator refresh: `{refresh_path}`",
        f"- Account summary: `{account_summary_path}`",
        f"- Paper monitor: `{paper_monitor_path}`",
        f"- Paper watchlist JSON: `{paper_watchlist_path}`",
        f"- Paper watchlist MD: `{paper_watchlist_md}`",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run paper-only daily weather operator automation: refresh, account bridge, paper watchlist, READY/NOT READY report.")
    parser.add_argument("--timestamp", default=utc_stamp())
    parser.add_argument("--resolution-date", default=today_utc())
    parser.add_argument("--input-json", default=None, help="Saved operator refresh or strategy shortlist JSON. Defaults to latest compatible artifact.")
    parser.add_argument("--classified-csv", default=str(DEFAULT_CLASSIFIED_CSV))
    parser.add_argument("--reverse-engineering-json", default=str(DEFAULT_REVERSE_JSON))
    parser.add_argument("--operator-limit", type=int, default=10)
    parser.add_argument("--skip-cron-monitor", action="store_true", help="Reuse latest paper monitor instead of running weather_cron_monitor_refresh.py")
    args = parser.parse_args()

    stamp = args.timestamp
    input_path = Path(args.input_json) if args.input_json else operator_input_default()
    refresh_path = DATA / "operator-refresh" / f"weather_operator_refresh_{stamp}.json"
    account_summary_path = DATA / "account-analysis" / f"weather_profitable_accounts_operator_summary_{stamp}.json"
    paper_watchlist_path = DATA / "watchlists" / f"weather_paper_watchlist_{stamp}.json"
    paper_watchlist_csv = DATA / "watchlists" / f"weather_paper_watchlist_{stamp}.csv"
    paper_watchlist_md = DATA / "watchlists" / f"weather_paper_watchlist_{stamp}.md"
    daily_json_path = DATA / "operator-daily" / f"weather_operator_daily_{stamp}.json"
    daily_md_path = DATA / "operator-daily" / f"weather_operator_daily_{stamp}.md"

    refresh_compact = run_json([
        sys.executable,
        "-m",
        "weather_pm.cli",
        "operator-refresh",
        "--input-json",
        str(input_path),
        "--source",
        "live",
        "--resolution-date",
        args.resolution_date,
        "--operator-limit",
        str(args.operator_limit),
        "--output-json",
        str(refresh_path),
        "--storage-backend",
        "noop",
        "--storage-dry-run",
    ], timeout=300)

    summary_compact = run_json([
        sys.executable,
        "-m",
        "weather_pm.cli",
        "profitable-accounts-operator-summary",
        "--classified-csv",
        str(args.classified_csv),
        "--reverse-engineering-json",
        str(args.reverse_engineering_json),
        "--operator-report-json",
        str(refresh_path),
        "--output-json",
        str(account_summary_path),
    ], timeout=180)

    if args.skip_cron_monitor:
        paper_monitor_path = latest_file(["weather_paper_cron_monitor_*.json"])
        monitor_compact: dict[str, Any] = {"json": str(paper_monitor_path), "reused": True}
    else:
        monitor_compact = run_json([sys.executable, "scripts/weather_cron_monitor_refresh.py"], timeout=360)
        paper_monitor_path = monitor_json_from_result(monitor_compact)

    paper_watchlist_compact = run_json([
        sys.executable,
        "-m",
        "weather_pm.cli",
        "paper-watchlist",
        "--input-json",
        str(paper_monitor_path),
        "--output-json",
        str(paper_watchlist_path),
        "--output-csv",
        str(paper_watchlist_csv),
        "--output-md",
        str(paper_watchlist_md),
        "--compact",
    ], timeout=180)

    shadow_skip_diagnostics = latest_shadow_skip_diagnostics()
    if shadow_skip_diagnostics:
        account_summary = load_json(account_summary_path)
        if isinstance(account_summary, dict) and "shadow_skip_diagnostics" not in account_summary:
            account_summary["shadow_skip_diagnostics"] = shadow_skip_diagnostics
            write_json(account_summary_path, account_summary)
            summary_compact.setdefault("artifacts", {})["shadow_skip_diagnostics_json"] = shadow_skip_diagnostics.get("artifacts", {}).get("shadow_skip_diagnostics_json")

    daily_payload = {
        "timestamp": stamp,
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "resolution_date": args.resolution_date,
        "input_json": str(input_path),
        "operator_refresh": refresh_compact,
        "account_summary": summary_compact,
        "paper_monitor": monitor_compact,
        "paper_watchlist": paper_watchlist_compact,
        "artifacts": {
            "operator_refresh_json": str(refresh_path),
            "account_summary_json": str(account_summary_path),
            "paper_monitor_json": str(paper_monitor_path),
            "paper_watchlist_json": str(paper_watchlist_path),
            "paper_watchlist_csv": str(paper_watchlist_csv),
            "paper_watchlist_md": str(paper_watchlist_md),
            "daily_json": str(daily_json_path),
            "daily_md": str(daily_md_path),
        },
    }
    write_json(daily_json_path, daily_payload)
    daily_md_path.parent.mkdir(parents=True, exist_ok=True)
    daily_md_path.write_text(
        render_daily_markdown(
            stamp=stamp,
            refresh_path=refresh_path,
            account_summary_path=account_summary_path,
            paper_monitor_path=paper_monitor_path,
            paper_watchlist_path=paper_watchlist_path,
            paper_watchlist_md=paper_watchlist_md,
            daily_json_path=daily_json_path,
        ),
        encoding="utf-8",
    )

    account_summary = load_json(account_summary_path)
    rollup = account_summary.get("daily_operator_rollup", {}) if isinstance(account_summary, dict) else {}
    print(json.dumps({
        "ok": True,
        "paper_only": True,
        "live_order_allowed": False,
        "status": "READY" if rollup.get("live_ready") else "NOT_READY",
        "live_ready_count": rollup.get("live_ready_count", 0),
        "watchlist_count": rollup.get("watchlist_count", 0),
        "daily_json": str(daily_json_path),
        "daily_md": str(daily_md_path),
        "artifacts": daily_payload["artifacts"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
