from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .repositories import PanoptiqueRepository
from .snapshots import run_market_snapshot, run_orderbook_snapshot
from .shadow_bots import run_shadow_evaluate_db, run_shadow_evaluate_fixture
from .measurement import run_measure_shadow_flow_archive, run_measure_shadow_flow_db
from .paper_strategies import run_paper_strategy_fixture
from .summary import build_panoptique_summary
from .github_repos import DEFAULT_SEARCH_TERMS, GitHubRepoMetadata, run_github_repo_crawl
from .storage_exports import EXPORTABLE_TABLES, StorageCommandResult, export_table_to_parquet, write_db_health_report

DEFAULT_OUTPUT_DIR = Path("/home/jul/prediction_core/data/panoptique/snapshots")
DEFAULT_SHADOW_OUTPUT_DIR = Path("/home/jul/prediction_core/data/panoptique/shadow_predictions")
DEFAULT_MEASUREMENT_OUTPUT_DIR = Path("/home/jul/prediction_core/data/panoptique/measurements")
DEFAULT_PAPER_STRATEGY_OUTPUT_DIR = Path("/home/jul/prediction_core/data/panoptique/paper_strategies")
DEFAULT_ECOSYSTEM_OUTPUT_DIR = Path("/home/jul/prediction_core/data/panoptique/ecosystem")
DEFAULT_EXPORT_OUTPUT_DIR = Path("/home/jul/prediction_core/data/panoptique/exports")
DEFAULT_HEALTH_OUTPUT_DIR = Path("/home/jul/prediction_core/data/panoptique/reports")


def _repository_from_sqlite_path(path: str | None) -> PanoptiqueRepository | None:
    if not path:
        return None
    import sqlite3

    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    repo = PanoptiqueRepository(conn)
    repo.create_schema()
    return repo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Panoptique read-only observation CLI (no trading, no wallet access).")
    subparsers = parser.add_subparsers(dest="command", required=True)

    markets = subparsers.add_parser("snapshot-markets", help="Fetch a bounded Gamma market sample and write read-only snapshot artifacts.")
    markets.add_argument("--source", choices=["live"], default="live")
    markets.add_argument("--limit", type=int, required=True, help="Required bounded live fetch limit; must be >= 1.")
    markets.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    markets.add_argument("--sqlite-db", default=None, help="Optional local SQLite repository path for fixture/local validation; otherwise DB writes are explicitly skipped.")

    orderbook = subparsers.add_parser("snapshot-orderbook", help="Fetch one CLOB orderbook by token id and write read-only snapshot artifacts.")
    orderbook.add_argument("--source", choices=["live"], default="live")
    orderbook.add_argument("--token-id", required=True)
    orderbook.add_argument("--market-id", default="unknown")
    orderbook.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    orderbook.add_argument("--sqlite-db", default=None, help="Optional local SQLite repository path for fixture/local validation; otherwise DB writes are explicitly skipped.")

    shadow_fixture = subparsers.add_parser("shadow-evaluate-fixture", help="Evaluate deterministic shadow bots against a fixture/snapshot JSON file.")
    shadow_fixture.add_argument("--fixture", required=True, help="Path to JSON fixture with market_snapshot/orderbook_snapshot/weather_score/recent_prices.")
    shadow_fixture.add_argument("--output-dir", default=str(DEFAULT_SHADOW_OUTPUT_DIR))
    shadow_fixture.add_argument("--sqlite-db", default=None, help="Optional local SQLite repository path; otherwise DB writes are explicitly skipped.")

    shadow_db = subparsers.add_parser("shadow-evaluate-db", help="Evaluate deterministic shadow bots from recent repository snapshots.")
    shadow_db.add_argument("--output-dir", default=str(DEFAULT_SHADOW_OUTPUT_DIR))
    shadow_db.add_argument("--sqlite-db", default=None, help="Optional local SQLite repository path; without it the command emits skipped_unavailable status.")

    measure_archive = subparsers.add_parser("measure-shadow-flow", help="Replay archived shadow predictions against archived market snapshots.")
    measure_archive.add_argument("--predictions-jsonl", required=True)
    measure_archive.add_argument("--snapshots-dir", required=True)
    measure_archive.add_argument("--output-dir", default=str(DEFAULT_MEASUREMENT_OUTPUT_DIR))
    measure_archive.add_argument("--window", choices=["5m", "15m", "30m", "60m", "24h"], default="15m")
    measure_archive.add_argument("--sqlite-db", default=None, help="Optional local SQLite repository path; otherwise DB writes are explicitly skipped.")

    measure_db = subparsers.add_parser("measure-shadow-flow-db", help="Measure shadow predictions from repository/TimescaleDB snapshots.")
    measure_db.add_argument("--window", choices=["5m", "15m", "30m", "60m"], required=True)
    measure_db.add_argument("--output-dir", default=str(DEFAULT_MEASUREMENT_OUTPUT_DIR))
    measure_db.add_argument("--sqlite-db", default=None, help="Optional local SQLite repository path; without it the command emits skipped_unavailable/not_enough_data status.")

    paper = subparsers.add_parser("panoptique-paper-run", help="Run paper-only front-run/fade/skip strategy research against a JSONL fixture; no real orders.")
    paper.add_argument("--fixture", required=True, help="JSONL paper strategy signals with archived order book assumptions.")
    paper.add_argument("--output-dir", default=str(DEFAULT_PAPER_STRATEGY_OUTPUT_DIR))
    paper.add_argument("--out-of-sample-fraction", type=float, default=0.0, help="Fraction of chronological fixture rows labeled out_of_sample.")

    github = subparsers.add_parser("github-repos-crawl", help="Read-only GitHub public metadata crawler for prediction-market bot ecosystem research.")
    github.add_argument("--output-dir", default=str(DEFAULT_ECOSYSTEM_OUTPUT_DIR))
    github.add_argument("--limit-per-term", type=int, default=25)
    github.add_argument("--term", action="append", dest="terms", help="Override/append search term; defaults to Phase 6 v0 terms.")
    github.add_argument("--sqlite-db", default=None, help="Optional local SQLite repository path; otherwise DB writes are explicitly skipped.")

    audit = subparsers.add_parser("github-manual-audit-command", help="Print an optional shallow-clone command into /tmp for manual inspection only; does not execute it.")
    audit.add_argument("--repo-url", required=True)
    audit.add_argument("--name", required=True)

    summary = subparsers.add_parser("summary", help="Emit a read-only Panoptique cockpit summary from local DB state.")
    summary.add_argument("--sqlite-db", default=None, help="Optional local SQLite repository path; without it the summary degrades to empty.")
    summary.add_argument("--report-path", default=None, help="Optional latest operator report path to include in the summary payload.")
    summary.add_argument("--json", action="store_true", help="Print the summary as JSON for cockpit/API consumers.")

    export = subparsers.add_parser("export-parquet", help="Export approved Panoptique tables for offline analytics; read-only and secret-redacted.")
    export.add_argument("--table", required=True, choices=sorted(EXPORTABLE_TABLES), help="Approved table to export.")
    export.add_argument("--from", dest="from_ts", required=True, help="Inclusive observed_at lower bound, ISO-8601.")
    export.add_argument("--to", dest="to_ts", required=True, help="Exclusive observed_at upper bound, ISO-8601.")
    export.add_argument("--output-dir", default=str(DEFAULT_EXPORT_OUTPUT_DIR))
    export.add_argument("--sqlite-db", default=None, help="Local SQLite fixture DB for tests/local validation. PostgreSQL export should use a readonly connection in production tooling.")

    health = subparsers.add_parser("db-health", help="Write a safe read-only DB health report from local fixture DB state.")
    health.add_argument("--output-dir", default=str(DEFAULT_HEALTH_OUTPUT_DIR))
    health.add_argument("--sqlite-db", default=None, help="Local SQLite fixture DB for tests/local validation.")
    health.add_argument("--migration-version", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repository = _repository_from_sqlite_path(getattr(args, "sqlite_db", None))
    if args.command == "github-manual-audit-command":
        repo_meta = GitHubRepoMetadata(name=args.name, url=args.repo_url, stars=0, forks=0, pushed_at=None)
        print(repo_meta.manual_audit_command())
        return 0
    if args.command == "summary":
        summary = build_panoptique_summary(repository, report_path=args.report_path)
        payload = summary.to_dict()
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        else:
            print(
                "panoptique_summary "
                f"source={summary.source} readiness={summary.readiness_state} "
                f"snapshot_freshness_seconds={summary.snapshot_freshness_seconds} "
                f"shadow_predictions={summary.shadow_prediction_count} "
                f"matched_observations={summary.matched_observation_count} "
                f"gate={summary.current_gate_status} "
                f"report={summary.latest_operator_report_path}"
            )
            for error in summary.errors:
                print(f"error={error}")
        return 0
    if args.command == "export-parquet":
        if repository is None:
            print("export-parquet status=error count=0 db_status=skipped_unavailable")
            print("artifact=")
            print("report=")
            print("error=--sqlite-db is required for local safe export validation; production PostgreSQL export must use a readonly connection")
            return 0
        manifest = export_table_to_parquet(
            repository.conn,
            table=args.table,
            output_dir=args.output_dir,
            from_ts=args.from_ts,
            to_ts=args.to_ts,
        )
        result = StorageCommandResult(
            command="export-parquet",
            status="ok",
            count=manifest.row_count,
            artifact_path=manifest.path,
            report_path=manifest.manifest_path,
        )
        print(f"{result.command} status={result.status} count={result.count} db_status={result.db_status}")
        print(f"artifact={result.artifact_path}")
        print(f"report={result.report_path}")
        return 0
    if args.command == "db-health":
        if repository is None:
            print("db-health status=error count=0 db_status=skipped_unavailable")
            print("artifact=")
            print("report=")
            print("error=--sqlite-db is required for local safe health validation; production checks should use readonly PostgreSQL catalog queries")
            return 0
        report = write_db_health_report(repository.conn, output_dir=args.output_dir, migration_version=args.migration_version)
        print("db-health status=ok count=1 db_status=read_only")
        print("artifact=")
        print(f"report={Path(args.output_dir)}")
        print(json.dumps(report.to_dict(), sort_keys=True))
        return 0
    if args.command == "snapshot-markets":
        result = run_market_snapshot(source=args.source, limit=args.limit, output_dir=args.output_dir, repository=repository)
    elif args.command == "snapshot-orderbook":
        result = run_orderbook_snapshot(token_id=args.token_id, market_id=args.market_id, source=args.source, output_dir=args.output_dir, repository=repository)
    elif args.command == "shadow-evaluate-fixture":
        result = run_shadow_evaluate_fixture(fixture_path=args.fixture, output_dir=args.output_dir, repository=repository)
    elif args.command == "shadow-evaluate-db":
        result = run_shadow_evaluate_db(repository=repository, output_dir=args.output_dir)
    elif args.command == "measure-shadow-flow":
        result = run_measure_shadow_flow_archive(
            predictions_jsonl=args.predictions_jsonl,
            snapshots_dir=args.snapshots_dir,
            output_dir=args.output_dir,
            window=args.window,
            repository=repository,
        )
    elif args.command == "measure-shadow-flow-db":
        result = run_measure_shadow_flow_db(repository=repository, output_dir=args.output_dir, window=args.window)
    elif args.command == "panoptique-paper-run":
        result = run_paper_strategy_fixture(
            fixture_path=args.fixture,
            output_dir=args.output_dir,
            out_of_sample_fraction=args.out_of_sample_fraction,
        )
    elif args.command == "github-repos-crawl":
        result = run_github_repo_crawl(
            output_dir=args.output_dir,
            repository=repository,
            terms=tuple(args.terms) if args.terms else DEFAULT_SEARCH_TERMS,
            limit_per_term=args.limit_per_term,
        )
    else:  # pragma: no cover
        parser.error(f"Unknown command: {args.command}")
    print(f"{result.command} status={result.status} count={result.count} db_status={result.db_status}")
    print(f"artifact={result.artifact_path}")
    print(f"report={result.report_path}")
    if result.errors:
        for error in result.errors:
            print(f"error={error}")
    return 0 if result.status in {"ok", "error"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
