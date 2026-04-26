# Winning weather account patterns → operator rules

Generated: 2026-04-25T22:21:20Z

## Evidence base
- Positive weather-PnL accounts: 10,050
- Weather-heavy/specialist or mixed: 5,966
- Top80 archetypes: {'event_surface_grid_specialist': 52, 'exact_bin_anomaly_hunter': 18, 'threshold_harvester': 3, 'weather_signal_generalist': 7}
- Raw observed weather-title kinds: {'range_or_bin': 15305, 'threshold': 2734, 'other_weather': 30}

## Rules extracted
- **R1 event-surface first** — Group all markets by city/date/unit. Never score an isolated exact bin before seeing adjacent bins and thresholds.
- **R2 choose side by source, not title** — For each bin compute YES and NO probability from settlement-station max. A far exact bin usually means NO edge, not discard.
- **R3 exploit monotonic/neighbor inconsistencies** — Flag thresholds/bins where price order contradicts temperature distribution or neighboring bins.
- **R4 consensus is a map, not signal** — Use profitable accounts to prioritize city/date surfaces; require station + book + model edge before paper/live.
- **R5 strict limit only** — Enter only if current ask <= limit and small-fill average keeps edge; do not chase moved books.
- **R6 portfolio caps** — Many tiny independent edges > one big conviction. Cap per city/date and per surface side.
- **R7 official source split** — Keep official resolution source separate from forecast proxy. Proxy-only = watch/paper at most.

## Current consensus surfaces needing source/orderbook validation
- **Moscow April 26**: NO 12°C — accounts=9, signals=32, side_share=0.994, proxy_max=10.0, verdict=NO_aligned_with_proxy_exact_bin_false, action_score=570.0
- **Shanghai April 26**: NO 21°C — accounts=10, signals=30, side_share=0.963, proxy_max=23.8, verdict=NO_aligned_with_proxy_exact_bin_false, action_score=529.5
- **Beijing April 26**: NO 22°C — accounts=8, signals=23, side_share=0.977, proxy_max=24.4, verdict=NO_aligned_with_proxy_exact_bin_false, action_score=404.2
- **Seoul April 26**: NO 17°C — accounts=10, signals=28, side_share=0.91, proxy_max=22.6, verdict=NO_aligned_with_proxy_exact_bin_false, action_score=348.5
- **Munich April 26**: NO 16°C — accounts=11, signals=38, side_share=0.879, proxy_max=18.3, verdict=NO_aligned_with_proxy_exact_bin_false, action_score=332.6
- **Shanghai April 27**: NO 24°C — accounts=3, signals=29, side_share=0.983, proxy_max=25.8, verdict=NO_aligned_with_proxy_exact_bin_false, action_score=305.5
- **Seoul April 27**: NO 15°C — accounts=6, signals=23, side_share=0.983, proxy_max=16.5, verdict=NO_aligned_with_proxy_exact_bin_false, action_score=299.5
- **London April 26**: NO 20°C — accounts=11, signals=27, side_share=0.791, proxy_max=18.2, verdict=NO_aligned_with_proxy_exact_bin_false, action_score=292.8

## Implementation priorities
- event_surface_builder
- near_resolution_threshold_watcher
- trader_activity_history_import
- strategy_backtest_replay
- paper_then_live_execution_loop
