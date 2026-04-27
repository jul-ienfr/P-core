from __future__ import annotations

import argparse
import asyncio
import json
from functools import partial
from pathlib import Path

from prediction_core.orchestrator import consume_weather_markets, run_weather_paper_batch, run_weather_workflow
from prediction_core.polymarket_execution import (
    ClobRestPolymarketExecutor,
    DryRunPolymarketExecutor,
    ExecutionCredentialsError,
    ExecutionRiskLimits,
    ExecutionRiskState,
    JsonlExecutionAuditLog,
    JsonlIdempotencyStore,
)
from prediction_core.polymarket_marketdata import (
    build_marketdata_worker_plan,
    dry_run_jsonl_stream_factory,
    replay_clob_ws_events,
    run_clob_marketdata_stream,
)
from prediction_core.polymarket_runtime import build_polymarket_runtime_scaffold, run_polymarket_runtime_cycle
from prediction_core.polymarket_stack import recommended_polymarket_stack, stack_decision_table
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

    stack = subparsers.add_parser(
        "polymarket-stack",
        help="Print the recommended fastest Polymarket integration stack for prediction_core",
    )
    stack.add_argument(
        "--table",
        action="store_true",
        help="Print the layer-by-layer API/client decision table instead of the compact recommendation",
    )

    marketdata_plan = subparsers.add_parser(
        "marketdata-plan",
        help="Print the read-only Polymarket marketdata worker/cache plan for a faster hot path",
    )
    marketdata_plan.add_argument(
        "--discovery-interval-seconds",
        type=int,
        default=60,
        help="How often the Gamma discovery worker should refresh metadata outside the hot path",
    )
    marketdata_plan.add_argument(
        "--max-hot-markets",
        type=int,
        default=50,
        help="Maximum number of markets to keep subscribed in the CLOB hot path",
    )

    marketdata_replay = subparsers.add_parser(
        "marketdata-replay",
        help="Replay captured/simulated CLOB websocket JSONL events into the read-only marketdata cache",
    )
    marketdata_replay.add_argument(
        "--events-jsonl",
        required=True,
        help="Path to JSONL websocket events; each line is one event object",
    )

    marketdata_stream = subparsers.add_parser(
        "marketdata-stream",
        help="Run the read-only CLOB marketdata stream worker; dry-run JSONL is supported without network",
    )
    marketdata_stream.add_argument(
        "--token-id",
        action="append",
        default=[],
        help="CLOB token id to subscribe; repeat for YES/NO or multiple markets",
    )
    marketdata_stream.add_argument(
        "--dry-run-events-jsonl",
        help="Path to JSONL websocket events for deterministic dry-run without network",
    )
    marketdata_stream.add_argument(
        "--live",
        action="store_true",
        help="Use the real CLOB websocket transport; requires --max-events to keep the operator run bounded",
    )
    marketdata_stream.add_argument(
        "--max-events",
        type=int,
        help="Stop after this many received websocket events",
    )

    runtime_plan = subparsers.add_parser(
        "polymarket-runtime-plan",
        help="Print the complete read-only Polymarket runtime scaffold including disabled execution",
    )

    runtime_cycle = subparsers.add_parser(
        "polymarket-runtime-cycle",
        help="Run a bounded read-only discovery→marketdata→decision→disabled-execution cycle from local fixtures",
    )
    runtime_cycle.add_argument("--markets-json", required=True, help="Path to local Gamma-like markets JSON array")
    runtime_cycle.add_argument("--probabilities-json", required=True, help="Path to token_id -> model probability JSON object")
    runtime_cycle.add_argument("--dry-run-events-jsonl", required=True, help="Path to JSONL CLOB websocket events for bounded dry-run")
    runtime_cycle.add_argument("--max-events", type=int, required=True, help="Stop after this many CLOB events")
    runtime_cycle.add_argument("--min-liquidity", type=float, default=0.0, help="Minimum market liquidity for hot-path subscription")
    runtime_cycle.add_argument("--min-edge", type=float, default=0.0, help="Minimum probability minus ask edge for paper signal")
    runtime_cycle.add_argument("--paper-notional-usdc", type=float, default=5.0, help="Paper intent notional for disabled execution planner")
    runtime_cycle.add_argument("--execution-mode", choices=("paper", "dry_run", "live"), default="paper", help="Execution mode; paper remains the safe default")
    runtime_cycle.add_argument("--idempotency-jsonl", help="JSONL idempotency store path required for dry_run/live execution")
    runtime_cycle.add_argument("--audit-jsonl", help="JSONL audit log path required for dry_run/live execution")
    runtime_cycle.add_argument("--max-order-notional-usdc", type=float, help="Per-order risk cap required for dry_run/live execution")
    runtime_cycle.add_argument("--max-total-exposure-usdc", type=float, help="Total exposure risk cap required for dry_run/live execution")
    runtime_cycle.add_argument("--max-daily-loss-usdc", type=float, help="Daily loss risk cap required for dry_run/live execution")
    runtime_cycle.add_argument("--max-spread", type=float, help="Maximum allowed bid/ask spread required for dry_run/live execution")
    runtime_cycle.add_argument("--total-exposure-usdc", type=float, default=0.0, help="Current total exposure for risk checks")
    runtime_cycle.add_argument("--daily-realized-pnl-usdc", type=float, default=0.0, help="Current daily realized PnL for risk checks")
    del runtime_plan

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

    if args.command == "polymarket-stack":
        result = {"layers": stack_decision_table()} if args.table else recommended_polymarket_stack()
        print(json.dumps(result))
        return 0

    if args.command == "marketdata-plan":
        result = build_marketdata_worker_plan(
            discovery_interval_seconds=args.discovery_interval_seconds,
            max_hot_markets=args.max_hot_markets,
        )
        print(json.dumps(result))
        return 0

    if args.command == "marketdata-replay":
        events = _read_jsonl_events(Path(args.events_jsonl))
        print(json.dumps(replay_clob_ws_events(events)))
        return 0

    if args.command == "marketdata-stream":
        if args.live and args.dry_run_events_jsonl:
            parser.error("--live cannot be combined with --dry-run-events-jsonl")
        if not args.live and not args.dry_run_events_jsonl:
            parser.error("either --dry-run-events-jsonl or --live is required")
        if args.live and args.max_events is None:
            parser.error("--live requires --max-events for bounded operator runs")

        if args.live:
            result = asyncio.run(
                run_clob_marketdata_stream(
                    token_ids=args.token_id,
                    max_events=args.max_events,
                    dry_run=False,
                )
            )
        else:
            stream_factory = partial(dry_run_jsonl_stream_factory, path=args.dry_run_events_jsonl)
            result = asyncio.run(
                run_clob_marketdata_stream(
                    token_ids=args.token_id,
                    stream_factory=stream_factory,
                    max_events=args.max_events,
                    dry_run=True,
                )
            )
        print(json.dumps(result))
        return 0

    if args.command == "polymarket-runtime-plan":
        print(json.dumps(build_polymarket_runtime_scaffold()))
        return 0

    if args.command == "polymarket-runtime-cycle":
        markets = _read_json_file(Path(args.markets_json))
        probabilities = _read_json_file(Path(args.probabilities_json))
        if not isinstance(markets, list):
            parser.error("--markets-json must contain a JSON array")
        if not isinstance(probabilities, dict):
            parser.error("--probabilities-json must contain a JSON object")
        order_executor = None
        risk_limits = None
        risk_state = None
        idempotency_store = None
        audit_log = None
        if args.execution_mode in {"dry_run", "live"}:
            required_risk_values = [args.max_order_notional_usdc, args.max_total_exposure_usdc, args.max_daily_loss_usdc, args.max_spread]
            if not args.idempotency_jsonl or not args.audit_jsonl or any(value is None for value in required_risk_values):
                parser.error("live execution requires --idempotency-jsonl, --audit-jsonl, and risk limits")
            risk_limits = ExecutionRiskLimits(
                max_order_notional_usdc=args.max_order_notional_usdc,
                max_total_exposure_usdc=args.max_total_exposure_usdc,
                max_daily_loss_usdc=args.max_daily_loss_usdc,
                max_spread=args.max_spread,
            )
            risk_state = ExecutionRiskState(
                total_exposure_usdc=args.total_exposure_usdc,
                daily_realized_pnl_usdc=args.daily_realized_pnl_usdc,
            )
            idempotency_store = JsonlIdempotencyStore(args.idempotency_jsonl)
            audit_log = JsonlExecutionAuditLog(args.audit_jsonl)
            if args.execution_mode == "dry_run":
                order_executor = DryRunPolymarketExecutor()
            else:
                try:
                    order_executor = ClobRestPolymarketExecutor.from_env()
                except ExecutionCredentialsError as exc:
                    parser.error(str(exc))
        result = asyncio.run(
            run_polymarket_runtime_cycle(
                markets=markets,
                probabilities=probabilities,
                dry_run_events_jsonl=args.dry_run_events_jsonl,
                max_events=args.max_events,
                min_liquidity=args.min_liquidity,
                min_edge=args.min_edge,
                paper_notional_usdc=args.paper_notional_usdc,
                execution_mode=args.execution_mode,
                order_executor=order_executor,
                risk_limits=risk_limits,
                risk_state=risk_state,
                idempotency_store=idempotency_store,
                audit_log=audit_log,
            )
        )
        print(json.dumps(result))
        return 0

    parser.print_help()
    return 0


def _read_jsonl_events(path: Path) -> list[dict]:
    events: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                raise ValueError(f"line {line_number} must be a JSON object")
            events.append(payload)
    return events


def _read_json_file(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


if __name__ == "__main__":
    raise SystemExit(main())
