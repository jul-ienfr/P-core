from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from functools import partial
from pathlib import Path

from prediction_core.orchestrator import consume_weather_markets, run_weather_paper_batch, run_weather_workflow
from prediction_core.polymarket_execution import (
    ClobRestPolymarketExecutor,
    CompositeExecutionAuditLog,
    CompositeIdempotencyStore,
    DryRunPolymarketExecutor,
    ExecutionCredentialsError,
    ExecutionRiskLimits,
    ExecutionRiskState,
    JsonlExecutionAuditLog,
    JsonlIdempotencyStore,
    LiveExecutionGuardrailError,
    LiveExecutionUnavailableError,
    PostgresExecutionAuditLog,
    PostgresIdempotencyStore,
)
from prediction_core.polymarket_marketdata import (
    build_marketdata_worker_plan,
    dry_run_jsonl_stream_factory,
    replay_clob_ws_events,
    run_clob_marketdata_stream,
)
from prediction_core.polymarket_runtime import ExecutionDisabledError, LiveExecutionPermit, build_polymarket_runtime_scaffold, preflight_polymarket_live_readiness, run_polymarket_runtime_cycle
from prediction_core.polymarket_stack import recommended_polymarket_stack, stack_decision_table


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

    live_preflight = subparsers.add_parser(
        "polymarket-live-preflight",
        help="Check live Polymarket CLOB environment readiness without constructing an executor or submitting orders",
    )
    del live_preflight

    storage_health_parser = subparsers.add_parser(
        "storage-health",
        help="Check configured PostgreSQL, ClickHouse, Redis, NATS, S3, and Grafana storage components",
    )
    del storage_health_parser

    mirror_artifacts = subparsers.add_parser(
        "mirror-artifacts-s3",
        help="Plan a safe S3 mirror for local artifacts; only dry-run is supported for now",
    )
    mirror_artifacts.add_argument("--input-dir", required=True, help="Local artifact directory to scan")
    mirror_artifacts.add_argument("--bucket", help="Target S3 bucket; defaults to PREDICTION_CORE_S3_BUCKET")
    mirror_artifacts.add_argument("--prefix", default="raw", help="Target S3 key prefix")
    mirror_artifacts.add_argument("--source", default="local", help="Artifact source label for the S3 key")
    mirror_artifacts.add_argument("--max-files", type=int, help="Maximum number of files to include in the plan")
    mirror_artifacts.add_argument("--max-file-size-bytes", type=int, help="Reject files larger than this many bytes")
    mirror_artifacts.add_argument("--max-total-bytes", type=int, help="Reject plans larger than this many total bytes")
    mirror_artifacts.add_argument(
        "--allow-outside-artifacts-root",
        action="store_true",
        help="Allow scanning outside the default approved artifact roots",
    )
    mirror_artifacts.add_argument("--dry-run", action="store_true", default=True, help="Plan only; uploads are intentionally not enabled yet")

    replay_jsonl = subparsers.add_parser(
        "replay-jsonl-audit",
        help="Plan replay of a JSONL execution audit file into durable storage; dry-run only for now",
    )
    replay_jsonl.add_argument("--jsonl", required=True, help="JSONL audit file to inspect")
    replay_jsonl.add_argument("--max-rows", type=int, help="Maximum rows to include in the dry-run plan")
    replay_jsonl.add_argument("--dry-run", action="store_true", default=True, help="Plan only; writes are intentionally not enabled yet")

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
    runtime_cycle.add_argument("--max-snapshot-age-seconds", type=float, help="Maximum CLOB snapshot age allowed for decisions")
    runtime_cycle.add_argument("--paper-notional-usdc", type=float, default=5.0, help="Paper intent notional for disabled execution planner")
    runtime_cycle.add_argument("--execution-mode", choices=("paper", "dry_run", "live"), default="paper", help="Execution mode; paper remains the safe default; live requires explicit operator guardrails")
    runtime_cycle.add_argument("--idempotency-jsonl", help="JSONL idempotency store path required for dry_run execution")
    runtime_cycle.add_argument("--audit-jsonl", help="JSONL audit log path required for dry_run execution")
    runtime_cycle.add_argument("--max-order-notional-usdc", type=float, help="Per-order risk cap required for dry_run execution")
    runtime_cycle.add_argument("--max-total-exposure-usdc", type=float, help="Total exposure risk cap required for dry_run execution")
    runtime_cycle.add_argument("--max-daily-loss-usdc", type=float, help="Daily loss risk cap required for dry_run execution")
    runtime_cycle.add_argument("--max-spread", type=float, help="Maximum allowed bid/ask spread required for dry_run execution")
    runtime_cycle.add_argument("--total-exposure-usdc", type=float, default=0.0, help="Current total exposure for risk checks")
    runtime_cycle.add_argument("--daily-realized-pnl-usdc", type=float, default=0.0, help="Current daily realized PnL for risk checks")
    runtime_cycle.add_argument("--i-understand-live-orders", action="store_true", help="Required with --execution-mode live; acknowledges real Polymarket orders may be submitted")
    runtime_cycle.add_argument("--positions-confirmed", action="store_true", help="Required with --execution-mode live after operator position reconciliation")
    runtime_cycle.add_argument("--max-orders-per-cycle", type=int, default=1, help="Maximum live orders per bounded cycle; currently must be 1")
    del runtime_plan

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "serve":
        from prediction_core.server import build_server

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

    if args.command == "polymarket-live-preflight":
        print(json.dumps(preflight_polymarket_live_readiness()))
        return 0

    if args.command == "storage-health":
        from prediction_core.storage.health import storage_health

        print(json.dumps(storage_health(), default=str))
        return 0

    if args.command == "mirror-artifacts-s3":
        from os import environ
        from prediction_core.storage.artifact_ops import plan_artifact_mirror

        bucket = args.bucket or environ.get("PREDICTION_CORE_S3_BUCKET")
        if not bucket:
            parser.error("--bucket or PREDICTION_CORE_S3_BUCKET is required")
        result = plan_artifact_mirror(
            input_dir=args.input_dir,
            bucket=bucket,
            prefix=args.prefix,
            source=args.source,
            max_files=args.max_files,
            allow_outside_artifacts_root=args.allow_outside_artifacts_root,
            **({"max_file_size_bytes": args.max_file_size_bytes} if args.max_file_size_bytes is not None else {}),
            **({"max_total_bytes": args.max_total_bytes} if args.max_total_bytes is not None else {}),
        )
        print(json.dumps(result))
        return 0

    if args.command == "replay-jsonl-audit":
        from prediction_core.storage.artifact_ops import replay_jsonl_audit_plan

        print(json.dumps(replay_jsonl_audit_plan(jsonl_path=args.jsonl, max_rows=args.max_rows)))
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
        live_permit = None
        if args.paper_notional_usdc is None or not math.isfinite(float(args.paper_notional_usdc)) or float(args.paper_notional_usdc) <= 0.0:
            parser.error("--paper-notional-usdc must be finite and positive")
        if args.execution_mode == "live":
            if not args.i_understand_live_orders:
                parser.error("--execution-mode live requires --i-understand-live-orders")
            if not args.positions_confirmed:
                parser.error("--execution-mode live requires --positions-confirmed")
            if int(args.max_orders_per_cycle) != 1:
                parser.error("--execution-mode live currently requires --max-orders-per-cycle 1")
        if args.execution_mode in {"dry_run", "live"}:
            required_risk_values = [args.max_order_notional_usdc, args.max_total_exposure_usdc, args.max_daily_loss_usdc, args.max_spread]
            if not args.idempotency_jsonl or not args.audit_jsonl or any(value is None for value in required_risk_values):
                parser.error("dry_run execution requires --idempotency-jsonl, --audit-jsonl, and risk limits")
            try:
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
            except ValueError as exc:
                parser.error(str(exc))
            idempotency_store = JsonlIdempotencyStore(args.idempotency_jsonl)
            audit_log = JsonlExecutionAuditLog(args.audit_jsonl)
            postgres_repository = _try_build_operational_state_repository()
            if postgres_repository is not None:
                idempotency_store = CompositeIdempotencyStore(
                    idempotency_store,
                    PostgresIdempotencyStore(postgres_repository, mode=args.execution_mode, paper_only=True),
                )
                audit_log = CompositeExecutionAuditLog(
                    audit_log,
                    PostgresExecutionAuditLog(postgres_repository, paper_only=True, live_order_allowed=False),
                )
            if args.execution_mode == "dry_run":
                order_executor = DryRunPolymarketExecutor()
                live_permit = None
            else:
                try:
                    order_executor = ClobRestPolymarketExecutor.from_env()
                    preflight = preflight_polymarket_live_readiness(
                        order_management=order_executor,
                        positions_confirmed=args.positions_confirmed,
                    )
                    if not preflight["ready"]:
                        parser.error("live preflight failed: " + ",".join(preflight["readiness_blockers"]))
                    live_permit = LiveExecutionPermit(
                        preflight_ready=True,
                        operator_ack="I_UNDERSTAND_THIS_SUBMITS_REAL_POLYMARKET_ORDERS",
                        positions_confirmed=args.positions_confirmed,
                        max_orders_per_cycle=args.max_orders_per_cycle,
                    )
                except (ExecutionCredentialsError, LiveExecutionUnavailableError, LiveExecutionGuardrailError, ExecutionDisabledError) as exc:
                    parser.error(str(exc))
        result = asyncio.run(
            run_polymarket_runtime_cycle(
                markets=markets,
                probabilities=probabilities,
                dry_run_events_jsonl=args.dry_run_events_jsonl,
                max_events=args.max_events,
                min_liquidity=args.min_liquidity,
                min_edge=args.min_edge,
                max_snapshot_age_seconds=args.max_snapshot_age_seconds,
                paper_notional_usdc=args.paper_notional_usdc,
                execution_mode=args.execution_mode,
                order_executor=order_executor,
                risk_limits=risk_limits,
                risk_state=risk_state,
                idempotency_store=idempotency_store,
                audit_log=audit_log,
                live_permit=live_permit,
                max_orders_per_cycle=args.max_orders_per_cycle,
            )
        )
        print(json.dumps(result))
        return 0

    parser.print_help()
    return 0


def _try_build_operational_state_repository():
    if not (os.environ.get("PREDICTION_CORE_SYNC_DATABASE_URL") or os.environ.get("PANOPTIQUE_SYNC_DATABASE_URL")):
        return None
    try:
        from prediction_core.storage.postgres import OperationalStateRepository, create_prediction_core_sync_engine_from_env

        return OperationalStateRepository(create_prediction_core_sync_engine_from_env())
    except Exception as exc:
        import warnings

        warnings.warn(f"Postgres dual-write setup failed; continuing with JSONL primary behavior: {type(exc).__name__}", RuntimeWarning, stacklevel=2)
        return None


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
