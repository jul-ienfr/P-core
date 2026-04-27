# Weather Strategy Profiles

| ID | Execution | Max order | Entry gates | Do-not-trade |
| --- | --- | ---: | --- | --- |
| surface_grid_trader | paper_strict_limit | 15 | surface_inconsistency_present, source_confirmed, edge_survives_fill, strict_limit_not_crossed | source_missing, source_conflict, empty_orderbook, price_above_strict_limit, edge_destroyed_by_fill |
| exact_bin_anomaly_hunter | paper_strict_limit | 10 | exact_bin_mass_anomaly, source_confirmed, neighbor_bins_consistent, strict_limit_not_crossed | source_missing, ambiguous_exact_bin_rules, isolated_bin_without_neighbor_context, price_above_strict_limit |
| threshold_resolution_harvester | paper_micro_strict_limit | 8 | near_resolution_window, source_margin_favors_side, latest_source_available, strict_limit_not_crossed | source_missing, latest_observation_missing, source_margin_too_small, priced_in, price_above_strict_limit |
| profitable_consensus_radar | watchlist_only | 5 | multi_handle_consensus, independent_source_confirms, edge_survives_fill, not_wallet_copy_only | wallet_copy_only, source_missing, consensus_without_edge, thin_book, handle_cluster_conflict |
| conviction_signal_follower | paper_strict_limit | 12 | conviction_archetype_match, min_edge_met, source_confirmed, edge_survives_fill | source_missing, archetype_only_no_edge, conflicting_archetypes, edge_destroyed_by_fill, portfolio_cap_reached |
| macro_weather_event_trader | operator_review | 20 | macro_event_identified, forecast_source_supported, rules_clear, liquidity_sufficient | unclear_resolution_rules, unsupported_forecast_source, headline_only_no_market_edge, event_correlation_cap_reached |
