from __future__ import annotations

import argparse
import json

from prediction_core.orchestrator import consume_weather_markets, run_weather_paper_batch, run_weather_workflow
from prediction_core.server import build_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prediction-core", description="prediction_core Python service controls")
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="Run the local prediction_core HTTP service")
    serve.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
    serve.add_argument("--port", default=8080, type=int, help="TCP port to bind")

    workflow = subparsers.add_parser(
        "weather-workflow",
        help="Run a thin parse/score/paper workflow against an existing prediction_core server",
    )
    workflow.add_argument("--base-url", default="http://127.0.0.1:8080", help="Base URL for the prediction_core server")
    workflow.add_argument("--question", required=True, help="Weather market question to parse and score")
    workflow.add_argument("--yes-price", required=True, type=float, help="Current yes price")
    workflow.add_argument("--source", choices=("fixture", "live"), default="fixture", help="Market source")
    workflow.add_argument("--run-id", help="Paper cycle run id; requires --market-id")
    workflow.add_argument("--market-id", help="Paper cycle market id; requires --run-id")
    workflow.add_argument("--resolution-source", help="Resolution source text")
    workflow.add_argument("--description", help="Resolution description text")
    workflow.add_argument("--rules", help="Resolution rules text")
    workflow.add_argument("--requested-quantity", type=float, help="Requested quantity for paper cycle")
    workflow.add_argument("--bankroll-usd", type=float, help="Bankroll size to derive requested quantity")
    workflow.add_argument("--filled-quantity", type=float, help="Explicit filled quantity for paper cycle")
    workflow.add_argument("--fill-price", type=float, help="Explicit fill price for paper cycle")
    workflow.add_argument("--reference-price", type=float, help="Explicit reference price for paper cycle")
    workflow.add_argument("--fee-paid", type=float, help="Explicit fee paid for paper cycle")
    workflow.add_argument("--position-side", help="Paper position side")
    workflow.add_argument("--execution-side", help="Paper execution side")
    workflow.add_argument("--best-bid", type=float, help="Best bid for score/execution inputs")
    workflow.add_argument("--best-ask", type=float, help="Best ask for score/execution inputs")
    workflow.add_argument("--volume", type=float, help="Market volume input")
    workflow.add_argument("--volume-usd", type=float, help="Market USD volume input")
    workflow.add_argument("--hours-to-resolution", type=float, help="Hours to resolution input")
    workflow.add_argument("--target-order-size-usd", type=float, help="Target order size input")
    workflow.add_argument("--taker-fee-bps", type=float, help="Taker fee basis points")
    workflow.add_argument("--transaction-fee-bps", type=float, help="Transaction fee basis points")
    workflow.add_argument("--deposit-fee-usd", type=float, help="Deposit fee input")
    workflow.add_argument("--withdrawal-fee-usd", type=float, help="Withdrawal fee input")

    consume = subparsers.add_parser(
        "consume-markets",
        help="Fetch and score weather markets through PredictionCoreClient, then keep only candidates above a minimum decision status",
    )
    consume.add_argument("--base-url", default="http://127.0.0.1:8080", help="Base URL for the prediction_core server")
    consume.add_argument("--source", choices=("fixture", "live"), default="fixture", help="Market source")
    consume.add_argument("--limit", default=20, type=int, help="Maximum number of markets to inspect")
    consume.add_argument(
        "--min-status",
        choices=("skip", "watchlist", "trade_small", "trade"),
        default="watchlist",
        help="Minimum decision status to keep in the output",
    )
    consume.add_argument(
        "--explain-filtered",
        action="store_true",
        help="Include filtered markets with a filter_reason for live-candidate triage",
    )

    paper_batch = subparsers.add_parser(
        "paper-batch",
        help="Fetch/scored weather candidates, then run paper-cycle for selected markets",
    )
    paper_batch.add_argument("--base-url", default="http://127.0.0.1:8080", help="Base URL for the prediction_core server")
    paper_batch.add_argument("--source", choices=("fixture", "live"), default="fixture", help="Market source")
    paper_batch.add_argument("--limit", default=20, type=int, help="Maximum number of markets to inspect")
    paper_batch.add_argument(
        "--min-status",
        choices=("skip", "watchlist", "trade_small", "trade"),
        default="trade_small",
        help="Minimum decision status to paper-trade",
    )
    paper_batch.add_argument("--run-id-prefix", default="weather-paper", help="Run id prefix for generated paper cycles")
    paper_batch.add_argument("--bankroll-usd", type=float, help="Bankroll size to derive requested quantity")
    paper_batch.add_argument("--requested-quantity", type=float, help="Explicit requested quantity for every selected market")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "serve":
        server = build_server(host=args.host, port=args.port)
        print(f"prediction_core server listening on http://{args.host}:{args.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0

    if args.command == "weather-workflow":
        result = run_weather_workflow(
            base_url=args.base_url,
            question=args.question,
            yes_price=args.yes_price,
            run_id=args.run_id,
            market_id=args.market_id,
            source=args.source,
            resolution_source=args.resolution_source,
            description=args.description,
            rules=args.rules,
            requested_quantity=args.requested_quantity,
            bankroll_usd=args.bankroll_usd,
            filled_quantity=args.filled_quantity,
            fill_price=args.fill_price,
            reference_price=args.reference_price,
            fee_paid=args.fee_paid,
            position_side=args.position_side,
            execution_side=args.execution_side,
            best_bid=args.best_bid,
            best_ask=args.best_ask,
            volume=args.volume,
            volume_usd=args.volume_usd,
            hours_to_resolution=args.hours_to_resolution,
            target_order_size_usd=args.target_order_size_usd,
            taker_fee_bps=args.taker_fee_bps,
            transaction_fee_bps=args.transaction_fee_bps,
            deposit_fee_usd=args.deposit_fee_usd,
            withdrawal_fee_usd=args.withdrawal_fee_usd,
        )
        print(json.dumps(result))
        return 0

    if args.command == "consume-markets":
        result = consume_weather_markets(
            base_url=args.base_url,
            source=args.source,
            limit=args.limit,
            min_status=args.min_status,
            explain_filtered=args.explain_filtered,
        )
        print(json.dumps(result))
        return 0

    if args.command == "paper-batch":
        result = run_weather_paper_batch(
            base_url=args.base_url,
            source=args.source,
            limit=args.limit,
            min_status=args.min_status,
            run_id_prefix=args.run_id_prefix,
            bankroll_usd=args.bankroll_usd,
            requested_quantity=args.requested_quantity,
        )
        print(json.dumps(result))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
