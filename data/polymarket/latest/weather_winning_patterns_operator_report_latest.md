# Polymarket Weather Winning Patterns

- Profitable accounts: 500
- Accounts in strategy sample: 500

## Archetypes
- **event_surface_grid_specialist** (297): Groups many bins/thresholds on the same city/date surface and prices the whole surface, not isolated tickets. → `event_surface_builder`
- **weather_signal_generalist** (147): Adds weak account-consensus signal but is not treated as a pure reusable weather system. → `copy_trader_signal_features`
- **exact_bin_anomaly_hunter** (34): Buys low-priced exact bins/ranges where neighboring prices or forecast mass look misordered. → `cross_market_inconsistency_engine`
- **threshold_harvester** (22): Harvests near-resolution or source-backed threshold contracts with strict price discipline. → `near_resolution_threshold_watcher`

## Operator rules
- **source_first_before_price**: Validate the market's exact resolution source/station before trusting an apparent price edge.
- **surface_before_ticket**: Score all bins and thresholds for a city/date together before choosing YES/NO on one market.
- **strict_limit_no_market_buy**: Winning-account patterns are copied as rules/signals only; execution remains strict-limit and paper-first.

## Project integration
Already integrated: trader_activity_import, strategy_archetype_extraction, event_surface_builder, strategy_shortlist_bridge, operator_summary_bridge
Missing next layers: full_historical_trade_replay, archetype_backtest_pnl_drawdown_fillability, continuous_consensus_tracker, strict_limit_paper_execution_ledger
