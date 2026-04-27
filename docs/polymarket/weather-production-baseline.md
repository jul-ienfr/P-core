# Polymarket Weather Production Baseline

Generated during Phase 1 of `2026-04-26_140850-polymarket-weather-production-plan.md`.

## Scope

This audit records the real current API surfaces for the production weather modules requested by Phase 1. It is a baseline only: no production module behavior was changed in this phase.

## Module API surfaces

### `weather_pm.event_surface`

- Public entry point: `build_weather_event_surface(markets: list[dict[str, Any]], *, exact_mass_tolerance: float = 1.0) -> dict[str, Any]`.
- Input contract: list of market-like dictionaries with at least `question`; optional `id` and `yes_price` are used in output/scoring.
- Parsing dependency: `weather_pm.market_parser.parse_market_question`.
- Grouping identity: internal event key string `city|measurement_kind|unit|date_local`.
- Output shape: `{"event_count": int, "events": list[dict]}`; each event includes `event_key`, `market_count`, `exact_bin_count`, `threshold_count`, `exact_bin_price_mass`, `inconsistencies`, and normalized `markets`.
- Current inconsistency checks: threshold monotonicity violations by direction (`higher`/`below`) and exact-bin mass overround above tolerance.
- Current limitations: no explicit surface object/dataclass, no YES/NO token metadata, no source/station metadata, no normalized identity tuple field, and no cross-market candidate-side output yet.

### `weather_pm.source_routing`

- Public dataclass: `ResolutionSourceRoute` with route/provider/station/source URL, latency, support, manual review, and lag metadata.
- Public entry point: `build_resolution_source_route(structure: MarketStructure, resolution: ResolutionMetadata, *, start_date: str | None = None, end_date: str | None = None) -> ResolutionSourceRoute`.
- Supported direct/fallback route families include NOAA, Wunderground, AccuWeather, AviationWeather, IEM ASOS, Hong Kong Observatory, Meteostat fallback, Environment Canada, many explicit official URL providers, commercial API providers, Weather.com scrape target, ECMWF fallback, and generic local/national official sources.
- Output serialization: `ResolutionSourceRoute.to_dict()`.
- Current limitations: route status is represented by `supported`, `direct`, `manual_review_needed`, `latency_tier`, and `reason`; there are no production status labels such as `source_confirmed`, `source_missing`, `source_fetch_error`, or `source_conflict` yet.

### `weather_pm.station_binding`

- Public dataclasses: `StationEndpointCandidate` and `StationBinding`.
- Public entry point: `build_station_binding(structure: MarketStructure, resolution: ResolutionMetadata, *, start_date: str | None = None, end_date: str | None = None) -> StationBinding`.
- Behavior: wraps `build_resolution_source_route`, materializes latest/final/fallback endpoint candidates, and records `exact_station_match`, `manual_review_needed`, `best_polling_focus`, and the underlying route.
- Serialization: both dataclasses expose `to_dict()`.
- Current limitations: no explicit conflict model and no source/station confirmation status enum.

### `weather_pm.polymarket_live`

- Public entry points exported in `__all__`:
  - `list_live_weather_markets(limit: int = 100, active: bool = True, closed: bool = False) -> list[dict[str, Any]]`
  - `get_live_market_by_id(market_id: str) -> dict[str, Any]`
  - `get_live_event_book_by_id(event_id: str) -> dict[str, Any]`
  - `fetch_market_execution_snapshot(market_id: str) -> dict[str, Any]`
- Live dependencies: Gamma API (`https://gamma-api.polymarket.com`) and CLOB API (`https://clob.polymarket.com`).
- Normalized market fields include `id`, `category`, `question`, `yes_price`, top-of-book fields, book levels/depth, `clob_token_id` for YES, `volume`, `hours_to_resolution`, `resolution_source`, `description`, and `rules`.
- Execution snapshot shape includes `market_id`, `question`, `tokens`, `book` for YES/NO, `spread`, `fetched_at`, and `source`.
- Current limitations: only the YES CLOB token ID is fully normalized; NO token ID is `None` in the snapshot and NO book levels are inferred rather than fetched directly.

### `weather_pm.execution_features`

- Public entry point: `build_execution_features(raw_market: dict[str, Any]) -> ExecutionFeatures`.
- Output dataclass: `weather_pm.models.ExecutionFeatures` via `.to_dict()`.
- Input fields used include best bid/ask, yes price, volume/depth, hours to resolution, target order size/requested quantity, fees, transfer fees, fair probability, execution side, and book levels.
- Metrics include spread, fillable size, speed requirement, slippage risk, max impact, fee/slippage/all-in costs, quoted prices, estimated average fill price, net execution edge, best-effort reason, tradeability status, and cost risk.
- Current limitations: not yet a side-aware strict-limit fill simulator; no per-candidate `top_ask`, `levels_used`, `edge_after_fill`, or explicit no-market-buy blocker labels.

### `weather_pm.strategy_extractor`

- Public entry points: `extract_weather_strategy_rules(traders: Iterable[WeatherTrader]) -> dict[str, Any]` and `summarize_strategy_rules(rules: dict[str, Any]) -> dict[str, Any]`.
- Input contract: iterable of `weather_pm.traders.WeatherTrader` with sample weather titles and PnL/volume metadata.
- Output includes per-account archetype, market type counts, top cities, repeated city/date events, strategy rules, and summary implementation priorities.
- Current archetypes inferred: `event_surface_grid_specialist`, `threshold_harvester`, `exact_bin_anomaly_hunter`, and `weather_signal_generalist`.
- Current limitations: title parsing is regex-based and summary-level; no historical replay/backtest output.

### `weather_pm.winning_patterns`

- Public entry points:
  - `build_winning_patterns_operator_report(...) -> dict[str, Any]`
  - `write_winning_patterns_operator_report(...) -> dict[str, Any]`
  - `compact_winning_patterns_operator_report(report: dict[str, Any]) -> dict[str, Any]`
  - `markdown_winning_patterns_operator_report(report: dict[str, Any]) -> str`
- Inputs: classified account summary, continued summary, strategy pattern summary, strategy report, future consensus rows, and orderbook bridge rows.
- Output includes summary counts, archetype counts, weather title kind counts, top cities, operator rules, consensus surfaces, orderbook candidates, implementation priorities, Discord brief, and artifact paths when written.
- Current limitations: report bridges existing artifacts but does not run source confirmation, inconsistency, strict fill, paper ledger, or risk caps directly.

### `weather_pm.paper_watchlist`

- Public entry points:
  - `build_paper_watchlist_report(payload: dict[str, Any]) -> dict[str, Any]`
  - `write_paper_watchlist_report(input_json, output_json=None) -> dict[str, Any]`
  - `write_paper_watchlist_csv(input_json, output_csv) -> int`
  - `write_paper_watchlist_markdown(input_json, output_md) -> str`
  - `render_paper_watchlist_markdown(report: dict[str, Any]) -> str`
  - `paper_watchlist_operator_decision(report: dict[str, Any]) -> dict[str, str]`
  - `compact_paper_watchlist_report(report, *, output_json=None, output_csv=None, output_md=None) -> dict[str, Any]`
  - `build_paper_watch_row(position, *, p_side, best_bid, best_ask, forecast_c) -> dict[str, Any]`
- Input contract: monitor JSON with `positions`; each position must provide enough fill and probability fields for EV/action calculation.
- Output includes summary totals/action counts and watchlist rows with stops, take-profit review levels, add limits, and operator actions.
- Current limitations: this is a monitor/watchlist report, not a strict-limit paper execution ledger with order lifecycle states.

## Test baseline

Existing targeted tests before Phase 1 additions covered event-surface grouping/inconsistency, strategy shortlist/operator flows, and winning-pattern report generation. Phase 1 added a production contract fixture and tests for fixture loading, normalized identity, token/orderbook/source/consensus contract fields, and stable JSON schema.

## Phase 1 fixture contract

Fixture path: `python/tests/fixtures/polymarket_weather_city_date_surface.json`.

The fixture represents one multi-market city/date surface with:

- normalized identity `(city, date, measurement_kind, unit)` = `(Chicago, 2026-04-30, high, f)`;
- exact bins for 70°F, 71°F, and 72°F;
- a threshold-high contract for 72°F or higher;
- a threshold-low contract for 70°F or below;
- YES/NO token IDs for every market;
- best bid/ask/spread for every market;
- a source URL and station metadata;
- account-consensus hints at surface and market level.
