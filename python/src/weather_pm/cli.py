from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
import shlex
import tempfile
import time
from datetime import date as date_type
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from prediction_core.analytics.clickhouse_writer import create_clickhouse_writer_from_env
from prediction_core.analytics.events import serialize_event
from prediction_core.analytics.metrics import build_profile_metric_events, build_strategy_metric_events
from prediction_core.strategies.config_store import StrategyConfigStore
from weather_pm.account_data_sources import build_account_data_source_manifest, compact_account_data_source_manifest
from weather_pm.account_resolution_coverage import write_resolution_coverage_report
from weather_pm.account_learning import (
    load_account_trade_backfill,
    write_account_learning_backfill_pipeline,
    write_account_pattern_learning_digest,
    write_account_trade_import,
    write_shadow_profile_deep_dive,
    write_shadow_profile_report,
)
from weather_pm.analytics_adapter import (
    debug_decision_events_from_shortlist,
    execution_events_from_payload,
    paper_order_events_from_ledger,
    paper_pnl_snapshot_events_from_ledger,
    paper_position_events_from_ledger,
    profile_decision_events_from_shortlist,
    strategy_signal_events_from_shortlist,
)
from weather_pm.account_trades import backfill_account_trades_from_followlist, import_account_trades
from weather_pm.decision import build_decision
from weather_pm.event_surface import build_weather_event_surface
from weather_pm.execution_features import build_execution_features
from weather_pm.forecast_client import build_forecast_bundle
from weather_pm.hf_polymarket_dataset import write_hf_account_trades_sample
from weather_pm.decision_dataset import write_account_decision_dataset
from weather_pm.history_client import StationHistoryClient, _latency_operational_fields, _parse_observation_timestamp, build_station_history_bundle
from weather_pm.live_observer import run_live_observer_fast_collector, run_live_observer_once
from weather_pm.live_observer_config import load_live_observer_config
from weather_pm.learning_cycle import (
    assemble_learning_cycle_result,
    build_learning_cycle_contract,
    render_learning_cycle_summary_markdown,
    validate_learning_cycle_safety,
)
from weather_pm.live_readiness import attach_live_readiness, live_readiness_summary
from weather_pm.live_observer_storage_estimator import estimate_live_observer_storage
from weather_pm.live_storage import assert_not_unmounted_truenas_path, write_live_observer_payload_to_storage
from weather_pm.market_parser import parse_market_question
from weather_pm.miro_seed import build_miro_seed_markdown
from weather_pm.models import ForecastBundle
from weather_pm.multi_profile_paper_runner import (
    load_shortlist_payload,
    run_multi_profile_paper_batch,
    write_multi_profile_paper_artifacts,
)
from weather_pm.neighbor_context import build_neighbor_context
from weather_pm.operator_summary import write_profitable_accounts_operator_summary
from weather_pm.official_observation_backfill import write_official_observation_backfill
from weather_pm.orderbook_context import write_orderbook_context_report
from weather_pm.paper_autopilot_bridge import build_paper_autopilot_ledger
from weather_pm.paper_ledger import load_candidate, load_paper_ledger, load_refresh_payload, paper_ledger_place, paper_ledger_refresh, write_paper_ledger_artifacts
from weather_pm.paper_watchlist import compact_paper_watchlist_report, write_paper_watchlist_csv, write_paper_watchlist_markdown, write_paper_watchlist_report
from weather_pm.pipeline import score_market_from_question
from weather_pm.polymarket_client import get_event_book_by_id, get_market_by_id, list_weather_markets, normalize_market_record
from weather_pm.polymarket_live import fetch_market_execution_snapshot
from weather_pm.probability_model import build_model_output
from weather_pm.resolution_monitor import write_paper_resolution_monitor
from weather_pm.resolution_parser import parse_resolution_metadata
from weather_pm.scoring import score_market
from weather_pm.shadow_paper_runner import (
    run_account_trade_resolution_artifact,
    run_historical_profile_rule_candidates_artifact,
    run_market_metadata_resolution_artifact,
    run_shadow_paper_runner_artifact,
    run_shadow_profile_evaluator_artifact,
    run_shadow_profile_exposure_preview_artifact,
    run_shadow_profile_learning_report_artifact,
)
from weather_pm.shadow_profiles import write_learned_shadow_patterns_artifacts, write_promoted_profile_opportunity_dataset_artifact, write_shadow_profile_artifacts
from weather_pm.smoke_comparison import write_smoke_comparison
from weather_pm.source_coverage import build_weather_source_coverage_report
from weather_pm.source_routing import build_resolution_source_route
from weather_pm.station_binding import build_station_binding
from weather_pm.source_selection import select_best_station_sources
from weather_pm.strategy_extractor import extract_weather_strategy_rules
from weather_pm.strategy_profiles import compact_strategy_profile_report, strategy_profiles_markdown
from weather_pm.strategy_shortlist import build_operator_shortlist_report, build_strategy_shortlist
from weather_pm.traders import WeatherTrader, build_weather_trader_registry, load_weather_traders, reverse_engineer_weather_traders
from weather_pm.wallet_intel import fetch_trader_strategy_profile
from weather_pm.wallet_sizing_priors import build_wallet_sizing_priors
from weather_pm.weather_decision_context import write_decision_weather_context
from weather_pm.winner_pattern_engine import write_winner_pattern_engine
from weather_pm.paper_candidate_gate import write_winner_pattern_paper_candidates
from weather_pm.winner_pattern_report import write_winner_pattern_operator_report
from weather_pm.winner_pattern_pipeline import run_winner_pattern_pipeline
from weather_pm.winning_patterns import compact_winning_patterns_operator_report, write_winning_patterns_operator_report


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

    subparsers.add_parser("source-coverage", help="Summarize integrated weather resolution source coverage")

    station_history = subparsers.add_parser("station-history", help="Fetch direct observed history from a market's resolution station")
    station_history.add_argument("--market-id", required=True, help="Market id whose resolution station should be followed")
    station_history.add_argument("--source", choices=_VALID_SOURCES, default="live", help="Market source")
    station_history.add_argument("--start-date", required=True, help="Start date YYYY-MM-DD")
    station_history.add_argument("--end-date", required=True, help="End date YYYY-MM-DD")

    station_latest = subparsers.add_parser("station-latest", help="Fetch latest direct observation from a market's resolution station")
    station_latest.add_argument("--market-id", required=True, help="Market id whose latest resolution station observation should be followed")
    station_latest.add_argument("--source", choices=_VALID_SOURCES, default="live", help="Market source")

    resolution_status = subparsers.add_parser("resolution-status", help="Combine latest direct and official daily extract into a resolution status")
    resolution_status.add_argument("--market-id", required=True, help="Market id whose resolution status should be checked")
    resolution_status.add_argument("--source", choices=_VALID_SOURCES, default="live", help="Market source")
    resolution_status.add_argument("--date", required=True, help="Resolution date YYYY-MM-DD")

    monitor_paper_resolution = subparsers.add_parser("monitor-paper-resolution", help="Persist paper-trade resolution status and operator monitor artifacts")
    monitor_paper_resolution.add_argument("--market-id", required=True, help="Market id whose paper resolution should be monitored")
    monitor_paper_resolution.add_argument("--source", choices=_VALID_SOURCES, default="live", help="Market source")
    monitor_paper_resolution.add_argument("--date", required=True, help="Resolution date YYYY-MM-DD")
    monitor_paper_resolution.add_argument("--paper-side", required=True, choices=("yes", "no"), help="Paper trade side")
    monitor_paper_resolution.add_argument("--paper-notional-usd", required=True, type=float, help="Paper notional in USD")
    monitor_paper_resolution.add_argument("--paper-shares", required=True, type=float, help="Paper shares")
    monitor_paper_resolution.add_argument("--output-dir", required=True, help="Directory for monitor artifacts")

    price_market = subparsers.add_parser("price-market", help="Produce a theoretical price for a market")
    price_market.add_argument("--market-id", required=False, help="Market identifier")

    import_traders = subparsers.add_parser("import-weather-traders", help="Import classified weather trader leaderboard data")
    import_traders.add_argument("--classified-csv", required=True, help="Classified Polymarket weather leaderboard CSV")
    import_traders.add_argument("--registry-out", required=True, help="Output JSON registry path")
    import_traders.add_argument("--reverse-engineering-out", required=True, help="Output JSON reverse-engineering report path")
    import_traders.add_argument("--min-pnl", required=False, type=float, default=0.0, help="Minimum weather PnL for reverse engineering report")

    trader_profile_parser = subparsers.add_parser("trader-profile", help="Build a Polymarket wallet strategy profile")
    trader_profile_parser.add_argument("--wallet", required=True, help="Polymarket user wallet/address")
    trader_profile_parser.add_argument("--page-size", required=False, type=int, default=50, help="Closed-position page size")

    account_learning_backfill = subparsers.add_parser("account-learning-backfill", help="Run backfill-first account learning into trades/profile artifacts")
    account_learning_backfill.add_argument("--input-json", required=True, help="Public account trade/backfill JSON")
    account_learning_backfill.add_argument("--output-dir", required=True, help="Output directory for account_trades and shadow_profiles artifacts")
    account_learning_backfill.add_argument("--run-id", required=False, help="Optional deterministic artifact run id")

    learning_cycle = subparsers.add_parser("learning-cycle", help="Build a dry-run/no-network learning cycle contract")
    learning_cycle.add_argument("--run-id", required=True, help="Learning cycle run id")
    learning_cycle.add_argument("--output-dir", required=True, help="Output directory for learning cycle artifacts")
    learning_cycle.add_argument("--max-accounts", required=True, type=int, help="Maximum accounts to consider")
    learning_cycle.add_argument("--trades-per-account", required=True, type=int, help="Maximum trades per account")
    learning_cycle.add_argument("--lookback-days", required=True, type=int, help="Lookback window in days")
    learning_cycle.add_argument("--dry-run", action="store_true", help="Required: do not execute side-effectful learning steps")
    learning_cycle.add_argument("--no-network", action="store_true", help="Required: do not use network access")
    learning_cycle.add_argument("--learning-report-json", required=False, help="Optional safe learning report JSON for full cycle artifact assembly")

    subparsers.add_parser("account-data-source-manifest", help="Summarize read-only data sources for account pattern learning")

    hf_account_trades_sample = subparsers.add_parser("hf-account-trades-sample", help="Normalize a local Hugging Face Polymarket_data trade sample in paper-only mode")
    hf_account_trades_sample.add_argument("--input", required=True, help="Local .json/.jsonl/.parquet sample path")
    hf_account_trades_sample.add_argument("--wallet", action="append", dest="wallets", help="Wallet to include; repeat for multiple wallets")
    hf_account_trades_sample.add_argument("--wallets-json", required=False, help="Optional JSON array or object with wallets/accounts array")
    hf_account_trades_sample.add_argument("--output-json", required=True, help="Output normalized sample artifact")
    hf_account_trades_sample.add_argument("--limit", required=False, type=int, default=1000, help="Maximum local sample rows to scan")

    account_resolution_coverage = subparsers.add_parser("account-resolution-coverage", help="Measure multi-key account trade resolution coverage in paper-only mode")
    account_resolution_coverage.add_argument("--trades-json", required=True, help="Input account trades JSON")
    account_resolution_coverage.add_argument("--resolutions-json", required=True, help="Input resolutions JSON")
    account_resolution_coverage.add_argument("--output-json", required=True, help="Output resolution coverage artifact")

    enrich_trades_orderbook_context = subparsers.add_parser("enrich-trades-orderbook-context", help="Attach historical orderbook context and capturability evidence to trades")
    enrich_trades_orderbook_context.add_argument("--trades-json", required=True, help="Input account trades JSON")
    enrich_trades_orderbook_context.add_argument("--orderbook-snapshots-json", required=True, help="Input historical orderbook snapshots JSON")
    enrich_trades_orderbook_context.add_argument("--output-json", required=True, help="Output enriched trades artifact")
    enrich_trades_orderbook_context.add_argument("--max-staleness-seconds", required=False, type=int, default=3600, help="Maximum allowed snapshot staleness in seconds")

    build_account_decision_dataset = subparsers.add_parser("build-account-decision-dataset", help="Build observable account trade/no-trade decision dataset v2")
    build_account_decision_dataset.add_argument("--trades-json", required=True, help="Input weather account trades JSON")
    build_account_decision_dataset.add_argument("--markets-snapshots-json", required=True, help="Input active market snapshots JSON")
    build_account_decision_dataset.add_argument("--output-json", required=True, help="Output decision dataset JSON")
    build_account_decision_dataset.add_argument("--bucket-minutes", required=False, type=int, default=60, help="Decision timestamp bucket size in minutes")
    build_account_decision_dataset.add_argument("--no-trade-per-trade", required=False, type=int, default=5, help="Max no-trade examples per trade per account/surface bucket")

    enrich_decision_weather_context = subparsers.add_parser("enrich-decision-weather-context", help="Attach forecast-at-decision and resolution/source context to decision examples")
    enrich_decision_weather_context.add_argument("--decision-dataset-json", required=True, help="Input decision dataset JSON")
    enrich_decision_weather_context.add_argument("--forecast-snapshots-json", required=True, help="Input forecast snapshots JSON")
    enrich_decision_weather_context.add_argument("--resolution-sources-json", required=False, help="Optional resolution/source observations JSON")
    enrich_decision_weather_context.add_argument("--output-json", required=True, help="Output weather decision context JSON")

    official_observation_backfill = subparsers.add_parser("official-observation-backfill", help="Validate local official weather observations into backfill-ready resolution rows")
    official_observation_backfill.add_argument("--input-json", required=True, help="Input official observation JSON")
    official_observation_backfill.add_argument("--output-json", required=True, help="Output validated backfill JSON")

    winner_pattern_engine = subparsers.add_parser("winner-pattern-engine", help="Learn robust, capturable weather winner patterns in paper-only mode")
    winner_pattern_engine.add_argument("--decision-context-json", required=True, help="Input enriched decision/weather context JSON")
    winner_pattern_engine.add_argument("--resolved-trades-json", required=True, help="Input resolved trades JSON")
    winner_pattern_engine.add_argument("--output-json", required=True, help="Output winner patterns JSON")
    winner_pattern_engine.add_argument("--output-md", required=False, help="Optional Markdown operator report")
    winner_pattern_engine.add_argument("--min-resolved-trades", required=False, type=int, default=5, help="Minimum resolved trades for robust promotion")
    winner_pattern_engine.add_argument("--max-top1-pnl-share", required=False, type=float, default=0.8, help="Maximum allowed top account/wallet PnL concentration")

    winner_pattern_candidates = subparsers.add_parser("winner-pattern-paper-candidates", help="Gate current markets into paper candidates or watch-only skips")
    winner_pattern_candidates.add_argument("--winner-patterns-json", required=True, help="Input winner patterns JSON")
    winner_pattern_candidates.add_argument("--current-markets-json", required=True, help="Input current markets JSON")
    winner_pattern_candidates.add_argument("--current-orderbooks-json", required=True, help="Input current orderbooks JSON")
    winner_pattern_candidates.add_argument("--current-weather-context-json", required=True, help="Input current weather context JSON")
    winner_pattern_candidates.add_argument("--output-json", required=True, help="Output paper candidates JSON")
    winner_pattern_candidates.add_argument("--output-md", required=False, help="Optional Markdown operator report")

    winner_pattern_report = subparsers.add_parser("winner-pattern-report", help="Build dashboard-ready winner pattern operator report")
    winner_pattern_report.add_argument("--winner-patterns-json", required=True, help="Input winner patterns JSON")
    winner_pattern_report.add_argument("--paper-candidates-json", required=True, help="Input paper candidates JSON")
    winner_pattern_report.add_argument("--resolution-coverage-json", required=False, help="Optional resolution coverage JSON")
    winner_pattern_report.add_argument("--orderbook-context-json", required=False, help="Optional orderbook context JSON")
    winner_pattern_report.add_argument("--output-json", required=True, help="Output operator report JSON")
    winner_pattern_report.add_argument("--output-md", required=True, help="Output operator report Markdown")

    smoke_comparison = subparsers.add_parser("smoke-comparison", help="Compare two weather winner-pattern smoke artifacts in paper-only mode")
    smoke_comparison.add_argument("--before-json", required=True, help="Baseline operator_report.json or winner_patterns.json")
    smoke_comparison.add_argument("--after-json", required=True, help="New operator_report.json or winner_patterns.json")
    smoke_comparison.add_argument("--output-json", required=True, help="Output comparison JSON")
    smoke_comparison.add_argument("--output-md", required=False, help="Optional output comparison Markdown")

    winner_pattern_pipeline = subparsers.add_parser("winner-pattern-pipeline", help="Run fixture-only winner pattern pipeline without network by default")
    winner_pattern_pipeline.add_argument("--trades-json", required=True, help="Input account trades JSON")
    winner_pattern_pipeline.add_argument("--resolutions-json", required=True, help="Input resolutions JSON")
    winner_pattern_pipeline.add_argument("--orderbook-snapshots-json", required=True, help="Input orderbook snapshots JSON")
    winner_pattern_pipeline.add_argument("--market-snapshots-json", required=True, help="Input active market snapshots JSON")
    winner_pattern_pipeline.add_argument("--forecast-snapshots-json", required=True, help="Input forecast snapshots JSON")
    winner_pattern_pipeline.add_argument("--output-dir", required=True, help="Output directory for pipeline artifacts")
    winner_pattern_pipeline.add_argument("--allow-network", action="store_true", help="Explicitly request network access (currently rejected)")

    legacy_account_trades_backfill = subparsers.add_parser("backfill-account-trades", help="Backfill public Polymarket account trades from a followlist CSV")
    legacy_account_trades_backfill.add_argument("--followlist", required=True, help="CSV followlist with wallet/handle columns")
    legacy_account_trades_backfill.add_argument("--out-json", required=True, help="Output raw public trades JSON")
    legacy_account_trades_backfill.add_argument("--limit-accounts", required=False, type=int, default=20, help="Maximum accounts to backfill")
    legacy_account_trades_backfill.add_argument("--trades-per-account", required=False, type=int, default=100, help="Maximum public trades per account")

    legacy_import_account_trades = subparsers.add_parser("import-account-trades", help="Classify raw public account trades into weather trades and profiles")
    legacy_import_account_trades.add_argument("--trades-json", required=True, help="Input raw public account trades JSON")
    legacy_import_account_trades.add_argument("--trades-out", required=True, help="Output classified weather trades JSON")
    legacy_import_account_trades.add_argument("--profiles-out", required=True, help="Output historical account profiles JSON")

    account_trades_backfill = subparsers.add_parser("account-trades-backfill", help="Normalize public Polymarket weather account trade backfill JSON")
    account_trades_backfill.add_argument("--input-json", required=True, help="Public account trade/backfill JSON")

    account_trades_import = subparsers.add_parser("account-trades-import", help="Import normalized public account trades into a local JSON artifact")
    account_trades_import.add_argument("--input-json", required=True, help="Public account trade/backfill JSON")
    account_trades_import.add_argument("--output-json", required=True, help="Output account_trades JSON artifact")

    shadow_profiles_report = subparsers.add_parser("shadow-profiles-report", help="Build historical shadow profiles from imported account trades")
    shadow_profiles_report.add_argument("--trades-json", required=True, help="account_trades JSON artifact")
    shadow_profiles_report.add_argument("--output-json", required=True, help="Output shadow_profiles JSON artifact")
    shadow_profiles_report.add_argument("--output-md", required=False, help="Optional Markdown operator report")

    legacy_shadow_patterns = subparsers.add_parser("shadow-patterns-report", help="Write learned shadow-pattern JSON/Markdown from a trade/no-trade dataset")
    legacy_shadow_patterns.add_argument("--dataset-json", required=True, help="Input trade/no-trade dataset JSON")
    legacy_shadow_patterns.add_argument("--output-json", required=True, help="Output learned patterns JSON")
    legacy_shadow_patterns.add_argument("--output-md", required=False, help="Optional Markdown operator report")
    legacy_shadow_patterns.add_argument("--limit", required=False, type=int, default=20, help="Maximum learned patterns")

    account_pattern_digest = subparsers.add_parser("account-pattern-learning-digest", help="Consolidate validated account patterns and live radar conflicts into paper-only guardrails")
    account_pattern_digest.add_argument("--validation-json", required=True, help="Input account-pattern validation JSON")
    account_pattern_digest.add_argument("--live-radar-json", required=True, help="Input live radar JSON")
    account_pattern_digest.add_argument("--output-json", required=True, help="Output consolidated learning digest JSON")
    account_pattern_digest.add_argument("--output-md", required=False, help="Optional Markdown operator report")

    promoted_profile_opportunities = subparsers.add_parser("promoted-profile-opportunity-dataset", help="Build a paper-only opportunity dataset from promoted shadow profiles and candidate markets")
    promoted_profile_opportunities.add_argument("--promoted-profiles-json", required=True, help="Shadow profile evaluation JSON containing promoted profiles")
    promoted_profile_opportunities.add_argument("--markets-json", required=True, help="Candidate/current markets JSON")
    promoted_profile_opportunities.add_argument("--dataset-out", required=True, help="Output promoted profile opportunity dataset JSON")

    legacy_shadow_profile = subparsers.add_parser("shadow-profile-report", help="Build trade/no-trade dataset and operator shadow profile report")
    legacy_shadow_profile.add_argument("--weather-trades-json", required=True, help="Input classified weather trades JSON")
    legacy_shadow_profile.add_argument("--markets-json", required=True, help="Input weather markets JSON")
    legacy_shadow_profile.add_argument("--dataset-out", required=True, help="Output trade/no-trade dataset JSON")
    legacy_shadow_profile.add_argument("--report-out", required=True, help="Output operator report JSON")
    legacy_shadow_profile.add_argument("--limit", required=False, type=int, default=10, help="Maximum profiles in report")
    legacy_shadow_profile.add_argument("--accounts-csv", required=False, help="Optional followlist CSV for no-trade expansion")
    legacy_shadow_profile.add_argument("--limit-accounts", required=False, type=int, help="Maximum followlist accounts")

    shadow_profiles_deep_dive = subparsers.add_parser("shadow-profiles-deep-dive", help="Render one account shadow-profile deep dive")
    shadow_profiles_deep_dive.add_argument("--profiles-json", required=True, help="shadow_profiles JSON artifact")
    shadow_profiles_deep_dive.add_argument("--wallet", required=False, help="Wallet to inspect")
    shadow_profiles_deep_dive.add_argument("--handle", required=False, help="Handle to inspect")
    shadow_profiles_deep_dive.add_argument("--output-md", required=False, help="Optional Markdown deep dive")

    shadow_paper_runner = subparsers.add_parser("shadow-paper-runner", help="Build paper-only shadow orders from account trade/no-trade profiles plus orderbook/forecast features")
    shadow_paper_runner.add_argument("--dataset-json", required=True, help="Trade/no-trade dataset JSON")
    shadow_paper_runner.add_argument("--orderbooks-json", required=False, help="Optional market-id keyed orderbook feature JSON")
    shadow_paper_runner.add_argument("--forecasts-json", required=False, help="Optional surface-key keyed forecast feature JSON")
    shadow_paper_runner.add_argument("--historical-forecasts-json", required=False, help="Optional market-id/surface-key forecast context JSON captured at trade time")
    shadow_paper_runner.add_argument("--resolutions-json", required=False, help="Optional market-id/surface-key historical resolution JSON")
    shadow_paper_runner.add_argument("--profile-configs-json", required=False, help="Optional wallet/handle keyed shadow profile replay config JSON")
    shadow_paper_runner.add_argument("--promoted-profiles-json", required=False, help="Optional shadow profile evaluation JSON with promoted paper profiles")
    shadow_paper_runner.add_argument("--historical-profile-rules-json", required=False, help="Optional historical profile rule candidates JSON for paper-only replay gating")
    shadow_paper_runner.add_argument("--stress-overlay-json", required=False, help="Optional paper-only stress overlay JSON to filter and cap generated paper orders")
    shadow_paper_runner.add_argument("--run-id", required=True, help="Shadow paper replay run id")
    shadow_paper_runner.add_argument("--output-json", required=True, help="Output paper-only shadow orders JSON")
    shadow_paper_runner.add_argument("--skip-diagnostics-json", required=False, help="Optional output JSON explaining skipped paper replay candidates and unlock conditions")
    shadow_paper_runner.add_argument("--max-order-usdc", required=False, type=float, default=5.0, help="Maximum simulated notional per shadow order")

    market_metadata_resolution = subparsers.add_parser("market-metadata-resolution", help="Extract closed/resolved market metadata into a paper-only resolution JSON")
    market_metadata_resolution.add_argument("--markets-json", required=True, help="Input Gamma market metadata JSON")
    market_metadata_resolution.add_argument("--output-json", required=True, help="Output market-id keyed resolution JSON")

    account_trade_resolution = subparsers.add_parser("account-trade-resolution", help="Score imported account trades against resolved outcomes in paper-only mode")
    account_trade_resolution.add_argument("--trades-json", required=True, help="Input classified account trades JSON")
    account_trade_resolution.add_argument("--resolutions-json", required=True, help="Market/slug keyed resolution JSON")
    account_trade_resolution.add_argument("--output-json", required=True, help="Output resolved trade dataset JSON")

    shadow_profile_evaluator = subparsers.add_parser("shadow-profile-evaluator", help="Evaluate shadow profile paper orders and historical resolved account trades")
    shadow_profile_evaluator.add_argument("--paper-orders-json", required=True, help="Input shadow paper orders JSON")
    shadow_profile_evaluator.add_argument("--trade-resolution-json", required=False, help="Optional resolved account trade dataset JSON")
    shadow_profile_evaluator.add_argument("--output-json", required=True, help="Output shadow profile evaluation JSON")
    shadow_profile_evaluator.add_argument("--output-md", required=False, help="Optional Markdown operator report")
    shadow_profile_evaluator.add_argument("--handoff-dataset-json", required=False, help="Dataset path to show in promoted opportunity replay handoff")
    shadow_profile_evaluator.add_argument("--handoff-orderbooks-json", required=False, help="Orderbooks path to show in promoted opportunity replay handoff")

    historical_profile_rules = subparsers.add_parser("historical-profile-rules", help="Build paper-only profile gating rules from resolved historical account trades")
    historical_profile_rules.add_argument("--trade-resolution-json", required=True, help="Resolved account trade dataset JSON")
    historical_profile_rules.add_argument("--output-json", required=True, help="Output historical profile rule candidates JSON")
    historical_profile_rules.add_argument("--output-md", required=False, help="Optional Markdown operator rule report")

    learning_report = subparsers.add_parser("shadow-profile-learning-report", help="Build a paper-only learning report from profile evaluation and optional paper orders")
    learning_report.add_argument("--evaluation-json", required=True, help="Shadow profile evaluation JSON")
    learning_report.add_argument("--paper-orders-json", required=False, help="Optional shadow paper orders JSON for high-information case selection")
    learning_report.add_argument("--output-json", required=True, help="Output learning report JSON")
    learning_report.add_argument("--output-md", required=False, help="Optional Markdown learning report")

    shadow_profile_evaluator.add_argument("--handoff-forecasts-json", required=False, help="Forecasts path to show in promoted opportunity replay handoff")
    shadow_profile_evaluator.add_argument("--handoff-stress-overlay-json", required=False, help="Stress overlay path to show in promoted opportunity replay handoff")
    shadow_profile_evaluator.add_argument("--handoff-historical-profile-rules-json", required=False, help="Historical profile rules path to show in promoted opportunity replay handoff")
    shadow_profile_evaluator.add_argument("--handoff-run-id", required=False, help="Run id to show in promoted opportunity replay handoff")
    shadow_profile_evaluator.add_argument("--handoff-paper-orders-json", required=False, help="Paper orders output path to show in replay and exposure handoff")
    shadow_profile_evaluator.add_argument("--handoff-exposure-json", required=False, help="Exposure preview JSON path to show in promoted opportunity handoff")
    shadow_profile_evaluator.add_argument("--handoff-exposure-md", required=False, help="Exposure preview Markdown path to show in promoted opportunity handoff")

    exposure_preview = subparsers.add_parser("shadow-profile-exposure-preview", help="Build a paper-only exposure preview from stress-overlay shadow paper orders")
    exposure_preview.add_argument("--paper-orders-json", required=True, help="Input stress-overlay paper orders JSON")
    exposure_preview.add_argument("--output-json", required=True, help="Output exposure preview JSON")
    exposure_preview.add_argument("--output-md", required=False, help="Optional Markdown operator exposure preview")

    strategy_report = subparsers.add_parser("strategy-report", help="Extract reusable weather strategy rules from a reverse-engineering report")
    strategy_report.add_argument("--reverse-engineering-json", required=True, help="Reverse-engineering JSON produced by import-weather-traders")

    strategy_profiles = subparsers.add_parser("strategy-profiles", help="List compact weather strategy profiles")
    strategy_profiles.add_argument("--output-md", required=False, help="Optional path to write a Markdown strategy profile matrix")

    strategy_shortlist = subparsers.add_parser("strategy-shortlist", help="Rank paper-cycle opportunities using profitable weather trader strategies and event-surface anomalies")
    strategy_shortlist.add_argument("--strategy-report-json", required=True, help="Strategy report JSON produced by strategy-report")
    strategy_shortlist.add_argument("--opportunity-report-json", required=True, help="Compact opportunity report JSON produced by paper-cycle-report")
    strategy_shortlist.add_argument("--event-surface-json", required=False, help="Optional event surface JSON produced by event-surface tooling")
    strategy_shortlist.add_argument("--limit", required=False, type=int, default=25, help="Maximum shortlisted opportunities")

    operator_shortlist = subparsers.add_parser("operator-shortlist", help="Compress a saved strategy shortlist into an operator action report")
    operator_shortlist.add_argument("--shortlist-json", required=True, help="Full or compact strategy shortlist JSON")
    operator_shortlist.add_argument("--limit", required=False, type=int, default=10, help="Maximum watchlist rows to include")
    operator_shortlist.add_argument("--output-json", required=False, help="Optional path to write the refreshed operator action report")

    export_analytics = subparsers.add_parser("export-analytics-clickhouse", help="Export weather shortlist and paper ledger analytics to ClickHouse")
    export_analytics.add_argument("--shortlist-json", required=False, help="Strategy shortlist/profile JSON to export")
    export_analytics.add_argument("--paper-ledger-json", required=False, help="Paper ledger JSON to export")
    export_analytics.add_argument("--execution-events-json", required=False, help="Execution events/live orders JSON to export")
    export_analytics.add_argument("--strategy-config-json", required=False, help="Strategy config JSON to export")
    export_analytics.add_argument("--dry-run", action="store_true", help="Build rows and print counts without inserting")

    operator_refresh = subparsers.add_parser("operator-refresh", help="Refresh a saved live strategy shortlist or operator report for operator handoff")
    operator_refresh.add_argument("--input-json", required=True, help="Saved strategy shortlist or operator report JSON")
    operator_refresh.add_argument("--source", choices=_VALID_SOURCES, required=False, help="Market source override")
    operator_refresh.add_argument("--resolution-date", required=False, help="Reference resolution date YYYY-MM-DD for direct/latest status refresh")
    operator_refresh.add_argument("--operator-limit", required=False, type=int, default=10, help="Maximum refreshed operator watchlist rows to include")
    operator_refresh.add_argument("--output-json", required=False, help="Optional path to write the full refreshed operator artifact")
    operator_refresh.add_argument("--storage-backend", choices=("auto", "noop", "postgres", "clickhouse", "all"), default="noop", help="Optional abstract storage sink for live observer rows")
    operator_refresh.add_argument("--storage-dry-run", action="store_true", help="Build storage rows without writing")
    operator_refresh.add_argument("--skip-resolution-status", action="store_true", help="Do not refresh direct/latest resolution status")
    operator_refresh.add_argument("--skip-orderbook", action="store_true", help="Do not refresh Polymarket order book metrics")
    operator_refresh.add_argument("--iterations", required=False, type=int, default=1, help="Number of refresh iterations to run")
    operator_refresh.add_argument("--poll-interval-seconds", required=False, type=float, default=0.0, help="Delay between refresh iterations")

    profitable_operator_summary = subparsers.add_parser(
        "profitable-accounts-operator-summary",
        help="Bridge classified profitable weather accounts with a live operator shortlist report",
    )
    profitable_operator_summary.add_argument("--classified-csv", required=True, help="Classified profitable weather accounts CSV")
    profitable_operator_summary.add_argument("--reverse-engineering-json", required=True, help="Reverse-engineering JSON produced by import-weather-traders")
    profitable_operator_summary.add_argument("--operator-report-json", required=True, help="Operator shortlist report JSON")
    profitable_operator_summary.add_argument("--output-json", required=True, help="Output compact operator summary JSON")
    profitable_operator_summary.add_argument("--priority-limit", required=False, type=int, default=10, help="Maximum priority accounts to include")

    wallet_sizing_priors = subparsers.add_parser("wallet-sizing-priors", help="Build wallet style sizing priors from profitable account behavior JSON")
    wallet_sizing_priors.add_argument("--input", required=True, help="Input profitable account behavior JSON")
    wallet_sizing_priors.add_argument("--output", required=True, help="Output wallet sizing priors JSON")

    winning_patterns_report = subparsers.add_parser("winning-patterns-report", help="Extract operator rules from profitable weather account strategy artifacts")
    winning_patterns_report.add_argument("--classified-summary-json", required=True, help="Classified profitable accounts summary JSON")
    winning_patterns_report.add_argument("--continued-summary-json", required=True, help="Continued profitable accounts summary JSON")
    winning_patterns_report.add_argument("--strategy-patterns-json", required=True, help="Strategy pattern extraction JSON")
    winning_patterns_report.add_argument("--strategy-report-json", required=True, help="Weather-heavy strategy report JSON")
    winning_patterns_report.add_argument("--future-consensus-json", required=True, help="Future consensus/source-check JSON")
    winning_patterns_report.add_argument("--orderbook-bridge-json", required=True, help="Consensus orderbook bridge JSON")
    winning_patterns_report.add_argument("--output-json", required=False, help="Optional full report JSON path")
    winning_patterns_report.add_argument("--output-md", required=False, help="Optional operator Markdown path")
    winning_patterns_report.add_argument("--limit", required=False, type=int, default=10, help="Maximum surfaces/candidates to include")

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
    strategy_shortlist_report.add_argument("--resolution-date", required=False, help="Optional resolution date YYYY-MM-DD used to enrich shortlist rows with direct/latest and official status")
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

    paper_watchlist = subparsers.add_parser("paper-watchlist", help="Build an operator watchlist from a saved paper monitor JSON")
    paper_watchlist.add_argument("--input-json", required=True, help="Saved paper monitor JSON containing positions")
    paper_watchlist.add_argument("--output-json", required=False, help="Optional path to write full watchlist JSON")
    paper_watchlist.add_argument("--output-csv", required=False, help="Optional path to write an operator CSV table")
    paper_watchlist.add_argument("--output-md", required=False, help="Optional path to write an operator markdown table")
    paper_watchlist.add_argument("--compact", action="store_true", help="Print compact operator payload instead of full watchlist JSON")

    paper_ledger_place_parser = subparsers.add_parser("paper-ledger-place", help="Record a strict-limit paper ledger order from a refreshed candidate")
    paper_ledger_place_parser.add_argument("--candidate-json", required=True, help="Candidate JSON with source/orderbook refresh context")
    paper_ledger_place_parser.add_argument("--ledger-json", required=True, help="Ledger JSON to create or append")
    paper_ledger_place_parser.add_argument("--output-dir", required=False, default="data/polymarket", help="Directory for ledger JSON/CSV/Markdown artifacts")

    paper_ledger_refresh_parser = subparsers.add_parser("paper-ledger-refresh", help="Refresh strict-limit paper ledger MTM/PnL and actions")
    paper_ledger_refresh_parser.add_argument("--ledger-json", required=True, help="Ledger JSON to refresh in place")
    paper_ledger_refresh_parser.add_argument("--refresh-json", required=False, help="JSON containing refreshes and optional settlements")
    paper_ledger_refresh_parser.add_argument("--output-dir", required=False, default="data/polymarket", help="Directory for ledger JSON/CSV/Markdown artifacts")
    paper_ledger_refresh_parser.add_argument("--max-position-usdc", required=False, type=float, default=10.0, help="Filled spend at or above this cap emits HOLD_CAPPED")

    paper_ledger_report_parser = subparsers.add_parser("paper-ledger-report", help="Write strict-limit paper ledger JSON/CSV/Markdown artifacts")
    paper_ledger_report_parser.add_argument("--ledger-json", required=True, help="Ledger JSON to report")
    paper_ledger_report_parser.add_argument("--output-dir", required=False, default="data/polymarket", help="Directory for ledger JSON/CSV/Markdown artifacts")

    paper_autopilot_bridge = subparsers.add_parser("paper-autopilot-bridge", help="Append PAPER_STRICT/PAPER_MICRO live rows to a derived strict-limit paper ledger only")
    paper_autopilot_bridge.add_argument("--operator-json", required=True, help="Live readiness/operator artifact containing candidate rows")
    paper_autopilot_bridge.add_argument("--ledger-json", required=True, help="Derived paper ledger JSON to create or append")
    paper_autopilot_bridge.add_argument("--run-id", required=False, help="Run id stamped onto appended simulated paper orders")
    paper_autopilot_bridge.add_argument("--output-dir", required=False, default="data/polymarket", help="Directory for derived ledger JSON/CSV/Markdown artifacts")
    paper_autopilot_bridge.add_argument("--strict-gates", action="store_true", help="Fail if any row asks for a non-paper gate instead of skipping it")

    multi_profile_paper = subparsers.add_parser("multi-profile-paper-runner", help="Run the same weather shortlist through separate paper ledgers per StrategyProfile")
    multi_profile_paper.add_argument("--shortlist-json", required=True, help="Strategy shortlist JSON to replay across profiles")
    multi_profile_paper.add_argument("--run-id", required=False, help="Parent run id for the batch")
    multi_profile_paper.add_argument("--mode", choices=("shadow", "paper", "live_dry_run"), default="paper", help="Guarded read-only runner mode; live_dry_run never submits live orders")
    multi_profile_paper.add_argument("--profile-id", action="append", dest="profile_ids", help="Profile id to include; repeat for multiple profiles")
    multi_profile_paper.add_argument("--output-dir", required=False, default="data/polymarket", help="Directory for multi-profile paper artifacts")

    miro_seed_export_parser = subparsers.add_parser("miro-seed-export", help="Export a fact-only Miro/MiroFish seed markdown from a saved market/research payload")
    miro_seed_export_parser.add_argument("--input-json", required=False, help="JSON containing market and optional research_items")
    miro_seed_export_parser.add_argument("--market-id", required=False, help="Fetch market by id from the configured source")
    miro_seed_export_parser.add_argument("--source", choices=_VALID_SOURCES, default="live", help="Market source for --market-id")
    miro_seed_export_parser.add_argument("--output-md", required=True, help="Output markdown seed path")
    miro_seed_export_parser.add_argument("--output-manifest", required=False, help="Optional JSON manifest with MiroFish/MiroShark upload metadata")
    miro_seed_export_parser.add_argument("--target", choices=("mirofish", "miroshark", "both"), default="mirofish", help="Which simulation runtime recipe to prioritize")
    miro_seed_export_parser.add_argument("--base-url", default="http://localhost:5001", help="Local MiroFish/MiroShark base URL for generated curl commands")

    live_observer_config = subparsers.add_parser("live-observer-config", help="Inspect or update the paper-only live observer config")
    live_observer_config_sub = live_observer_config.add_subparsers(dest="live_observer_config_action")
    _add_config_arg(live_observer_config_sub.add_parser("show", help="Show redacted config and estimate"))
    live_observer_config_sub.choices["show"].add_argument("--json", action="store_true", help="Emit JSON")
    _add_config_arg(live_observer_config_sub.add_parser("estimate", help="Estimate live-observer storage"))
    set_scenario = live_observer_config_sub.add_parser("set-scenario", help="Set active observer scenario")
    set_scenario.add_argument("scenario", choices=("minimal", "realistic", "aggressive"))
    _add_config_arg(set_scenario)
    set_storage = live_observer_config_sub.add_parser("set-storage", help="Set observer storage backends")
    set_storage.add_argument("--primary", required=False)
    set_storage.add_argument("--analytics", required=False)
    set_storage.add_argument("--archive", required=False)
    _add_config_arg(set_storage)
    set_path = live_observer_config_sub.add_parser("set-path", help="Set observer base path")
    set_path.add_argument("--base-dir", required=True)
    _add_config_arg(set_path)
    enable_cmd = live_observer_config_sub.add_parser("enable", help="Enable collection/stream/profile")
    enable_cmd.add_argument("target", choices=("collection", "stream", "profile"))
    enable_cmd.add_argument("name", nargs="?")
    enable_cmd.add_argument("--reason", required=False)
    _add_config_arg(enable_cmd)
    disable_cmd = live_observer_config_sub.add_parser("disable", help="Disable collection/stream/profile")
    disable_cmd.add_argument("target", choices=("collection", "stream", "profile"))
    disable_cmd.add_argument("name", nargs="?")
    disable_cmd.add_argument("--reason", required=False)
    _add_config_arg(disable_cmd)

    live_observer = subparsers.add_parser("live-observer", help="Run the paper-only live observer")
    live_observer_sub = live_observer.add_subparsers(dest="live_observer_action")
    run_once = live_observer_sub.add_parser("run-once", help="Run one observer pass")
    run_once.add_argument("--source", choices=("fixture", "live"), default="fixture")
    run_once.add_argument("--dry-run", action="store_true")
    _add_config_arg(run_once)
    fast_collector = live_observer_sub.add_parser("fast-collector", help="Run fast event-trigger collector without reporting")
    fast_collector.add_argument("--source", choices=("fixture", "live"), default="live")
    fast_collector.add_argument("--dry-run", action="store_true")
    fast_collector.add_argument("--max-iterations", type=int, default=1)
    fast_collector.add_argument("--poll-interval-seconds", type=int, required=False)
    _add_config_arg(fast_collector)
    return parser


def _add_config_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default="config/weather_live_observer.yaml", help="Weather live observer YAML config path")


def _add_paper_cycle_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True, help="Paper cycle run id")
    parser.add_argument("--source", choices=_VALID_SOURCES, default="live", help="Market source")
    parser.add_argument("--limit", required=False, type=int, default=25, help="Maximum live markets to score")
    parser.add_argument("--bankroll-usd", required=False, type=float, help="Bankroll used for decision sizing")
    parser.add_argument("--requested-quantity", required=False, type=float, default=1.0, help="Requested quantity per tradeable market")
    parser.add_argument("--max-impact-bps", required=False, type=float, help="Override max executable price impact in bps")


def _print_analytics_export_counts(rows_by_table: dict[str, list[dict[str, Any]]]) -> None:
    for table in sorted(rows_by_table):
        print(f"analytics.{table}.rows={len(rows_by_table[table])}")


def _config_payload(config_path: str | Path) -> dict[str, Any]:
    config = load_live_observer_config(config_path)
    return {"config": asdict(config), "estimate": estimate_live_observer_storage(config).to_dict()}


def _handle_live_observer_config(args: argparse.Namespace) -> dict[str, Any]:
    action = args.live_observer_config_action
    config_path = Path(args.config)
    if action == "show":
        return _config_payload(config_path)
    if action == "estimate":
        config = load_live_observer_config(config_path)
        return estimate_live_observer_storage(config).to_dict()
    if action == "set-scenario":
        _replace_line_prefix(config_path, "active_scenario:", f"active_scenario: {args.scenario:<11} # prepared scenario; collection.enabled is the true ON/OFF switch")
        return {"active_scenario": args.scenario}
    if action == "set-storage":
        updates = {key: value for key, value in {"primary": args.primary, "analytics": args.analytics, "archive": args.archive}.items() if value is not None}
        _update_yaml_block(config_path, "storage", updates)
        return {"storage": updates}
    if action == "set-path":
        base = args.base_dir.rstrip("/")
        paths = {"base_dir": base, "jsonl_dir": f"{base}/jsonl", "parquet_dir": f"{base}/parquet", "reports_dir": f"{base}/reports", "manifests_dir": f"{base}/manifests"}
        _update_yaml_block(config_path, "paths", paths)
        return {"paths": paths}
    if action in {"enable", "disable"}:
        enabled = action == "enable"
        if args.target == "collection":
            _update_yaml_block(config_path, "collection", {"enabled": enabled, "reason": args.reason or action})
            return {"collection": {"enabled": enabled, "reason": args.reason or action}}
        block = "streams" if args.target == "stream" else "profiles"
        if not args.name:
            raise SystemExit(f"live-observer-config {action} {args.target} requires a name")
        _update_nested_yaml_block(config_path, block, args.name, {"enabled": enabled, "reason": args.reason or action})
        return {args.target: args.name, "enabled": enabled, "reason": args.reason or action}
    raise SystemExit(f"unknown live-observer-config action: {action}")


def _handle_live_observer(args: argparse.Namespace) -> dict[str, Any]:
    config = load_live_observer_config(args.config)
    if args.live_observer_action == "run-once":
        return run_live_observer_once(config, source=args.source, dry_run=args.dry_run).to_dict()
    if args.live_observer_action == "fast-collector":
        return run_live_observer_fast_collector(
            config,
            source=args.source,
            dry_run=args.dry_run,
            max_iterations=args.max_iterations,
            poll_interval_seconds=args.poll_interval_seconds,
        ).to_dict()
    raise SystemExit(f"unknown live-observer action: {args.live_observer_action}")


def _replace_line_prefix(path: Path, prefix: str, replacement: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    raise ValueError(f"missing YAML line prefix: {prefix}")


def _update_yaml_block(path: Path, block: str, updates: dict[str, Any]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = _find_yaml_block(lines, block)
    end = _find_yaml_block_end(lines, start)
    for key, value in updates.items():
        rendered = _yaml_scalar(value)
        prefix = f"  {key}:"
        for index in range(start + 1, end):
            if lines[index].startswith(prefix):
                comment = f"  #{lines[index].split('#', 1)[1]}" if "#" in lines[index] else ""
                lines[index] = f"  {key}: {rendered}{comment}"
                break
        else:
            lines.insert(end, f"  {key}: {rendered}")
            end += 1
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _update_nested_yaml_block(path: Path, block: str, name: str, updates: dict[str, Any]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    parent = _find_yaml_block(lines, block)
    parent_end = _find_yaml_block_end(lines, parent)
    nested = None
    for index in range(parent + 1, parent_end):
        if lines[index].startswith(f"  {name}:"):
            nested = index
            break
    if nested is None:
        raise ValueError(f"missing YAML block: {block}.{name}")
    end = nested + 1
    while end < parent_end and (lines[end].startswith("    ") or not lines[end].strip()):
        end += 1
    for key, value in updates.items():
        rendered = _yaml_scalar(value)
        prefix = f"    {key}:"
        for index in range(nested + 1, end):
            if lines[index].startswith(prefix):
                comment = f"  #{lines[index].split('#', 1)[1]}" if "#" in lines[index] else ""
                lines[index] = f"    {key}: {rendered}{comment}"
                break
        else:
            lines.insert(end, f"    {key}: {rendered}")
            end += 1
            parent_end += 1
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _find_yaml_block(lines: list[str], block: str) -> int:
    for index, line in enumerate(lines):
        if line.startswith(f"{block}:"):
            return index
    raise ValueError(f"missing YAML block: {block}")


def _find_yaml_block_end(lines: list[str], start: int) -> int:
    end = start + 1
    while end < len(lines) and (lines[end].startswith(" ") or not lines[end].strip()):
        end += 1
    return end


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "live-observer-config":
        print(json.dumps(_handle_live_observer_config(args)))
        return 0

    if args.command == "live-observer":
        print(json.dumps(_handle_live_observer(args)))
        return 0

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

    if args.command == "source-coverage":
        print(json.dumps(build_weather_source_coverage_report().to_dict()))
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
                    output_dir=Path(args.output_dir),
                    status_fetcher=resolution_status_for_market_id,
                )
            )
        )
        return 0

    if args.command == "import-weather-traders":
        print(json.dumps(import_weather_traders(args.classified_csv, args.registry_out, args.reverse_engineering_out, min_pnl=args.min_pnl)))
        return 0

    if args.command == "trader-profile":
        print(json.dumps(trader_profile(args.wallet, page_size=args.page_size)))
        return 0

    if args.command == "account-learning-backfill":
        print(json.dumps(write_account_learning_backfill_pipeline(args.input_json, args.output_dir, run_id=args.run_id)))
        return 0

    if args.command == "learning-cycle":
        if not args.dry_run:
            parser.error("learning-cycle requires --dry-run")
        if not args.no_network:
            parser.error("learning-cycle requires --no-network")
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        contract = build_learning_cycle_contract(
            run_id=args.run_id,
            output_dir=output_dir,
            max_accounts=args.max_accounts,
            trades_per_account=args.trades_per_account,
            lookback_days=args.lookback_days,
        )
        safety = validate_learning_cycle_safety(contract)
        contract_json = output_dir / "learning_cycle_contract.json"
        contract_json.write_text(json.dumps(contract, sort_keys=True) + "\n", encoding="utf-8")
        if args.learning_report_json:
            learning_report = json.loads(Path(args.learning_report_json).read_text(encoding="utf-8"))
            result = assemble_learning_cycle_result(
                run_id=args.run_id,
                output_dir=output_dir,
                learning_report=learning_report,
                max_accounts=args.max_accounts,
                trades_per_account=args.trades_per_account,
                lookback_days=args.lookback_days,
            )
            policy_json = output_dir / "learning_policy_actions.json"
            backfill_json = output_dir / "learning_backfill_plan.json"
            cycle_json = output_dir / "learning_cycle_result.json"
            summary_md = output_dir / "learning_cycle_summary.md"
            policy_json.write_text(json.dumps(result["policy"], sort_keys=True) + "\n", encoding="utf-8")
            backfill_json.write_text(json.dumps(result["backfill_plan"], sort_keys=True) + "\n", encoding="utf-8")
            cycle_json.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
            summary_md.write_text(render_learning_cycle_summary_markdown(result), encoding="utf-8")
            print(
                json.dumps(
                    {
                        "ok": result["ok"],
                        "paper_only": result["paper_only"],
                        "live_order_allowed": result["live_order_allowed"],
                        "no_real_order_placed": result["no_real_order_placed"],
                        "artifacts": {
                            "contract_json": str(contract_json),
                            "cycle_json": str(cycle_json),
                            "policy_json": str(policy_json),
                            "backfill_json": str(backfill_json),
                            "summary_md": str(summary_md),
                            "ledger_jsonl": result["ledger_path"],
                        },
                    },
                    separators=(",", ":"),
                )
            )
            return 0
        print(
            json.dumps(
                {
                    "ok": safety["ok"],
                    "paper_only": contract["paper_only"],
                    "live_order_allowed": contract["live_order_allowed"],
                    "artifacts": {"contract_json": str(contract_json)},
                },
                separators=(",", ":"),
            )
        )
        return 0

    if args.command == "account-data-source-manifest":
        print(json.dumps(compact_account_data_source_manifest(build_account_data_source_manifest())))
        return 0

    if args.command == "hf-account-trades-sample":
        print(
            json.dumps(
                write_hf_account_trades_sample(
                    args.input,
                    args.output_json,
                    wallets=args.wallets,
                    wallets_json=args.wallets_json,
                    limit=args.limit,
                )
            )
        )
        return 0

    if args.command == "account-resolution-coverage":
        print(json.dumps(write_resolution_coverage_report(args.trades_json, args.resolutions_json, args.output_json)))
        return 0

    if args.command == "enrich-trades-orderbook-context":
        print(json.dumps(write_orderbook_context_report(args.trades_json, args.orderbook_snapshots_json, args.output_json, max_staleness_seconds=args.max_staleness_seconds)))
        return 0

    if args.command == "build-account-decision-dataset":
        print(json.dumps(write_account_decision_dataset(args.trades_json, args.markets_snapshots_json, args.output_json, bucket_minutes=args.bucket_minutes, no_trade_per_trade=args.no_trade_per_trade)))
        return 0

    if args.command == "enrich-decision-weather-context":
        print(json.dumps(write_decision_weather_context(args.decision_dataset_json, args.forecast_snapshots_json, args.output_json, resolution_sources_json=args.resolution_sources_json)))
        return 0

    if args.command == "official-observation-backfill":
        print(json.dumps(write_official_observation_backfill(args.input_json, args.output_json)))
        return 0

    if args.command == "winner-pattern-engine":
        print(json.dumps(write_winner_pattern_engine(args.decision_context_json, args.resolved_trades_json, args.output_json, output_md=args.output_md, min_resolved_trades=args.min_resolved_trades, max_top1_pnl_share=args.max_top1_pnl_share)))
        return 0

    if args.command == "winner-pattern-paper-candidates":
        print(json.dumps(write_winner_pattern_paper_candidates(args.winner_patterns_json, args.current_markets_json, args.current_orderbooks_json, args.current_weather_context_json, args.output_json, output_md=args.output_md)))
        return 0

    if args.command == "winner-pattern-report":
        print(json.dumps(write_winner_pattern_operator_report(args.winner_patterns_json, args.paper_candidates_json, args.output_json, args.output_md, resolution_coverage_json=args.resolution_coverage_json, orderbook_context_json=args.orderbook_context_json)))
        return 0

    if args.command == "smoke-comparison":
        print(json.dumps(write_smoke_comparison(args.before_json, args.after_json, args.output_json, args.output_md)))
        return 0

    if args.command == "winner-pattern-pipeline":
        try:
            payload = run_winner_pattern_pipeline(
                trades_json=args.trades_json,
                resolutions_json=args.resolutions_json,
                orderbook_snapshots_json=args.orderbook_snapshots_json,
                market_snapshots_json=args.market_snapshots_json,
                forecast_snapshots_json=args.forecast_snapshots_json,
                output_dir=args.output_dir,
                allow_network=args.allow_network,
            )
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(payload))
        return 0

    if args.command == "backfill-account-trades":
        print(
            json.dumps(
                backfill_account_trades_from_followlist(
                    args.followlist,
                    args.out_json,
                    limit_accounts=args.limit_accounts,
                    trades_per_account=args.trades_per_account,
                )
            )
        )
        return 0

    if args.command == "import-account-trades":
        print(json.dumps(import_account_trades(args.trades_json, trades_out=args.trades_out, profiles_out=args.profiles_out)))
        return 0

    if args.command == "account-trades-backfill":
        print(json.dumps(load_account_trade_backfill(args.input_json)))
        return 0

    if args.command == "account-trades-import":
        print(json.dumps(write_account_trade_import(args.input_json, args.output_json)))
        return 0

    if args.command == "shadow-profiles-report":
        print(json.dumps(write_shadow_profile_report(args.trades_json, args.output_json, output_md=args.output_md)))
        return 0

    if args.command == "shadow-patterns-report":
        print(
            json.dumps(
                write_learned_shadow_patterns_artifacts(
                    dataset_json=args.dataset_json,
                    output_json=args.output_json,
                    output_md=args.output_md,
                    limit=args.limit,
                )
            )
        )
        return 0

    if args.command == "account-pattern-learning-digest":
        print(
            json.dumps(
                write_account_pattern_learning_digest(
                    validation_json=args.validation_json,
                    live_radar_json=args.live_radar_json,
                    output_json=args.output_json,
                    output_md=args.output_md,
                )
            )
        )
        return 0

    if args.command == "promoted-profile-opportunity-dataset":
        print(
            json.dumps(
                write_promoted_profile_opportunity_dataset_artifact(
                    promoted_profiles_json=args.promoted_profiles_json,
                    markets_json=args.markets_json,
                    dataset_out=args.dataset_out,
                )
            )
        )
        return 0

    if args.command == "shadow-profile-report":
        print(
            json.dumps(
                write_shadow_profile_artifacts(
                    weather_trades_json=args.weather_trades_json,
                    markets_json=args.markets_json,
                    dataset_out=args.dataset_out,
                    report_out=args.report_out,
                    limit=args.limit,
                    accounts_csv=args.accounts_csv,
                    limit_accounts=args.limit_accounts,
                )
            )
        )
        return 0

    if args.command == "shadow-profiles-deep-dive":
        if not args.wallet and not args.handle:
            parser.error("shadow-profiles-deep-dive requires --wallet or --handle")
        print(json.dumps(write_shadow_profile_deep_dive(args.profiles_json, wallet=args.wallet, handle=args.handle, output_md=args.output_md)))
        return 0

    if args.command == "shadow-paper-runner":
        print(
            json.dumps(
                run_shadow_paper_runner_artifact(
                    dataset_json=args.dataset_json,
                    orderbooks_json=args.orderbooks_json,
                    forecasts_json=args.forecasts_json,
                    run_id=args.run_id,
                    output_json=args.output_json,
                    skip_diagnostics_json=args.skip_diagnostics_json,
                    resolutions_json=args.resolutions_json,
                    historical_forecasts_json=args.historical_forecasts_json,
                    profile_configs_json=args.profile_configs_json,
                    promoted_profiles_json=args.promoted_profiles_json,
                    historical_profile_rules_json=args.historical_profile_rules_json,
                    stress_overlay_json=args.stress_overlay_json,
                    max_order_usdc=args.max_order_usdc,
                )
            )
        )
        return 0

    if args.command == "market-metadata-resolution":
        print(json.dumps(run_market_metadata_resolution_artifact(markets_json=args.markets_json, output_json=args.output_json)))
        return 0

    if args.command == "account-trade-resolution":
        print(json.dumps(run_account_trade_resolution_artifact(trades_json=args.trades_json, resolutions_json=args.resolutions_json, output_json=args.output_json)))
        return 0

    if args.command == "shadow-profile-evaluator":
        print(
            json.dumps(
                run_shadow_profile_evaluator_artifact(
                    paper_orders_json=args.paper_orders_json,
                    trade_resolution_json=args.trade_resolution_json,
                    output_json=args.output_json,
                    output_md=args.output_md,
                    handoff_overrides={
                        "dataset_json": args.handoff_dataset_json,
                        "orderbooks_json": args.handoff_orderbooks_json,
                        "forecasts_json": args.handoff_forecasts_json,
                        "stress_overlay_json": args.handoff_stress_overlay_json,
                        "historical_profile_rules_json": args.handoff_historical_profile_rules_json,
                        "run_id": args.handoff_run_id,
                        "paper_orders_json": args.handoff_paper_orders_json,
                        "exposure_json": args.handoff_exposure_json,
                        "exposure_md": args.handoff_exposure_md,
                    },
                )
            )
        )
        return 0

    if args.command == "historical-profile-rules":
        print(
            json.dumps(
                run_historical_profile_rule_candidates_artifact(
                    trade_resolution_json=args.trade_resolution_json,
                    output_json=args.output_json,
                    output_md=args.output_md,
                )
            )
        )
        return 0

    if args.command == "shadow-profile-learning-report":
        print(
            json.dumps(
                run_shadow_profile_learning_report_artifact(
                    evaluation_json=args.evaluation_json,
                    paper_orders_json=args.paper_orders_json,
                    output_json=args.output_json,
                    output_md=args.output_md,
                )
            )
        )
        return 0

    if args.command == "shadow-profile-exposure-preview":
        print(
            json.dumps(
                run_shadow_profile_exposure_preview_artifact(
                    paper_orders_json=args.paper_orders_json,
                    output_json=args.output_json,
                    output_md=args.output_md,
                )
            )
        )
        return 0

    if args.command == "strategy-report":
        print(json.dumps(strategy_report(args.reverse_engineering_json)))
        return 0

    if args.command == "strategy-profiles":
        report = compact_strategy_profile_report()
        if args.output_md:
            output_path = Path(args.output_md)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(strategy_profiles_markdown(), encoding="utf-8")
            report.setdefault("artifacts", {})["output_md"] = str(output_path)
        print(json.dumps(report))
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

    if args.command == "export-analytics-clickhouse":
        if not args.shortlist_json and not args.paper_ledger_json and not args.execution_events_json and not args.strategy_config_json:
            raise ValueError("provide --shortlist-json, --paper-ledger-json, --execution-events-json, --strategy-config-json, or a combination")

        rows_by_table: dict[str, list[dict[str, Any]]] = {
            "profile_decisions": [],
            "debug_decisions": [],
            "profile_metrics": [],
            "strategy_metrics": [],
            "strategy_signals": [],
            "strategy_configs": [],
            "execution_events": [],
            "paper_orders": [],
            "paper_positions": [],
            "paper_pnl_snapshots": [],
        }
        if args.shortlist_json:
            payload = json.loads(Path(args.shortlist_json).read_text())
            events = profile_decision_events_from_shortlist(payload)
            debug_events = debug_decision_events_from_shortlist(payload)
            signal_events = strategy_signal_events_from_shortlist(payload)
            metric_events = [*build_profile_metric_events(events), *build_strategy_metric_events(events)]
            rows_by_table["profile_decisions"] = [serialize_event(event) for event in events]
            rows_by_table["debug_decisions"] = [serialize_event(event) for event in debug_events]
            rows_by_table["strategy_signals"] = [serialize_event(event) for event in signal_events]
            rows_by_table["profile_metrics"] = [serialize_event(event) for event in metric_events if event.table == "profile_metrics"]
            rows_by_table["strategy_metrics"] = [serialize_event(event) for event in metric_events if event.table == "strategy_metrics"]
        if args.paper_ledger_json:
            ledger = json.loads(Path(args.paper_ledger_json).read_text())
            order_events = paper_order_events_from_ledger(ledger)
            position_events = paper_position_events_from_ledger(ledger)
            pnl_events = paper_pnl_snapshot_events_from_ledger(ledger)
            rows_by_table["paper_orders"] = [serialize_event(event) for event in order_events]
            rows_by_table["paper_positions"] = [serialize_event(event) for event in position_events]
            rows_by_table["paper_pnl_snapshots"] = [serialize_event(event) for event in pnl_events]
        if args.execution_events_json:
            execution_payload = json.loads(Path(args.execution_events_json).read_text())
            execution_events = execution_events_from_payload(execution_payload)
            rows_by_table["execution_events"] = [serialize_event(event) for event in execution_events]
        if args.strategy_config_json:
            config_events = StrategyConfigStore(Path(args.strategy_config_json)).list_config_events()
            rows_by_table["strategy_configs"] = [serialize_event(event) for event in config_events]

        if args.dry_run:
            _print_analytics_export_counts(rows_by_table)
            print("analytics.enabled=false")
            return 0
        writer = create_clickhouse_writer_from_env()
        if writer is None:
            _print_analytics_export_counts(rows_by_table)
            print("analytics.enabled=false")
            return 0
        for table, rows in rows_by_table.items():
            writer.insert_rows(table, rows)
        _print_analytics_export_counts(rows_by_table)
        print("analytics.enabled=true")
        return 0

    if args.command == "operator-refresh":
        payload = poll_live_operator_artifact(
            args.input_json,
            output_json=args.output_json,
            source=args.source,
            resolution_date=args.resolution_date,
            operator_limit=args.operator_limit,
            refresh_resolution_status=not bool(args.skip_resolution_status),
            refresh_orderbook=not bool(args.skip_orderbook),
            iterations=args.iterations,
            poll_interval_seconds=args.poll_interval_seconds,
            storage_backend=args.storage_backend,
            storage_dry_run=args.storage_dry_run,
        )
        print(json.dumps(compact_operator_refresh_report(payload) if args.output_json else payload))
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

    if args.command == "wallet-sizing-priors":
        report = wallet_sizing_priors_report(args.input, args.output)
        print(json.dumps(report))
        return 0

    if args.command == "winning-patterns-report":
        report = write_winning_patterns_operator_report(
            classified_summary_json=args.classified_summary_json,
            continued_summary_json=args.continued_summary_json,
            strategy_patterns_json=args.strategy_patterns_json,
            strategy_report_json=args.strategy_report_json,
            future_consensus_json=args.future_consensus_json,
            orderbook_bridge_json=args.orderbook_bridge_json,
            output_json=args.output_json,
            output_md=args.output_md,
            limit=args.limit,
        )
        print(json.dumps(compact_winning_patterns_operator_report(report)))
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

    if args.command == "paper-watchlist":
        report = write_paper_watchlist_report(args.input_json, output_json=args.output_json)
        report_source = args.output_json or args.input_json
        tmp_path: Path | None = None
        if (args.output_md or args.output_csv) and not args.output_json:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
                tmp_path = Path(handle.name)
                json.dump(report, handle, indent=2, sort_keys=True)
            report_source = str(tmp_path)
        try:
            if args.output_csv:
                write_paper_watchlist_csv(report_source, args.output_csv)
            if args.output_md:
                write_paper_watchlist_markdown(report_source, args.output_md)
        finally:
            if tmp_path:
                tmp_path.unlink(missing_ok=True)
        if args.compact:
            print(
                json.dumps(
                    compact_paper_watchlist_report(
                        report,
                        output_json=args.output_json,
                        output_csv=args.output_csv,
                        output_md=args.output_md,
                    )
                )
            )
        else:
            print(json.dumps(report))
        return 0

    if args.command == "paper-ledger-place":
        candidate = load_candidate(args.candidate_json)
        ledger = load_paper_ledger(args.ledger_json) if Path(args.ledger_json).exists() else {"orders": []}
        payload = paper_ledger_place(candidate, ledger=ledger)
        _write_json_atomic(Path(args.ledger_json), payload)
        artifact = write_paper_ledger_artifacts(payload, output_dir=args.output_dir)
        print(json.dumps(artifact))
        return 0

    if args.command == "paper-ledger-refresh":
        ledger = load_paper_ledger(args.ledger_json)
        refreshes, settlements = load_refresh_payload(args.refresh_json) if args.refresh_json else ({}, {})
        payload = paper_ledger_refresh(ledger, refreshes=refreshes, settlements=settlements, max_position_usdc=args.max_position_usdc)
        _write_json_atomic(Path(args.ledger_json), payload)
        artifact = write_paper_ledger_artifacts(payload, output_dir=args.output_dir)
        print(json.dumps(artifact))
        return 0

    if args.command == "paper-ledger-report":
        payload = write_paper_ledger_artifacts(load_paper_ledger(args.ledger_json), output_dir=args.output_dir)
        print(json.dumps(payload))
        return 0

    if args.command == "paper-autopilot-bridge":
        operator_artifact = json.loads(Path(args.operator_json).read_text(encoding="utf-8"))
        ledger = load_paper_ledger(args.ledger_json) if Path(args.ledger_json).exists() else {"orders": []}
        payload = build_paper_autopilot_ledger(
            operator_artifact,
            ledger=ledger,
            run_id=args.run_id,
            allow_unknown_gate=not args.strict_gates,
        )
        _write_json_atomic(Path(args.ledger_json), payload)
        artifact = write_paper_ledger_artifacts(payload, output_dir=args.output_dir)
        artifact["paper_autopilot_summary"] = payload.get("paper_autopilot_summary", {})
        artifact["paper_autopilot_skipped"] = payload.get("paper_autopilot_skipped", [])
        print(json.dumps(artifact))
        return 0

    if args.command == "multi-profile-paper-runner":
        result = run_multi_profile_paper_batch(
            load_shortlist_payload(args.shortlist_json),
            profile_ids=args.profile_ids,
            run_id=args.run_id,
            mode=args.mode,
        )
        print(json.dumps(write_multi_profile_paper_artifacts(result, output_dir=args.output_dir)))
        return 0

    if args.command == "miro-seed-export":
        print(
            json.dumps(
                miro_seed_export(
                    args.input_json,
                    args.output_md,
                    market_id=args.market_id,
                    source=args.source,
                    output_manifest=args.output_manifest,
                    target=args.target,
                    base_url=args.base_url,
                )
            )
        )
        return 0

    return 0


def wallet_sizing_priors_report(input_json: str | Path, output_json: str | Path) -> dict[str, Any]:
    input_path = Path(input_json)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("wallet-sizing-priors input JSON must be an object")
    report = build_wallet_sizing_priors(payload)
    report["source"] = str(input_path)
    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def miro_seed_export(
    input_json: str | Path | None,
    output_md: str | Path,
    *,
    market_id: str | None = None,
    source: str = "live",
    output_manifest: str | Path | None = None,
    target: str = "mirofish",
    base_url: str = "http://localhost:5001",
) -> dict[str, Any]:
    if not input_json and not market_id:
        raise ValueError("miro-seed-export requires --input-json or --market-id")

    research_items: list[Any] = []
    if input_json:
        payload = json.loads(Path(input_json).read_text())
        if isinstance(payload, dict):
            market = payload.get("market", payload)
            research_items = payload.get("research_items", payload.get("research", []))
        else:
            raise ValueError("input JSON must be an object")
    else:
        market = get_market_by_id(str(market_id), source=source)

    if not isinstance(market, dict):
        raise ValueError("input JSON market must be an object")
    if not isinstance(research_items, list):
        research_items = []
    clean_research_items = [item for item in research_items if isinstance(item, dict)]
    markdown = build_miro_seed_markdown(market, clean_research_items)
    output_path = Path(output_md)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    resolved_market_id = str(market.get("id") or market_id or "")
    question = str(market.get("question") or market.get("title") or "Untitled market")
    if target not in {"mirofish", "miroshark", "both"}:
        raise ValueError("target must be 'mirofish', 'miroshark', or 'both'")
    project_name = f"Polymarket Miro seed - {resolved_market_id or question[:48]}"
    manifest = _build_miro_upload_manifest(
        seed_paths=[output_path],
        simulation_requirement=question,
        project_name=project_name,
        base_url=base_url,
        target=target,
    )
    if output_manifest:
        manifest_path = Path(output_manifest)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    mirofish_upload = None
    if manifest.get("mirofish_upload") is not None:
        mirofish_upload = {
            "endpoint": manifest["mirofish_upload"]["endpoint"],
            "files": manifest["files"],
            "manifest": str(output_manifest) if output_manifest else None,
        }
    miroshark_ask = None
    if manifest.get("miroshark_ask") is not None:
        miroshark_ask = {
            "endpoint": manifest["miroshark_ask"]["endpoint"],
            "manifest": str(output_manifest) if output_manifest else None,
        }
    return {
        "output_md": str(output_path),
        "market_id": resolved_market_id,
        "source": source if market_id else "input_json",
        "target": target,
        "paper_only": True,
        "prices_excluded": True,
        "research_items": len(clean_research_items),
        "mirofish_upload": mirofish_upload,
        "miroshark_ask": miroshark_ask,
    }


def _build_miro_upload_manifest(
    *,
    seed_paths: Sequence[Path],
    simulation_requirement: str,
    project_name: str,
    base_url: str = "http://localhost:5001",
    target: str = "mirofish",
) -> dict[str, Any]:
    files = [str(path) for path in seed_paths]
    mirofish_upload = _build_mirofish_upload_recipe(files, simulation_requirement, project_name, base_url=base_url)
    miroshark_ask = _build_miroshark_ask_recipe(files, simulation_requirement, base_url=base_url)
    return {
        "target": target,
        "base_url": base_url,
        "primary_endpoint": "/api/simulation/ask" if target == "miroshark" else "/api/graph/ontology/generate",
        "endpoint": "/api/graph/ontology/generate",
        "method": "POST",
        "content_type": "multipart/form-data",
        "files": files,
        "simulation_requirement": simulation_requirement,
        "project_name": project_name,
        "prices_excluded": True,
        "paper_only": True,
        "live_order_allowed": False,
        "compatible_endpoints": [
            "/api/graph/ontology/generate",
            "/api/graph/task/{task_id}",
            "/api/graph/project/{project_id}",
            "/api/simulation/ask",
            "/api/simulation/create",
            "/api/simulation/prepare",
            "/api/simulation/start",
            "/api/report/{project_id}",
            "/api/report/{simulation_id}",
        ],
        "follow_up_endpoints": [
            "/api/graph/task/{task_id}",
            "/api/graph/project/{project_id}",
            "/api/simulation/create",
            "/api/simulation/prepare",
            "/api/simulation/start",
            "/api/report/{project_id}",
        ],
        "mirofish_upload": mirofish_upload if target in {"mirofish", "both"} else None,
        "miroshark_ask": miroshark_ask if target in {"miroshark", "both"} else None,
        "miroshark_ask_payload": miroshark_ask["payload"],
        "curl_command": mirofish_upload["curl_command"],
    }


def _build_mirofish_upload_recipe(files: Sequence[str], simulation_requirement: str, project_name: str, *, base_url: str) -> dict[str, Any]:
    curl_parts = [
        "curl",
        "-X",
        "POST",
        f"{base_url}/api/graph/ontology/generate",
        *[part for path in files for part in ("-F", f"files=@{path}")],
        "-F",
        f"simulation_requirement={simulation_requirement}",
        "-F",
        f"project_name={project_name}",
    ]
    return {
        "endpoint": "/api/graph/ontology/generate",
        "method": "POST",
        "content_type": "multipart/form-data",
        "files": list(files),
        "form_fields": {
            "simulation_requirement": simulation_requirement,
            "project_name": project_name,
        },
        "curl_command": " ".join(shlex.quote(part) for part in curl_parts),
    }


def _build_miroshark_ask_recipe(files: Sequence[str], simulation_requirement: str, *, base_url: str) -> dict[str, Any]:
    payload = {
        "question": simulation_requirement,
        "seed_document_paths": list(files),
        "paper_only": True,
        "live_order_allowed": False,
    }
    curl_parts = [
        "curl",
        "-X",
        "POST",
        f"{base_url}/api/simulation/ask",
        "-H",
        "Content-Type: application/json",
        "--data",
        json.dumps(payload, sort_keys=True),
    ]
    return {
        "endpoint": "/api/simulation/ask",
        "method": "POST",
        "content_type": "application/json",
        "payload": payload,
        "curl_command": " ".join(shlex.quote(part) for part in curl_parts),
    }


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(tmp_name).replace(path)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise


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


def trader_profile(wallet: str, *, page_size: int = 50) -> dict[str, Any]:
    return fetch_trader_strategy_profile(wallet, page_size=page_size).to_dict()


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
    skip_orderbook: bool = False,
) -> dict[str, Any]:
    shortlist_payload = _operator_refresh_shortlist_payload(payload)
    enrich_shortlist_with_resolution_status(shortlist_payload, source=source, date=resolution_date)
    if skip_orderbook:
        execution_refreshed = 0
        execution_errors = 0
    else:
        enrich_shortlist_with_execution_snapshot(shortlist_payload)
        execution_refreshed = _execution_snapshot_refreshed_count(shortlist_payload)
        execution_errors = _execution_snapshot_error_count(shortlist_payload)
    attach_live_readiness(shortlist_payload)
    operator = build_operator_shortlist_report(shortlist_payload, limit=operator_limit)
    artifacts = {"source_operator_refresh_input": source_input_json}
    rows = [row for row in shortlist_payload.get("shortlist", []) if isinstance(row, dict)]
    return {
        "summary": {
            "paper_only": True,
            "input_kind": _operator_refresh_input_kind(payload),
            "rows": len(shortlist_payload.get("shortlist", [])),
            "resolution_status_refreshed": _resolution_status_refreshed_count(shortlist_payload),
            "execution_snapshot_refreshed": execution_refreshed,
            "execution_snapshot_errors": execution_errors,
            "operator_watchlist_rows": len(operator.get("watchlist", [])),
            **live_readiness_summary(rows),
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
    return sum(
        1
        for row in payload.get("shortlist", [])
        if isinstance(row, dict)
        and any(
            row.get(key) is not None
            for key in (
                "resolution_status",
                "latest_direct",
                "official_daily_extract",
                "provisional_outcome",
                "confirmed_outcome",
                "resolution_action_operator",
            )
        )
    )


def _execution_snapshot_refreshed_count(payload: dict[str, Any]) -> int:
    return sum(1 for row in payload.get("shortlist", []) if isinstance(row, dict) and row.get("execution_snapshot"))


def _execution_snapshot_error_count(payload: dict[str, Any]) -> int:
    return sum(1 for row in payload.get("shortlist", []) if isinstance(row, dict) and row.get("execution_refresh_error"))


def _compact_execution_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    book = snapshot.get("book") if isinstance(snapshot.get("book"), dict) else {}
    yes = book.get("yes") if isinstance(book.get("yes"), dict) else {}
    no = book.get("no") if isinstance(book.get("no"), dict) else {}
    spread = snapshot.get("spread") if isinstance(snapshot.get("spread"), dict) else {}
    return {
        "best_bid_yes": yes.get("best_bid"),
        "best_ask_yes": yes.get("best_ask"),
        "best_bid_no": no.get("best_bid"),
        "best_ask_no": no.get("best_ask"),
        "spread_yes": spread.get("yes"),
        "spread_no": spread.get("no"),
        "yes_bid_depth_usd": yes.get("bid_depth_usd"),
        "yes_ask_depth_usd": yes.get("ask_depth_usd"),
        "no_bid_depth_usd": no.get("bid_depth_usd"),
        "no_ask_depth_usd": no.get("ask_depth_usd"),
        "fetched_at": snapshot.get("fetched_at"),
    }


def enrich_shortlist_with_execution_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    for row in [item for item in report.get("shortlist", []) if isinstance(item, dict)]:
        market_id = str(row.get("market_id") or "")
        if not market_id:
            continue
        try:
            row["execution_snapshot"] = _compact_execution_snapshot(fetch_market_execution_snapshot(market_id))
            row.pop("execution_refresh_error", None)
        except Exception as exc:
            row["execution_refresh_error"] = str(exc)
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
        return date_type.fromisoformat(raw_value).year
    except ValueError:
        return None


def _parse_month_day(raw_value: str, *, year: int) -> str | None:
    for fmt in ("%b %d", "%B %d"):
        try:
            parsed = datetime.strptime(raw_value, fmt)
        except ValueError:
            continue
        return date_type(year, parsed.month, parsed.day).isoformat()
    return None

def poll_live_operator_artifact(
    input_json: str | Path,
    *,
    output_json: str | Path | None = None,
    source: str | None = None,
    resolution_date: str | None = None,
    operator_limit: int = 10,
    refresh_resolution_status: bool = True,
    refresh_orderbook: bool = True,
    iterations: int = 1,
    poll_interval_seconds: float = 0.0,
    storage_backend: str = "noop",
    storage_dry_run: bool = False,
) -> dict[str, Any]:
    input_path = Path(input_json)
    last_payload: dict[str, Any] | None = None
    for index in range(max(int(iterations), 1)):
        payload = json.loads(input_path.read_text())
        if not isinstance(payload, dict):
            raise ValueError("input JSON must be an object")
        resolved_source = _operator_refresh_source(payload, source)
        if refresh_resolution_status:
            last_payload = build_operator_refresh_report(
                payload,
                source=resolved_source,
                resolution_date=resolution_date or date_type.today().isoformat(),
                operator_limit=operator_limit,
                source_input_json=str(input_path),
                skip_orderbook=not refresh_orderbook,
            )
        else:
            shortlist_payload = _operator_refresh_shortlist_payload(payload)
            if refresh_orderbook:
                enrich_shortlist_with_execution_snapshot(shortlist_payload)
            attach_live_readiness(shortlist_payload)
            operator = build_operator_shortlist_report(shortlist_payload, limit=operator_limit)
            rows = [row for row in shortlist_payload.get("shortlist", []) if isinstance(row, dict)]
            last_payload = {
                "summary": {
                    "paper_only": True,
                    "input_kind": _operator_refresh_input_kind(payload),
                    "rows": len(shortlist_payload.get("shortlist", [])),
                    "resolution_status_refreshed": 0,
                    "execution_snapshot_refreshed": _execution_snapshot_refreshed_count(shortlist_payload),
                    "execution_snapshot_errors": _execution_snapshot_error_count(shortlist_payload),
                    "operator_watchlist_rows": len(operator.get("watchlist", [])),
                    **live_readiness_summary(rows),
                },
                "shortlist": shortlist_payload.get("shortlist", []),
                "operator": operator,
                "artifacts": {"source_operator_refresh_input": str(input_path)},
            }
        if storage_backend != "noop" or storage_dry_run:
            storage_summary = write_live_observer_payload_to_storage(
                last_payload,
                backend=storage_backend,
                dry_run=storage_dry_run,
            )
        else:
            storage_summary = write_live_observer_payload_to_storage(last_payload, backend="noop", dry_run=False)
        last_payload["storage"] = storage_summary
        last_payload.setdefault("summary", {}).update(storage_summary)
        if output_json:
            output_path = Path(output_json)
            assert_not_unmounted_truenas_path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            last_payload.setdefault("artifacts", {})["output_json"] = str(output_path)
            output_path.write_text(json.dumps(last_payload, indent=2, sort_keys=True))
        if index < max(int(iterations), 1) - 1 and poll_interval_seconds > 0:
            time.sleep(float(poll_interval_seconds))
    assert last_payload is not None
    return last_payload


def refresh_live_operator_artifact(
    input_json: str | Path,
    *,
    output_json: str | Path | None = None,
    source: str | None = None,
    resolution_date: str | None = None,
    operator_limit: int = 10,
    refresh_resolution_status: bool = True,
    refresh_orderbook: bool = True,
) -> dict[str, Any]:
    input_path = Path(input_json)
    payload = json.loads(input_path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("input JSON must be an object")

    artifact_type = _operator_refresh_artifact_type(payload)
    resolved_source = _operator_refresh_source(payload, source)
    shortlist = _operator_refresh_shortlist(payload, artifact_type=artifact_type)
    refreshed_resolution = 0
    refreshed_orderbook = 0

    report = {
        "run_id": payload.get("run_id"),
        "source": resolved_source,
        "summary": {},
        "shortlist": shortlist,
        "artifacts": {
            **(payload.get("artifacts", {}) if isinstance(payload.get("artifacts"), dict) else {}),
            "source_input_json": str(input_path),
        },
    }

    if refresh_resolution_status and resolution_date:
        enrich_shortlist_with_resolution_status(report, source=resolved_source, date=resolution_date)
        refreshed_resolution = _rows_with_resolution_status(report["shortlist"])

    if refresh_orderbook:
        refreshed_orderbook = _refresh_shortlist_orderbooks(report["shortlist"], source=resolved_source)

    report["operator"] = build_operator_shortlist_report(report, limit=operator_limit)
    report["summary"] = {
        "input_artifact_type": artifact_type,
        "source": resolved_source,
        "shortlisted": len(report["shortlist"]),
        "operator_watchlist": len(report["operator"].get("watchlist", [])),
        "resolution_status_refreshed": refreshed_resolution,
        "order_book_refreshed": refreshed_orderbook,
        "paper_only": True,
    }
    if output_json:
        output_path = Path(output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        report["artifacts"]["output_json"] = str(output_path)
        report["operator"].setdefault("artifacts", {})["output_json"] = str(output_path)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


def _operator_refresh_artifact_type(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("shortlist"), list):
        return "strategy_shortlist"
    if isinstance(payload.get("watchlist"), list):
        return "operator_report"
    if isinstance(payload.get("operator"), dict) and isinstance(payload["operator"].get("watchlist"), list):
        return "strategy_shortlist_with_operator"
    raise ValueError("input JSON must contain a shortlist or operator watchlist")


def _operator_refresh_source(payload: dict[str, Any], source: str | None) -> str:
    resolved = str(source or payload.get("source") or "live")
    if resolved not in _VALID_SOURCES:
        raise ValueError("source must be 'fixture' or 'live'")
    return resolved


def _operator_refresh_shortlist(payload: dict[str, Any], *, artifact_type: str) -> list[dict[str, Any]]:
    if artifact_type.startswith("strategy_shortlist"):
        return [dict(row) for row in payload.get("shortlist", []) if isinstance(row, dict)]
    return [_shortlist_row_from_operator_watch(row) for row in payload.get("watchlist", []) if isinstance(row, dict)]


def _shortlist_row_from_operator_watch(row: dict[str, Any]) -> dict[str, Any]:
    refreshed = dict(row)
    if "blocker" in refreshed and "execution_blocker" not in refreshed:
        refreshed["execution_blocker"] = refreshed.get("blocker")
    if "next" in refreshed and "next_actions" not in refreshed:
        refreshed["next_actions"] = list(refreshed.get("next") or [])
    resolution_status = refreshed.pop("resolution_status", None)
    if isinstance(resolution_status, dict):
        refreshed["latest_direct"] = resolution_status.get("latest_direct")
        refreshed["official_daily_extract"] = resolution_status.get("official_daily_extract")
        refreshed["provisional_outcome"] = resolution_status.get("provisional_outcome")
        refreshed["confirmed_outcome"] = resolution_status.get("confirmed_outcome")
        refreshed["resolution_action_operator"] = resolution_status.get("action_operator")
    return refreshed


def _rows_with_resolution_status(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if any(row.get(key) is not None for key in ("latest_direct", "official_daily_extract", "provisional_outcome", "confirmed_outcome", "resolution_action_operator")))


def _refresh_shortlist_orderbooks(rows: list[dict[str, Any]], *, source: str) -> int:
    refreshed = 0
    for row in rows:
        market_id = str(row.get("market_id") or "")
        if not market_id:
            continue
        try:
            market = normalize_market_record(get_market_by_id(market_id, source=source))
            execution = build_execution_features(market)
        except Exception as exc:
            row["order_book_refresh_error"] = str(exc)
            continue
        row["yes_price"] = market.get("yes_price")
        row["best_bid"] = market.get("best_bid")
        row["best_ask"] = market.get("best_ask")
        row["spread"] = execution.spread
        row["order_book_depth_usd"] = execution.order_book_depth_usd
        row["hours_to_resolution"] = execution.hours_to_resolution
        row["book_depth_source"] = market.get("book_depth_source")
        refreshed += 1
    return refreshed


def build_strategy_shortlist_report(
    strategy_payload: dict[str, Any],
    opportunity_payload: dict[str, Any],
    surface_payload: dict[str, Any],
    *,
    run_id: str,
    source: str,
    limit: int = 25,
    operator_limit: int | None = None,
    resolution_date: str | None = None,
    artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    shortlist_payload = build_strategy_shortlist(strategy_payload, opportunity_payload, surface_payload, limit=limit)
    generated_artifacts = dict(artifacts or {})
    generated_artifacts.setdefault("generated_reports", ["strategy_report", "opportunity_report", "event_surface", "shortlist"])
    report = {
        **shortlist_payload,
        "run_id": run_id,
        "source": source,
        "artifacts": generated_artifacts,
        "strategy_report": strategy_payload,
        "opportunity_report": opportunity_payload,
        "event_surface": surface_payload,
    }
    if resolution_date:
        enrich_shortlist_with_resolution_status(report, source=source, date=resolution_date)
    if operator_limit is not None:
        generated_artifacts["generated_reports"].append("operator")
        report["operator"] = build_operator_shortlist_report(report, limit=operator_limit)
    return report


def enrich_shortlist_with_resolution_status(report: dict[str, Any], *, source: str, date: str) -> dict[str, Any]:
    for row in [item for item in report.get("shortlist", []) if isinstance(item, dict)]:
        market_id = str(row.get("market_id") or "")
        if not market_id:
            continue
        row_date = _resolution_date_for_shortlist_row(row, reference_date=date)
        try:
            status = resolution_status_for_market_id(market_id, source=source, date=row_date)
        except Exception as exc:
            row["resolution_status_error"] = str(exc)
            continue
        row["resolution_status_date"] = row_date
        row["resolution_status"] = _compact_resolution_status(status)
        row["latest_direct"] = status.get("latest_direct")
        row["official_daily_extract"] = status.get("official_daily_extract")
        row["provisional_outcome"] = status.get("provisional_outcome")
        row["confirmed_outcome"] = status.get("confirmed_outcome")
        row["resolution_action_operator"] = status.get("action_operator")
        if isinstance(status.get("latency"), dict):
            row["resolution_latency"] = status.get("latency")
        source_route = status.get("source_route")
        if isinstance(source_route, dict):
            row["source_direct"] = bool(source_route.get("direct"))
            if source_route.get("provider"):
                row["source_provider"] = source_route.get("provider")
            if source_route.get("station_code"):
                row["source_station_code"] = source_route.get("station_code")
            if source_route.get("latency_tier"):
                row["source_latency_tier"] = source_route.get("latency_tier")
            if source_route.get("latency_priority"):
                row["source_latency_priority"] = source_route.get("latency_priority")
            if source_route.get("polling_focus"):
                row["source_polling_focus"] = source_route.get("polling_focus")
            if source_route.get("latest_url"):
                row["source_latest_url"] = source_route.get("latest_url")
            if source_route.get("history_url"):
                row["source_history_url"] = source_route.get("history_url")
    return report


def _resolution_date_for_shortlist_row(row: dict[str, Any], *, reference_date: str) -> str:
    raw_date = str(row.get("date") or "").strip()
    if not raw_date:
        return reference_date
    year = date_type.fromisoformat(reference_date).year
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(f"{raw_date} {year}", fmt).date().isoformat()
        except ValueError:
            continue
    return reference_date


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
    return build_strategy_shortlist_report(
        strategy_payload,
        opportunity_payload,
        surface_payload,
        run_id=args.run_id,
        source=args.source,
        limit=args.limit,
        operator_limit=getattr(args, "operator_limit", None),
        resolution_date=getattr(args, "resolution_date", None),
        artifacts={"reverse_engineering_json": str(args.reverse_engineering_json)},
    )


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
    _annotate_source_lag_seconds(bundle, now=_utc_now())
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



def station_source_plan_for_market_id(
    market_id: str,
    *,
    source: str = "live",
    start_date: str | None = None,
    end_date: str | None = None,
    client: Any | None = None,
    now: datetime | None = None,
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
    binding = build_station_binding(structure, resolution, start_date=start_date, end_date=end_date)
    report = select_best_station_sources(structure, [binding], client=client, now=now)
    return {
        "market_id": market_id,
        "source": source,
        "market": structure.to_dict(),
        "resolution": resolution.to_dict(),
        "station_binding": binding.to_dict(),
        "source_selection": report.to_dict(),
    }


def _annotate_source_lag_seconds(bundle: Any, *, now: datetime) -> None:
    point = bundle.latest()
    if point is None:
        return
    observed_at = _parse_observation_timestamp(point.timestamp)
    if observed_at is None:
        return
    bundle.source_lag_seconds = max(0, int((now - observed_at).total_seconds()))



def _parse_observation_timestamp(raw_timestamp: str) -> datetime | None:
    text = str(raw_timestamp).strip()
    if not text:
        return None
    candidates = [text]
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        candidates.append(f"{text}T00:00:00+00:00")
    for candidate in candidates:
        normalized = candidate.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None



def _utc_now() -> datetime:
    return datetime.now(timezone.utc)



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
    status_client = client or StationHistoryClient(now_utc=_utc_now())
    try:
        latest_bundle = status_client.fetch_latest_bundle(structure, resolution)
    except Exception:
        latest_bundle = build_station_history_bundle(structure, resolution, start_date="", end_date="", client=status_client)
    official_bundle = build_station_history_bundle(structure, resolution, start_date=date, end_date=date, client=status_client)
    latest = latest_bundle.latest()
    official = official_bundle.latest()
    route = build_resolution_source_route(structure, resolution, start_date=date, end_date=date)
    provisional = _build_resolution_outcome(structure, latest.value if latest else None, basis="latest_direct")
    confirmed = _build_resolution_outcome(structure, official.value if official else None, basis="official_daily_extract")
    action = "resolution_confirmed" if confirmed["status"] != "pending" else "monitor_until_official_daily_extract"
    return {
        "market_id": market_id,
        "source": source,
        "date": date,
        "market": structure.to_dict(),
        "resolution": resolution.to_dict(),
        "source_route": route.to_dict(),
        "latest_direct": _resolution_observation_payload(latest_bundle, latest),
        "official_daily_extract": _resolution_observation_payload(official_bundle, official),
        "provisional_outcome": provisional["status"],
        "confirmed_outcome": confirmed["status"],
        "latency": {
            "latest": _resolution_latency_payload(latest_bundle, latest),
            "official": _resolution_latency_payload(official_bundle, official),
        },
        "action_operator": action,
    }


def _resolution_observation_payload(bundle: Any, point: Any | None) -> dict[str, Any]:
    polling_focus = bundle.polling_focus
    expected_lag_seconds = bundle.expected_lag_seconds
    if polling_focus is None and expected_lag_seconds is None:
        polling_focus, expected_lag_seconds = _latency_operational_fields(bundle.source_provider, bundle.latency_tier)
    source_lag_seconds = bundle.source_lag_seconds
    if source_lag_seconds is None and point is not None and str(bundle.latency_tier).startswith("direct"):
        observed_at = _parse_observation_timestamp(point.timestamp)
        if observed_at is not None:
            now = _utc_now()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            source_lag_seconds = max(0, int((now.astimezone(timezone.utc) - observed_at).total_seconds()))
    return {
        "available": point is not None,
        "value": point.value if point else None,
        "timestamp": point.timestamp if point else None,
        "latency_tier": bundle.latency_tier,
        "source_url": bundle.source_url,
        "polling_focus": polling_focus,
        "expected_lag_seconds": expected_lag_seconds,
        "source_lag_seconds": source_lag_seconds,
    }


def _resolution_latency_payload(bundle: Any, point: Any | None) -> dict[str, Any]:
    payload = bundle.latency_diagnostics()
    observation = _resolution_observation_payload(bundle, point)
    for key in ("polling_focus", "expected_lag_seconds", "source_lag_seconds"):
        payload[key] = observation[key]
    return payload


def _build_resolution_outcome(structure: Any, observed_value: float | None, *, basis: str) -> dict[str, Any]:
    if observed_value is None:
        return {"status": "pending", "basis": basis}
    threshold = structure.target_value
    if threshold is None:
        return {"status": "observed", "basis": basis, "observed_value": observed_value, "threshold": None}
    if structure.threshold_direction == "higher":
        resolved_yes = observed_value >= threshold
    elif structure.threshold_direction == "below":
        resolved_yes = observed_value <= threshold
    else:
        resolved_yes = False
    return {
        "status": "yes" if resolved_yes else "no",
        "basis": basis,
        "observed_value": round(float(observed_value), 2),
        "threshold": round(float(threshold), 2),
    }


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
