from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any


def build_paper_watchlist_report(payload: dict[str, Any]) -> dict[str, Any]:
    positions = payload.get("positions") if isinstance(payload, dict) else None
    if not isinstance(positions, list):
        raise ValueError("paper monitor JSON must contain a positions list")
    watchlist = []
    for position in positions:
        if not isinstance(position, dict):
            continue
        p_side = position.get("p_side_now", position.get("base_p_side"))
        if p_side is None:
            raise ValueError("paper position must contain p_side_now or base_p_side")
        watchlist.append(
            build_paper_watch_row(
                _normalize_paper_monitor_position(position),
                p_side=float(p_side),
                best_bid=position.get("best_bid_now", position.get("live_best_bid_now", position.get("best_bid"))),
                best_ask=position.get("best_ask_now", position.get("live_best_ask_now", position.get("best_ask"))),
                forecast_c=position.get("current_forecast_max_c", position.get("station_forecast_max_c_now", position.get("station_forecast_max_c"))),
            )
        )
    return {
        "summary": {
            "positions": len(watchlist),
            "total_spend": round(sum(float(row["spend_usdc"]) for row in watchlist), 4),
            "total_ev_now": round(sum(float(row["paper_ev_now_usdc"]) for row in watchlist), 2),
            "total_mtm_bid": round(sum(float(row["paper_mtm_bid_usdc"] or 0.0) for row in watchlist), 2),
            "action_counts": dict(Counter(row["operator_action"] for row in watchlist)),
            "paper_only": True,
        },
        "watchlist": watchlist,
    }


def write_paper_watchlist_report(input_json: str | Path, output_json: str | Path | None = None) -> dict[str, Any]:
    import json

    payload = json.loads(Path(input_json).read_text())
    report = build_paper_watchlist_report(payload)
    if output_json:
        output_path = Path(output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


_CSV_FIELDS = [
    "city",
    "date",
    "station",
    "side",
    "market",
    "spend_usdc",
    "entry_avg",
    "p_side_now",
    "paper_ev_now_usdc",
    "operator_action",
    "hard_stop_if_p_below",
    "trim_review_if_p_below",
    "take_profit_review_if_bid_above",
    "add_allowed",
    "max_add_usdc",
]


def write_paper_watchlist_csv(input_json: str | Path, output_csv: str | Path) -> int:
    import json

    report = json.loads(Path(input_json).read_text())
    if not isinstance(report, dict):
        raise ValueError("paper watchlist JSON must be an object")
    watchlist = report.get("watchlist") if isinstance(report.get("watchlist"), list) else []
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        rows = 0
        for row in watchlist:
            if not isinstance(row, dict):
                continue
            writer.writerow(_paper_watchlist_csv_row(row))
            rows += 1
    return rows


def _paper_watchlist_csv_row(row: dict[str, Any]) -> dict[str, str]:
    return {
        "city": _format_cell(row.get("city")),
        "date": _format_cell(row.get("date")),
        "station": _format_cell(row.get("station")),
        "side": _format_cell(row.get("side")),
        "market": _format_cell(f"{row.get('kind')} {row.get('temp')}°{row.get('unit')}"),
        "spend_usdc": _format_float(row.get("spend_usdc"), 2),
        "entry_avg": _format_float(row.get("entry_avg"), 4),
        "p_side_now": _format_float(row.get("p_side_now"), 4),
        "paper_ev_now_usdc": _format_float(row.get("paper_ev_now_usdc"), 2),
        "operator_action": _format_cell(row.get("operator_action")),
        "hard_stop_if_p_below": _format_float(row.get("hard_stop_if_p_below"), 4),
        "trim_review_if_p_below": _format_float(row.get("trim_review_if_p_below"), 4),
        "take_profit_review_if_bid_above": _format_float(row.get("take_profit_review_if_bid_above"), 4),
        "add_allowed": "true" if row.get("add_allowed") else "false",
        "max_add_usdc": _format_float(row.get("max_add_usdc"), 2),
    }


def write_paper_watchlist_markdown(input_json: str | Path, output_md: str | Path) -> str:
    import json

    report = json.loads(Path(input_json).read_text())
    if not isinstance(report, dict):
        raise ValueError("paper watchlist JSON must be an object")
    markdown = render_paper_watchlist_markdown(report)
    output_path = Path(output_md)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return markdown


def render_paper_watchlist_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    watchlist = report.get("watchlist") if isinstance(report.get("watchlist"), list) else []
    action_counts = summary.get("action_counts") if isinstance(summary.get("action_counts"), dict) else {}
    operator_decision = _paper_watchlist_operator_decision(summary, watchlist)
    lines = [
        "# Polymarket weather paper watchlist",
        "",
        f"Positions: {int(summary.get('positions') or len(watchlist))}",
        f"Spend: {_format_float(summary.get('total_spend'), 2)} USDC",
        f"EV now: {_format_float(summary.get('total_ev_now'), 2)} USDC",
        "Actions: " + ", ".join(f"{key}: {value}" for key, value in sorted(action_counts.items())),
        "",
        "## Operator decision",
        "",
        f"Global action: {operator_decision['global_action']}",
        f"Rationale: {operator_decision['rationale']}",
        f"Top EV: {operator_decision['top_ev']}",
        "",
        "| City | Date | Station | Side | Market | Spend | Entry | P side | EV | Action | Hard stop | Trim review | TP review | Add? |",
        "|---|---|---|---|---|---:|---:|---:|---:|---|---:|---:|---:|---|",
    ]
    for row in watchlist:
        if not isinstance(row, dict):
            continue
        market = f"{row.get('kind')} {row.get('temp')}°{row.get('unit')}"
        lines.append(
            "| "
            + " | ".join(
                [
                    _format_cell(row.get("city")),
                    _format_cell(row.get("date")),
                    _format_cell(row.get("station")),
                    _format_cell(row.get("side")),
                    _format_cell(market),
                    _format_float(row.get("spend_usdc"), 2),
                    _format_float(row.get("entry_avg"), 4),
                    _format_float(row.get("p_side_now"), 4),
                    _format_float(row.get("paper_ev_now_usdc"), 2),
                    _format_cell(row.get("operator_action")),
                    _format_float(row.get("hard_stop_if_p_below"), 4),
                    _format_float(row.get("trim_review_if_p_below"), 4),
                    _format_float(row.get("take_profit_review_if_bid_above"), 4),
                    "yes" if row.get("add_allowed") else "no",
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def paper_watchlist_operator_decision(report: dict[str, Any]) -> dict[str, str]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    watchlist = report.get("watchlist") if isinstance(report.get("watchlist"), list) else []
    return _paper_watchlist_operator_decision(summary, watchlist)


def compact_paper_watchlist_report(
    report: dict[str, Any],
    *,
    output_json: str | Path | None = None,
    output_csv: str | Path | None = None,
    output_md: str | Path | None = None,
) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    watchlist = report.get("watchlist") if isinstance(report.get("watchlist"), list) else []
    decision = paper_watchlist_operator_decision(report)
    artifacts: dict[str, str] = {}
    if output_json:
        artifacts["json"] = str(output_json)
    if output_csv:
        artifacts["csv"] = str(output_csv)
    if output_md:
        artifacts["markdown"] = str(output_md)
    return {
        "positions": int(summary.get("positions") or len(watchlist)),
        "total_spend": round(float(summary.get("total_spend") or 0.0), 2),
        "total_ev_now": round(float(summary.get("total_ev_now") or 0.0), 2),
        "global_action": decision["global_action"],
        "top_ev": decision["top_ev"],
        "add_allowed_count": sum(1 for row in watchlist if isinstance(row, dict) and row.get("add_allowed")),
        "artifacts": artifacts,
    }


def _paper_watchlist_operator_decision(summary: dict[str, Any], watchlist: list[Any]) -> dict[str, str]:
    rows = [row for row in watchlist if isinstance(row, dict)]
    total_ev = float(summary.get("total_ev_now") or 0.0)
    addable = [row for row in rows if row.get("add_allowed")]
    exit_rows = [row for row in rows if row.get("operator_action") == "EXIT_PAPER"]
    if exit_rows:
        global_action = "EXIT_REVIEW"
        rationale = "One or more paper positions crossed hard stop."
    elif addable:
        global_action = "ADD_REVIEW"
        rationale = "At least one paper position allows add under strict cap."
    else:
        global_action = "HOLD"
        rationale = "Positive paper EV, but no add allowed; monitor stops and take-profit reviews."
    if total_ev <= 0 and not addable and not exit_rows:
        rationale = "No positive aggregate paper EV; monitor stops, no add."

    top_row = max(rows, key=lambda row: float(row.get("paper_ev_now_usdc") or 0.0), default=None)
    top_ev = "n/a"
    if top_row:
        market = f"{top_row.get('kind')} {top_row.get('temp')}°{top_row.get('unit')}"
        top_ev = (
            f"{_format_cell(top_row.get('city'))} {_format_cell(top_row.get('date'))} "
            f"{_format_cell(top_row.get('side'))} {_format_cell(market)} "
            f"(+{_format_float(top_row.get('paper_ev_now_usdc'), 2)} USDC)"
        )
    return {"global_action": global_action, "rationale": rationale, "top_ev": top_ev}


def _format_float(value: Any, digits: int) -> str:
    if value is None:
        return ""
    return f"{float(value):.{digits}f}"


def _format_cell(value: Any) -> str:
    return "" if value is None else str(value).replace("|", "\\|")


def _normalize_paper_monitor_position(position: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(position)
    paper_fill = position.get("paper_fill") if isinstance(position.get("paper_fill"), dict) else {}
    if "entry_avg" not in normalized and paper_fill.get("avg_price") is not None:
        normalized["entry_avg"] = paper_fill.get("avg_price")
    if "filled_usdc" not in normalized and paper_fill.get("filled_usdc") is not None:
        normalized["filled_usdc"] = paper_fill.get("filled_usdc")
    if "shares" not in normalized and paper_fill.get("shares") is not None:
        normalized["shares"] = paper_fill.get("shares")
    if "side" not in normalized and normalized.get("best_side") is not None:
        normalized["side"] = normalized.get("best_side")
    return normalized


def build_paper_watch_row(
    position: dict[str, Any],
    *,
    p_side: float,
    best_bid: float | None,
    best_ask: float | None,
    forecast_c: float | None,
) -> dict[str, Any]:
    """Build a deterministic operator watch row for a paper weather position."""
    entry_avg = float(position["entry_avg"])
    filled_usdc = float(position["filled_usdc"])
    shares = float(position["shares"])
    hard_stop = round(max(0.0, entry_avg - 0.03), 4)
    trim_review = round(max(0.0, entry_avg + 0.02), 4)
    take_profit = round(min(0.98, max(entry_avg + 0.12, p_side - 0.02)), 4)

    paper_ev = round(shares * p_side - filled_usdc, 3)
    paper_mtm = round(shares * best_bid - filled_usdc, 3) if best_bid is not None else None

    action = "HOLD_MONITOR"
    reason = "OK"
    if p_side < hard_stop:
        action = "EXIT_PAPER"
        reason = f"p_side {p_side:.4f} < hard_stop {hard_stop:.4f}"
    elif best_bid is not None and best_bid > take_profit:
        action = "TAKE_PROFIT_REVIEW"
        reason = f"bid {best_bid:.4f} > tp_review {take_profit:.4f}"
    elif p_side < trim_review:
        action = "TRIM_REVIEW"
        reason = f"p_side {p_side:.4f} near entry {entry_avg:.4f}"

    concentration_capped = filled_usdc >= 10.0
    if action == "HOLD_MONITOR" and concentration_capped:
        action = "HOLD_CAPPED"
        reason = "large position; no further add"

    add_allowed = (
        action == "HOLD_MONITOR"
        and not concentration_capped
        and best_ask is not None
        and p_side - best_ask > 0.18
    )

    return {
        "city": position.get("city"),
        "date": position.get("date"),
        "station": position.get("station"),
        "side": position.get("side"),
        "temp": position.get("temp"),
        "unit": position.get("unit"),
        "kind": position.get("kind"),
        "spend_usdc": filled_usdc,
        "shares": shares,
        "entry_avg": entry_avg,
        "forecast_c": forecast_c,
        "p_side_now": round(p_side, 4),
        "bid": best_bid,
        "ask": best_ask,
        "paper_ev_now_usdc": paper_ev,
        "paper_mtm_bid_usdc": paper_mtm,
        "operator_action": action,
        "reason": reason,
        "hard_stop_if_p_below": hard_stop,
        "trim_review_if_p_below": trim_review,
        "take_profit_review_if_bid_above": take_profit,
        "add_allowed": add_allowed,
        "max_add_usdc": 5 if add_allowed else 0,
        "add_limit": round(min(best_ask, p_side - 0.15), 4) if add_allowed and best_ask is not None else None,
    }
