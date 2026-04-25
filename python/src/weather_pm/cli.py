from __future__ import annotations

import argparse
import json
from typing import Any

from weather_pm.decision import build_decision
from weather_pm.execution_features import build_execution_features
from weather_pm.forecast_client import build_forecast_bundle
from weather_pm.market_parser import parse_market_question
from weather_pm.models import ForecastBundle
from weather_pm.neighbor_context import build_neighbor_context
from weather_pm.pipeline import score_market_from_question
from weather_pm.polymarket_client import get_event_book_by_id, get_market_by_id, list_weather_markets, normalize_market_record
from weather_pm.probability_model import build_model_output
from weather_pm.resolution_parser import parse_resolution_metadata
from weather_pm.scoring import score_market


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

    price_market = subparsers.add_parser("price-market", help="Produce a theoretical price for a market")
    price_market.add_argument("--market-id", required=False, help="Market identifier")

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
                )
            )
        )
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
    forecast_bundle = build_forecast_bundle(structure, live=(source == "live"))
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
    return {
        "market": structure.to_dict(),
        "resolution": resolution.to_dict(),
        "model": model_output.to_dict(),
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
