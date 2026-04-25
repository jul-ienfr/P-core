from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from weather_pm.decision import build_decision
from weather_pm.event_surface import build_weather_event_surface
from weather_pm.execution_features import build_execution_features
from weather_pm.forecast_client import build_forecast_bundle
from weather_pm.history_client import StationHistoryClient, build_station_history_bundle
from weather_pm.market_parser import parse_market_question
from weather_pm.models import ForecastBundle, StationHistoryPoint
from weather_pm.neighbor_context import build_neighbor_context
from weather_pm.operator_summary import write_profitable_accounts_operator_summary
from weather_pm.pipeline import score_market_from_question
from weather_pm.polymarket_client import get_event_book_by_id, get_market_by_id, list_weather_markets, normalize_market_record
from weather_pm.probability_model import build_model_output
from weather_pm.resolution_monitor import write_paper_resolution_monitor
from weather_pm.resolution_parser import parse_resolution_metadata
from weather_pm.scoring import score_market
from weather_pm.source_routing import build_resolution_source_route
from weather_pm.strategy_extractor import extract_weather_strategy_rules
from weather_pm.strategy_shortlist import build_operator_shortlist_report, build_strategy_shortlist
from weather_pm.traders import WeatherTrader, build_weather_trader_registry, load_weather_traders, reverse_engineer_weather_traders


_VALID_SOURCES = ("fixture", "live")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weather-pm", description="Polymarket weather MVP CLI")
    subparsers = parser.add_subparsers(dest="command")

    fetch_markets = subparsers.add_parser("fetch-markets", help="Fetch weather markets from Polymarket")
    fetch_markets.add_argument("--source", choices=_VALID_SOURCES, default="fixture", help="Market source")
    fetch_markets.add_argument("--limit", required=False, type=int, default=100, help="Maximum markets to fetch")

    fetch_event_book = subparsers.add_parser("fetch-event-book", help="Fetch a weather event with child market books")
    fetch_event_book.add_argument("--market-id", required=False, help="Event id to fetch")
    fetch_event_book.add_argument("--source", choices=_VALID_SOURCES, default="fixture", help="Market source")

    parse_market = subparsers.add_parser("parse-market", help="Parse a weather market question")
    parse_market.add_argument("--question", required=False, help="Market question to parse")

    score_market_parser = subparsers.add_parser("score-market", help="Score a weather market question")
    score_market_parser.add_argument("--question", required=False, help="Market question to score")
    score_market_parser.add_argument("--market-id", required=False, help="Market id to score")
    score_market_parser.add_argument("--source", choices=_VALID_SOURCES, default="fixture", help="Market source")
    score_market_parser.add_argument("--yes-price", required=False, type=float, help="Current yes price")
    score_market_parser.add_argument("--resolution-source", required=False, help="Resolution source text")
    score_market_parser.add_argument("--description", required=False, help="Resolution description text")
    score_market_parser.add_argument("--rules", required=False, help="Resolution rules text")
    score_market_parser.add_argument("--max-impact-bps", required=False, type=float, help="Override max executable price impact in bps")

    station_history = subparsers.add_parser("station-history", help="Fetch direct observed history from a market's resolution station")
    station_history.add_argument("--market-id", required=True, help="Market id whose resolution station should be followed")
    station_history.add_argument("--source", choices=_VALID_SOURCES, default="live", help="Market source")
    station_history.add_argument("--start-date", required=True, help="Start date YYYY-MM-DD")
    station_history.add_argument("--end-date", required=True, help="End date YYYY-MM-DD")

    station_latest = subparsers.add_parser("station-latest", help="Fetch latest direct observation from a market's resolution station")
    station_latest.add_argument("--market-id", required=True, help="Market id whose latest resolution station observation should be followed")
    station_latest.add_argument("--source", choices=_VALID_SOURCES, default="live", help="Market source")

    resolution_status = subparsers.add_parser("resolution-status", help="Check provisional latest vs official final resolution status")
    resolution_status.add_argument("--market-id", required=True, help="Market id whose resolution status should be checked")
    resolution_status.add_argument("--source", choices=_VALID_SOURCES, default="live", help="Market source")
    resolution_status.add_argument("--date", required=True, help="Settlement date YYYY-MM-DD")

    monitor_resolution = subparsers.add_parser("monitor-paper-resolution", help="Persist paper-only resolution monitor artifacts for a weather market")
    monitor_resolution.add_argument("--market-id", required=True, help="Market id whose paper resolution should be monitored")
    monitor_resolution.add_argument("--source", choices=_VALID_SOURCES, default="live", help="Market source")
    monitor_resolution.add_argument("--date", required=True, help="Settlement date YYYY-MM-DD")
    monitor_resolution.add_argument("--paper-side", required=True, choices=("yes", "no"), help="Paper trade side")
    monitor_resolution.add_argument("--paper-notional-usd", required=False, type=float, help="Paper notional in USD")
    monitor_resolution.add_argument("--paper-shares", required=False, type=float, help="Paper shares/contracts")
    monitor_resolution.add_argument("--output-dir", required=False, default="/home/jul/prediction_core/data/polymarket", help="Directory for raw status JSON and operator markdown")

    price_market = subparsers.add_parser("price-market", help="Produce a theoretical price for a market")
    price_market.add_argument("--market-id", required=False, help="Market identifier")

    import_traders = subparsers.add_parser("import-weather-traders", help="Import classified weather trader leaderboard data")
    import_traders.add_argument("--classified-csv", required=True, help="Classified Polymarket weather leaderboard CSV")
    import_traders.add_argument("--registry-out", required=True, help="Output JSON registry path")
    import_traders.add_argument("--reverse-engineering-out", required=True, help="Output JSON reverse-engineering report path")
    import_traders.add_argument("--min-pnl", required=False, type=float, default=0.0, help="Minimum weather PnL for reverse engineering report")

    strategy_report = subparsers.add_parser("strategy-report", help="Extract reusable weather strategy rules from a reverse-engineering report")
    strategy_report.add_argument("--reverse-engineering-json", required=True, help="Reverse-engineering JSON produced by import-weather-traders")

    strategy_shortlist = subparsers.add_parser("strategy-shortlist", help="Rank paper-cycle opportunities using profitable weather trader strategies and event-surface anomalies")
    strategy_shortlist.add_argument("--strategy-report-json", required=True, help="Strategy report JSON produced by strategy-report")
    strategy_shortlist.add_argument("--opportunity-report-json", required=True, help="Compact opportunity report JSON produced by paper-cycle-report")
    strategy_shortlist.add_argument("--event-surface-json", required=False, help="Optional event surface JSON produced by event-surface tooling")
    strategy_shortlist.add_argument("--limit", required=False, type=int, default=25, help="Maximum shortlisted opportunities")

    operator_shortlist = subparsers.add_parser("operator-shortlist", help="Compress a saved strategy shortlist into an operator action report")
    operator_shortlist.add_argument("--shortlist-json", required=True, help="Full or compact strategy shortlist JSON")
    operator_shortlist.add_argument("--limit", required=False, type=int, default=10, help="Maximum watchlist rows to include")
    operator_shortlist.add_argument("--output-json", required=False, help="Optional path to write the refreshed operator action report")

    profitable_operator_summary = subparsers.add_parser(
        "profitable-accounts-operator-summary",
        help="Bridge classified profitable weather accounts with a live operator shortlist report",
    )
    profitable_operator_summary.add_argument("--classified-csv", required=True, help="Classified profitable weather accounts CSV")
    profitable_operator_summary.add_argument("--reverse-engineering-json", required=True, help="Reverse-engineering JSON produced by import-weather-traders")
    profitable_operator_summary.add_argument("--operator-report-json", required=True, help="Operator shortlist report JSON")
    profitable_operator_summary.add_argument("--output-json", required=True, help="Output compact operator summary JSON")
    profitable_operator_summary.add_argument("--priority-limit", required=False, type=int, default=10, help="Maximum priority accounts to include")

    operator_refresh = subparsers.add_parser("operator-refresh", help="Refresh a saved weather shortlist/operator report with paper-only live resolution status")
    operator_refresh.add_argument("--input-json", required=True, help="Saved strategy shortlist or operator refresh JSON")
    operator_refresh.add_argument("--source", choices=_VALID_SOURCES, default="live", help="Market source")
    operator_refresh.add_argument("--resolution-date", required=True, help="Fallback settlement date YYYY-MM-DD")
    operator_refresh.add_argument("--operator-limit", required=False, type=int, default=10, help="Maximum watchlist rows to include")
    operator_refresh.add_argument("--skip-orderbook", action="store_true", help="Reserved: do not refresh execution/orderbook state")
    operator_refresh.add_argument("--output-json", required=False, help="Optional path to write the full paper-only refresh wrapper")

    event_surface = subparsers.add_parser("event-surface", help="Build city/date weather event surfaces and flag threshold/bin anomalies")
    event_surface.add_argument("--markets-json", required=True, help="JSON file containing either a markets list or an object with markets/opportunities")
    event_surface.add_argument("--exact-mass-tolerance", required=False, type=float, default=1.0, help="Maximum acceptable exact-bin YES price mass")
    event_surface.add_argument("--output-json", required=False, help="Optional path to write the full event surface report")

    strategy_shortlist_report = subparsers.add_parser("strategy-shortlist-report", help="Build strategy report, paper opportunity report, event surface, and ranked shortlist in one command")
    strategy_shortlist_report.add_argument("--reverse-engineering-json", required=True, help="Reverse-engineering JSON produced by import-weather-traders")
    strategy_shortlist_report.add_argument("--run-id", required=True, help="Paper cycle run id")
    strategy_shortlist_report.add_argument("--source", choices=_VALID_SOURCES, default="fixture", help="Market source")
    strategy_shortlist_report.add_argument("--limit", required=False, type=int, default=25, help="Maximum markets/opportunities to inspect")
    strategy_shortlist_report.add_argument("--requested-quantity", required=False, type=float, default=1.0, help="Requested quantity per tradeable market")
    strategy_shortlist_report.add_argument("--include-skipped", action="store_true", help="Include skipped/watchlist diagnostics in the opportunity report")
    strategy_shortlist_report.add_argument("--tradeable-only", action="store_true", help="Only include trade/trade_small opportunities before shortlisting")
    strategy_shortlist_report.add_argument("--min-edge", required=False, type=float, help="Minimum probability edge to include in the opportunity report")
    strategy_shortlist_report.add_argument("--max-cost-bps", required=False, type=float, help="Maximum all-in execution cost in basis points")
    strategy_shortlist_report.add_argument("--min-depth-usd", required=False, type=float, help="Minimum order book depth in USD")
    strategy_shortlist_report.add_argument("--event-surface-json", required=False, help="Optional prebuilt event surface JSON to reuse instead of deriving one from opportunities")
    strategy_shortlist_report.add_argument("--operator-limit", required=False, type=int, help="Embed a compact operator action snapshot limited to this many rows")
    strategy_shortlist_report.add_argument("--resolution-date", required=False, help="Reference settlement date YYYY-MM-DD for enriching shortlist rows with resolution status")
    strategy_shortlist_report.add_argument("--output-json", required=False, help="Optional path to write the combined shortlist report")

    paper_cycle = subparsers.add_parser("paper-cycle", help="Run one paper trading cycle")
    _add_paper_cycle_arguments(paper_cycle)

    paper_cycle_report = subparsers.add_parser("paper-cycle-report", help="Run a paper cycle and output compact ranked opportunities")
    _add_paper_cycle_arguments(paper_cycle_report)
    paper_cycle_report.add_argument("--tradeable-only", action="store_true", help="Only output candidates with a trade/trade_small decision")
    paper_cycle_report.add_argument("--include-skipped", action="store_true", help="Include skipped/watchlist diagnostics in addition to tradeable candidates")
    paper_cycle_report.add_argument("--min-edge", required=False, type=float, help="Minimum probability edge to include in the report")
    paper_cycle_report.add_argument("--max-cost-bps", required=False, type=float, help="Maximum all-in execution cost in basis points")
    paper_cycle_report.add_argument("--min-depth-usd", required=False, type=float, help="Minimum order book depth in USD")
    return parser


def _add_paper_cycle_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True, help="Paper cycle run id")
    parser.add_argument("--source", choices=_VALID_SOURCES, default="live", help="Market source")
    parser.add_argument("--limit", required=False, type=int, default=25, help="Maximum live markets to score")
    parser.add_argument("--bankroll-usd", required=False, type=float, help="Bankroll used for decision sizing")
    parser.add_argument("--requested-quantity", required=False, type=float, default=1.0, help="Requested quantity per tradeable market")
    parser.add_argument("--max-impact-bps", required=False, type=float, help="Override max executable price impact in bps")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "fetch-markets":
        markets = [normalize_market_record(market) for market in list_weather_markets(source=args.source, limit=args.limit)]
        print(json.dumps(markets))
        return 0

    if args.command == "fetch-event-book":
        if not args.market_id:
            parser.error("fetch-event-book requires --market-id")
        print(json.dumps(_normalize_event_book_payload(get_event_book_by_id(args.market_id, source=args.source))))
        return 0

    if args.command == "parse-market":
        if not args.question:
            parser.error("parse-market requires --question")
        print(json.dumps(parse_market_question(args.question).to_dict()))
        return 0

    if args.command == "score-market":
        if args.market_id:
            print(json.dumps(_score_market_from_market_id(args.market_id, source=args.source, max_impact_bps=args.max_impact_bps)))
            return 0
        if not args.question:
            parser.error("score-market requires --question or --market-id")
        if args.yes_price is None:
            parser.error("score-market requires --yes-price when using --question")
        print(
            json.dumps(
                score_market_from_question(
                    args.question,
                    args.yes_price,
                    resolution_source=args.resolution_source,
                    description=args.description,
                    rules=args.rules,
                    max_impact_bps=args.max_impact_bps,
                    infer_default_resolution=True,
                )
            )
        )
        return 0

    if args.command == "station-history":
        print(json.dumps(station_history_for_market_id(args.market_id, source=args.source, start_date=args.start_date, end_date=args.end_date)))
        return 0

    if args.command == "station-latest":
        print(json.dumps(station_latest_for_market_id(args.market_id, source=args.source)))
        return 0

    if args.command == "resolution-status":
        print(json.dumps(resolution_status_for_market_id(args.market_id, source=args.source, date=args.date)))
        return 0

    if args.command == "monitor-paper-resolution":
        print(
            json.dumps(
                write_paper_resolution_monitor(
                    market_id=args.market_id,
                    source=args.source,
                    settlement_date=args.date,
                    paper_side=args.paper_side,
                    paper_notional_usd=args.paper_notional_usd,
                    paper_shares=args.paper_shares,
                    output_dir=args.output_dir,
                )
            )
        )
        return 0

    if args.command == "import-weather-traders":
        print(json.dumps(import_weather_traders(args.classified_csv, args.registry_out, args.reverse_engineering_out, min_pnl=args.min_pnl)))
        return 0

    if args.command == "strategy-report":
        print(json.dumps(strategy_report(args.reverse_engineering_json)))
        return 0

    if args.command == "event-surface":
        payload = event_surface_report(args.markets_json, exact_mass_tolerance=args.exact_mass_tolerance)
        output_payload = payload
        if args.output_json:
            output_path = Path(args.output_json)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            payload.setdefault("artifacts", {})["source_markets_json"] = str(args.markets_json)
            payload.setdefault("artifacts", {})["output_json"] = str(output_path)
            output_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
            output_payload = compact_event_surface_report(payload)
        print(json.dumps(output_payload))
        return 0

    if args.command == "strategy-shortlist":
        print(
            json.dumps(
                strategy_shortlist_report(
                    args.strategy_report_json,
                    args.opportunity_report_json,
                    event_surface_json=args.event_surface_json,
                    limit=args.limit,
                )
            )
        )
        return 0

    if args.command == "operator-shortlist":
        payload = json.loads(Path(args.shortlist_json).read_text())
        if not isinstance(payload, dict):
            raise ValueError("shortlist JSON must be an object")
        report = build_operator_shortlist_report(payload, limit=args.limit)
        if args.output_json:
            output_path = Path(args.output_json)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            report.setdefault("artifacts", {})["output_json"] = str(output_path)
            output_path.write_text(json.dumps(report, indent=2, sort_keys=True))
        print(json.dumps(report))
        return 0

    if args.command == "profitable-accounts-operator-summary":
        print(
            json.dumps(
                write_profitable_accounts_operator_summary(
                    classified_accounts_csv=args.classified_csv,
                    reverse_engineering_json=args.reverse_engineering_json,
                    operator_report_json=args.operator_report_json,
                    output_json=args.output_json,
                    priority_limit=args.priority_limit,
                )
            )
        )
        return 0

    if args.command == "operator-refresh":
        payload = json.loads(Path(args.input_json).read_text())
        if not isinstance(payload, dict):
            raise ValueError("operator refresh input JSON must be an object")
        report = build_operator_refresh_report(
            payload,
            source=args.source,
            resolution_date=args.resolution_date,
            operator_limit=args.operator_limit,
            source_input_json=str(args.input_json),
        )
        output_payload = compact_operator_refresh_report(report)
        if args.output_json:
            output_path = Path(args.output_json)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            report.setdefault("artifacts", {})["output_json"] = str(output_path)
            output_path.write_text(json.dumps(report, indent=2, sort_keys=True))
            output_payload = compact_operator_refresh_report(report)
        print(json.dumps(output_payload))
        return 0

    if args.command == "strategy-shortlist-report":
        payload = build_strategy_shortlist_report_from_args(args)
        output_payload = payload
        if args.output_json:
            output_path = Path(args.output_json)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            payload.setdefault("artifacts", {})["output_json"] = str(output_path)
            output_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
            output_payload = compact_strategy_shortlist_report(payload)
        print(json.dumps(output_payload))
        return 0

    if args.command == "paper-cycle":
        from prediction_core.server import live_paper_cycle_request

        print(json.dumps(live_paper_cycle_request(_paper_cycle_payload_from_args(args))))
        return 0

    if args.command == "paper-cycle-report":
        from prediction_core.server import paper_cycle_opportunity_report_request

        print(json.dumps(paper_cycle_opportunity_report_request(_paper_cycle_payload_from_args(args))))
        return 0

    return 0


def import_weather_traders(
    classified_csv: str | Path,
    registry_out: str | Path,
    reverse_engineering_out: str | Path,
    *,
    min_pnl: float = 0.0,
) -> dict[str, Any]:
    traders = load_weather_traders(classified_csv)
    registry = build_weather_trader_registry(traders)
    report = reverse_engineer_weather_traders(traders, min_pnl_usd=min_pnl)
    registry_path = Path(registry_out)
    report_path = Path(reverse_engineering_out)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True))
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    return {
        "registry_path": str(registry_path),
        "reverse_engineering_path": str(report_path),
        "total_accounts": report["total_accounts"],
        "weather_heavy_count": report["weather_heavy_count"],
    }


def strategy_report(reverse_engineering_json: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(reverse_engineering_json).read_text())
    accounts = payload.get("accounts") if isinstance(payload, dict) else None
    if not isinstance(accounts, list):
        raise ValueError("reverse engineering JSON must contain an accounts list")
    traders = [_weather_trader_from_report_account(account) for account in accounts if isinstance(account, dict)]
    return extract_weather_strategy_rules(traders)


def strategy_shortlist_report(
    strategy_report_json: str | Path,
    opportunity_report_json: str | Path,
    *,
    event_surface_json: str | Path | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    strategy_payload = json.loads(Path(strategy_report_json).read_text())
    opportunity_payload = json.loads(Path(opportunity_report_json).read_text())
    surface_payload = json.loads(Path(event_surface_json).read_text()) if event_surface_json else {"events": []}
    if not isinstance(strategy_payload, dict):
        raise ValueError("strategy report JSON must be an object")
    if not isinstance(opportunity_payload, dict):
        raise ValueError("opportunity report JSON must be an object")
    if not isinstance(surface_payload, dict):
        raise ValueError("event surface JSON must be an object")
    return build_strategy_shortlist(strategy_payload, opportunity_payload, surface_payload, limit=limit)


def event_surface_report(markets_json: str | Path, *, exact_mass_tolerance: float = 1.0) -> dict[str, Any]:
    payload = json.loads(Path(markets_json).read_text())
    if isinstance(payload, list):
        markets = payload
    elif isinstance(payload, dict):
        candidate = payload.get("markets") if "markets" in payload else payload.get("opportunities")
        markets = candidate if isinstance(candidate, list) else []
    else:
        markets = []
    report = build_weather_event_surface([market for market in markets if isinstance(market, dict)], exact_mass_tolerance=exact_mass_tolerance)
    report["artifacts"] = {"source_markets_json": str(markets_json)}
    return report


def compact_event_surface_report(payload: dict[str, Any]) -> dict[str, Any]:
    events = payload.get("events", [])
    event_list = events if isinstance(events, list) else []
    market_count = 0
    for event in event_list:
        if isinstance(event, dict):
            markets = event.get("markets", [])
            if isinstance(markets, list):
                market_count += len(markets)
            else:
                market_count += int(event.get("market_count") or 0)
    return {
        "event_count": int(payload.get("event_count") or len(event_list)),
        "events_with_inconsistencies": sum(
            1 for event in event_list if isinstance(event, dict) and event.get("inconsistencies")
        ),
        "market_count": market_count,
        "artifacts": {"output_json": payload.get("artifacts", {}).get("output_json")},
    }


def compact_strategy_shortlist_report(payload: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "summary": payload.get("summary", {}),
        "shortlist": payload.get("shortlist", []),
        "run_id": payload.get("run_id"),
        "source": payload.get("source"),
        "artifacts": payload.get("artifacts", {}),
    }
    if "operator" in payload:
        compact["operator"] = payload.get("operator")
    return compact


def compact_operator_refresh_report(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": payload.get("summary", {}),
        "operator": payload.get("operator", {}),
        "artifacts": payload.get("artifacts", {}),
    }


def build_operator_refresh_report(
    payload: dict[str, Any],
    *,
    source: str,
    resolution_date: str,
    operator_limit: int = 10,
    source_input_json: str | None = None,
) -> dict[str, Any]:
    shortlist_payload = _operator_refresh_shortlist_payload(payload)
    enrich_shortlist_with_resolution_status(shortlist_payload, source=source, date=resolution_date)
    operator = build_operator_shortlist_report(shortlist_payload, limit=operator_limit)
    artifacts = {"source_operator_refresh_input": source_input_json}
    return {
        "summary": {
            "paper_only": True,
            "input_kind": _operator_refresh_input_kind(payload),
            "rows": len(shortlist_payload.get("shortlist", [])),
            "resolution_status_refreshed": _resolution_status_refreshed_count(shortlist_payload),
            "operator_watchlist_rows": len(operator.get("watchlist", [])),
        },
        "shortlist": shortlist_payload.get("shortlist", []),
        "operator": operator,
        "artifacts": artifacts,
    }


def _operator_refresh_shortlist_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("operator"), dict) and isinstance(payload.get("shortlist"), list):
        return {**payload, "shortlist": [dict(row) for row in payload.get("shortlist", []) if isinstance(row, dict)]}
    if isinstance(payload.get("shortlist"), list):
        return {**payload, "shortlist": [dict(row) for row in payload.get("shortlist", []) if isinstance(row, dict)]}
    if isinstance(payload.get("watchlist"), list):
        return {
            "run_id": payload.get("run_id"),
            "source": payload.get("source"),
            "summary": payload.get("summary", {}),
            "artifacts": payload.get("artifacts", {}),
            "shortlist": [_shortlist_row_from_operator_watch_row(row) for row in payload.get("watchlist", []) if isinstance(row, dict)],
        }
    raise ValueError("operator refresh input must contain a shortlist or watchlist")


def _operator_refresh_input_kind(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("operator"), dict) and isinstance(payload.get("shortlist"), list):
        return "refresh_wrapper"
    if isinstance(payload.get("shortlist"), list):
        return "shortlist"
    if isinstance(payload.get("watchlist"), list):
        return "operator"
    return "unknown"


def _shortlist_row_from_operator_watch_row(row: dict[str, Any]) -> dict[str, Any]:
    status = row.get("resolution_status") if isinstance(row.get("resolution_status"), dict) else {}
    return {
        "rank": row.get("rank"),
        "market_id": row.get("market_id"),
        "city": row.get("city"),
        "date": row.get("date"),
        "action": row.get("action"),
        "decision_status": row.get("decision_status"),
        "probability_edge": row.get("edge"),
        "all_in_cost_bps": row.get("all_in_cost_bps"),
        "order_book_depth_usd": row.get("depth_usd"),
        "matched_traders": list(row.get("matched_traders") or []),
        "surface_inconsistency_types": list(row.get("anomalies") or []),
        "execution_blocker": row.get("blocker"),
        "next_actions": list(row.get("next") or []),
        "source_polling_focus": row.get("polling_focus"),
        "source_latest_url": row.get("source_latest_url"),
        "source_latency_tier": row.get("latency_tier"),
        "source_latency_priority": row.get("latency_priority"),
        "resolution_status_date": status.get("date"),
        "resolution_status": {key: value for key, value in status.items() if key not in {"date", "latency"}},
        "resolution_latency": status.get("latency"),
        **_parse_direct_source_label(row.get("direct_source")),
    }


def _parse_direct_source_label(value: Any) -> dict[str, Any]:
    if not value:
        return {"source_direct": False}
    label = str(value)
    provider, _, station = label.partition(":")
    return {"source_direct": True, "source_provider": provider or None, "source_station_code": station or None}


def _resolution_status_refreshed_count(payload: dict[str, Any]) -> int:
    return sum(1 for row in payload.get("shortlist", []) if isinstance(row, dict) and row.get("resolution_status"))


def enrich_shortlist_with_resolution_status(report: dict[str, Any], *, source: str, date: str) -> dict[str, Any]:
    """Attach per-market resolution status while preserving each market's settlement date."""
    for row in [item for item in report.get("shortlist", []) if isinstance(item, dict)]:
        market_id = str(row.get("market_id") or "")
        if not market_id:
            continue
        status_date = _resolution_status_date_for_row(row, fallback_date=date)
        status = resolution_status_for_market_id(market_id, source=source, date=status_date)
        row["resolution_status_date"] = status_date
        row["resolution_status"] = _compact_resolution_status(status)
        row["resolution_latency"] = status.get("latency")
        route = status.get("source_route") if isinstance(status.get("source_route"), dict) else {}
        _copy_source_route_to_row(row, route)
    return report


def _compact_resolution_status(status: dict[str, Any]) -> dict[str, Any]:
    return {
        key: status.get(key)
        for key in (
            "latest_direct",
            "official_daily_extract",
            "provisional_outcome",
            "confirmed_outcome",
            "action_operator",
        )
        if key in status
    }


def _copy_source_route_to_row(row: dict[str, Any], route: dict[str, Any]) -> None:
    if not route:
        return
    mapping = {
        "direct": "source_direct",
        "provider": "source_provider",
        "station_code": "source_station_code",
        "latency_tier": "source_latency_tier",
        "latency_priority": "source_latency_priority",
        "polling_focus": "source_polling_focus",
        "latest_url": "source_latest_url",
        "history_url": "source_history_url",
    }
    for source_key, row_key in mapping.items():
        if source_key in route:
            row[row_key] = route[source_key]


def _resolution_status_date_for_row(row: dict[str, Any], *, fallback_date: str) -> str:
    row_date = str(row.get("date") or "").strip()
    if not row_date:
        return fallback_date
    year = _year_from_iso_date(fallback_date)
    if year is None:
        return fallback_date
    parsed = _parse_month_day(row_date, year=year)
    return parsed or fallback_date


def _year_from_iso_date(raw_value: str) -> int | None:
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").year
    except ValueError:
        return None


def _parse_month_day(raw_value: str, *, year: int) -> str | None:
    for fmt in ("%B %d", "%b %d"):
        try:
            parsed = datetime.strptime(raw_value, fmt)
            return f"{year:04d}-{parsed.month:02d}-{parsed.day:02d}"
        except ValueError:
            continue
    return None


def build_strategy_shortlist_report_from_args(args: argparse.Namespace) -> dict[str, Any]:
    from prediction_core.server import paper_cycle_opportunity_report_request

    strategy_payload = strategy_report(args.reverse_engineering_json)
    opportunity_payload = paper_cycle_opportunity_report_request(
        {
            "run_id": args.run_id,
            "source": args.source,
            "limit": args.limit,
            "requested_quantity": args.requested_quantity,
            "include_skipped": bool(args.include_skipped),
            "tradeable_only": bool(args.tradeable_only),
            **({"min_edge": args.min_edge} if args.min_edge is not None else {}),
            **({"max_cost_bps": args.max_cost_bps} if args.max_cost_bps is not None else {}),
            **({"min_depth_usd": args.min_depth_usd} if args.min_depth_usd is not None else {}),
        }
    )
    if getattr(args, "event_surface_json", None):
        surface_payload = json.loads(Path(args.event_surface_json).read_text())
        if not isinstance(surface_payload, dict):
            raise ValueError("event surface JSON must be an object")
        surface_payload.setdefault("artifacts", {})["source_event_surface_json"] = str(args.event_surface_json)
    else:
        surface_payload = build_weather_event_surface(opportunity_payload.get("opportunities", []))
    shortlist_payload = build_strategy_shortlist(strategy_payload, opportunity_payload, surface_payload, limit=args.limit)
    artifacts: dict[str, Any] = {
        "reverse_engineering_json": str(args.reverse_engineering_json),
        "generated_reports": ["strategy_report", "opportunity_report", "event_surface", "shortlist"],
    }
    report = {
        **shortlist_payload,
        "run_id": args.run_id,
        "source": args.source,
        "artifacts": artifacts,
        "strategy_report": strategy_payload,
        "opportunity_report": opportunity_payload,
        "event_surface": surface_payload,
    }
    if getattr(args, "resolution_date", None):
        artifacts["generated_reports"].append("resolution_status")
        enrich_shortlist_with_resolution_status(report, source=args.source, date=args.resolution_date)
    if getattr(args, "operator_limit", None) is not None:
        artifacts["generated_reports"].append("operator")
        report["operator"] = build_operator_shortlist_report(report, limit=args.operator_limit)
    return report


def _weather_trader_from_report_account(account: dict[str, Any]) -> WeatherTrader:
    return WeatherTrader(
        rank=int(account.get("rank") or 0),
        handle=str(account.get("handle") or ""),
        wallet=str(account.get("wallet") or ""),
        weather_pnl_usd=float(account.get("weather_pnl_usd") or 0.0),
        weather_volume_usd=float(account.get("weather_volume_usd") or 0.0),
        pnl_over_volume_pct=float(account.get("pnl_over_volume_pct") or 0.0),
        classification=str(account.get("classification") or ""),
        confidence=str(account.get("confidence") or ""),
        active_positions=int(account.get("active_positions") or 0),
        active_weather_positions=int(account.get("active_weather_positions") or 0),
        active_nonweather_positions=int(account.get("active_nonweather_positions") or 0),
        recent_activity=int(account.get("recent_activity") or 0),
        recent_weather_activity=int(account.get("recent_weather_activity") or 0),
        recent_nonweather_activity=int(account.get("recent_nonweather_activity") or 0),
        sample_weather_titles=[str(title) for title in account.get("sample_weather_titles") or []],
        sample_nonweather_titles=[str(title) for title in account.get("sample_nonweather_titles") or []],
        profile_url=str(account.get("profile_url") or ""),
    )


def _paper_cycle_payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "run_id": args.run_id,
        "source": args.source,
        "limit": args.limit,
        "bankroll_usd": args.bankroll_usd,
        "requested_quantity": args.requested_quantity,
        "max_impact_bps": args.max_impact_bps,
        "tradeable_only": getattr(args, "tradeable_only", False),
        "include_skipped": getattr(args, "include_skipped", False),
        "min_edge": getattr(args, "min_edge", None),
        "max_cost_bps": getattr(args, "max_cost_bps", None),
        "min_depth_usd": getattr(args, "min_depth_usd", None),
    }
    return {key: value for key, value in payload.items() if value is not None}


def station_history_for_market_id(
    market_id: str,
    *,
    source: str = "live",
    start_date: str,
    end_date: str,
    client: Any | None = None,
) -> dict[str, Any]:
    if source not in _VALID_SOURCES:
        raise ValueError("source must be 'fixture' or 'live'")
    raw_market = dict(get_market_by_id(market_id, source=source))
    structure = parse_market_question(str(raw_market["question"]))
    resolution = parse_resolution_metadata(
        resolution_source=raw_market.get("resolution_source"),
        description=raw_market.get("description"),
        rules=raw_market.get("rules"),
    )
    history = build_station_history_bundle(
        structure,
        resolution,
        start_date=start_date,
        end_date=end_date,
        client=client,
    )
    route = build_resolution_source_route(structure, resolution, start_date=start_date, end_date=end_date)
    return {
        "market_id": market_id,
        "source": source,
        "market": structure.to_dict(),
        "resolution": resolution.to_dict(),
        "source_route": route.to_dict(),
        "history": history.to_dict(),
        "latency": history.latency_diagnostics(),
    }


def station_latest_for_market_id(
    market_id: str,
    *,
    source: str = "live",
    client: Any | None = None,
) -> dict[str, Any]:
    if source not in _VALID_SOURCES:
        raise ValueError("source must be 'fixture' or 'live'")
    raw_market = dict(get_market_by_id(market_id, source=source))
    structure = parse_market_question(str(raw_market["question"]))
    resolution = parse_resolution_metadata(
        resolution_source=raw_market.get("resolution_source"),
        description=raw_market.get("description"),
        rules=raw_market.get("rules"),
    )
    latest_client = client or StationHistoryClient()
    try:
        bundle = latest_client.fetch_latest_bundle(structure, resolution)
    except Exception:
        bundle = build_station_history_bundle(structure, resolution, start_date="", end_date="", client=latest_client)
    latest = bundle.latest()
    route = build_resolution_source_route(structure, resolution)
    return {
        "market_id": market_id,
        "source": source,
        "market": structure.to_dict(),
        "resolution": resolution.to_dict(),
        "source_route": route.to_dict(),
        "latest": latest.to_dict() if latest else None,
        "history": bundle.to_dict(),
        "latency": bundle.latency_diagnostics(),
    }



def resolution_status_for_market_id(
    market_id: str,
    *,
    source: str = "live",
    date: str,
    client: Any | None = None,
) -> dict[str, Any]:
    if source not in _VALID_SOURCES:
        raise ValueError("source must be 'fixture' or 'live'")
    raw_market = dict(get_market_by_id(market_id, source=source))
    structure = parse_market_question(str(raw_market["question"]))
    resolution = parse_resolution_metadata(
        resolution_source=raw_market.get("resolution_source"),
        description=raw_market.get("description"),
        rules=raw_market.get("rules"),
    )
    status_client = client or StationHistoryClient()
    latest_bundle = _safe_fetch_latest_status_bundle(structure, resolution, status_client)
    official_bundle = build_station_history_bundle(
        structure,
        resolution,
        start_date=date,
        end_date=date,
        client=status_client,
    )
    latest_bundle = _ensure_status_latency_fields(latest_bundle, polling_focus="hko_current_weather_api" if resolution.provider == "hong_kong_observatory" else None)
    official_bundle = _ensure_status_latency_fields(
        official_bundle,
        polling_focus="hko_official_daily_extract" if resolution.provider == "hong_kong_observatory" else None,
        expected_lag_seconds=86400 if resolution.provider == "hong_kong_observatory" else None,
    )
    latest_point = latest_bundle.latest()
    official_point = official_bundle.latest()
    route = build_resolution_source_route(structure, resolution, start_date=date, end_date=date)
    provisional = _outcome_for_point(structure, latest_point) if latest_point else "pending"
    confirmed = _outcome_for_point(structure, official_point) if official_point else "pending"
    return {
        "market_id": market_id,
        "source": source,
        "date": date,
        "market": structure.to_dict(),
        "resolution": resolution.to_dict(),
        "source_route": route.to_dict(),
        "latest_direct": _status_point_payload(latest_bundle),
        "official_daily_extract": _status_point_payload(official_bundle),
        "provisional_outcome": provisional,
        "confirmed_outcome": confirmed,
        "action_operator": "resolution_confirmed" if confirmed != "pending" else "monitor_until_official_daily_extract",
        "latency": {
            "latest": latest_bundle.latency_diagnostics(),
            "official": official_bundle.latency_diagnostics(),
        },
    }


def _safe_fetch_latest_status_bundle(structure, resolution, client: Any) -> Any:
    try:
        return client.fetch_latest_bundle(structure, resolution)
    except Exception:
        return build_station_history_bundle(structure, resolution, start_date="", end_date="", client=client)


def _ensure_status_latency_fields(bundle: Any, *, polling_focus: str | None = None, expected_lag_seconds: int | None = None) -> Any:
    if polling_focus is not None and getattr(bundle, "polling_focus", None) is None:
        bundle.polling_focus = polling_focus
    if expected_lag_seconds is not None and getattr(bundle, "expected_lag_seconds", None) is None:
        bundle.expected_lag_seconds = expected_lag_seconds
    return bundle


def _status_point_payload(bundle: Any) -> dict[str, Any]:
    point = bundle.latest()
    return {
        "available": point is not None,
        "value": point.value if point else None,
        "timestamp": point.timestamp if point else None,
        "latency_tier": bundle.latency_tier,
    }


def _outcome_for_point(structure, point: StationHistoryPoint) -> str:
    value = point.value
    if structure.is_exact_bin and structure.range_low is not None and structure.range_high is not None:
        return "yes" if structure.range_low <= value < structure.range_high else "no"
    if structure.threshold_direction == "below" and structure.target_value is not None:
        return "yes" if value <= structure.target_value else "no"
    if structure.target_value is not None:
        return "yes" if value >= structure.target_value else "no"
    return "pending"

def _normalize_event_book_payload(event_book: dict[str, Any]) -> dict[str, Any]:
    event = {
        "id": str(event_book.get("id", "")),
        "question": str(event_book.get("question", "")),
        "category": str(event_book.get("category", "unknown")),
        "resolution_source": event_book.get("resolution_source"),
        "description": event_book.get("description"),
        "rules": event_book.get("rules"),
    }
    markets = [normalize_market_record(market) for market in event_book.get("markets", []) if isinstance(market, dict)]
    return {"event": event, "markets": markets}


def _score_market_from_market_id(market_id: str, *, source: str, max_impact_bps: float | None = None) -> dict[str, Any]:
    raw_market = dict(get_market_by_id(market_id, source=source))
    if max_impact_bps is not None:
        raw_market["max_impact_bps"] = max_impact_bps
    structure = parse_market_question(str(raw_market["question"]))
    resolution = parse_resolution_metadata(
        resolution_source=raw_market.get("resolution_source"),
        description=raw_market.get("description"),
        rules=raw_market.get("rules"),
    )
    forecast_bundle = build_forecast_bundle(structure, live=(source == "live"), resolution=resolution)
    model_output = build_model_output(structure, forecast_bundle)
    neighbor_context = build_neighbor_context(structure, list_weather_markets(source=source))
    execution = build_execution_features(raw_market)
    score = score_market(
        structure=structure,
        resolution=resolution,
        forecast_bundle=forecast_bundle,
        model_output=model_output,
        neighbor_context=neighbor_context,
        execution=execution,
        yes_price=float(raw_market.get("yes_price", 0.0)),
    )
    decision = build_decision(
        score=score,
        is_exact_bin=structure.is_exact_bin,
        spread=execution.spread,
        forecast_dispersion=forecast_bundle.dispersion,
        execution=execution,
    )
    model_payload = model_output.to_dict()
    model_payload.update(
        {
            "source_provider": forecast_bundle.source_provider or resolution.provider,
            "source_station_code": forecast_bundle.source_station_code or resolution.station_code,
            "source_url": forecast_bundle.source_url or resolution.source_url,
            "source_latency_tier": forecast_bundle.source_latency_tier if forecast_bundle.source_provider else "resolution_direct_target",
        }
    )
    source_route = build_resolution_source_route(structure, resolution)
    return {
        "market": structure.to_dict(),
        "resolution": resolution.to_dict(),
        "source_route": source_route.to_dict(),
        "model": model_payload,
        "forecast": forecast_bundle.to_dict(),
        "edge": {
            "market_implied_yes_probability": round(float(raw_market.get("yes_price", 0.0)), 2),
            "probability_edge": round(score.raw_edge, 2),
            "theoretical_yes_price": round(model_output.probability_yes, 2),
        },
        "score": score.to_dict(),
        "decision": decision.to_dict(),
        "neighbors": neighbor_context.to_dict(),
        "execution": execution.to_dict(),
    }


if __name__ == "__main__":
    raise SystemExit(main())
