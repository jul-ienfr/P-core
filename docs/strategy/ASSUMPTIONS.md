# Panoptique Assumptions

Verified facts are separated from hypotheses. This file lists assumptions to test, signals that would falsify them, and planned measurement sources.

## Assumptions to test

| Assumption | Falsification signal | Planned measurement source |
|---|---|---|
| Weather-market latency signals can be measured before they disappear. | Latency windows cannot be reconstructed, or apparent edges vanish after fees/spread/slippage in paper replay. | `weather_pm/weather_latency_edge.py`, paper ledgers, market snapshots, resolved weather outcomes. |
| Wallet behavior contains reusable signal after accounting for copy-trading decay. | Followed wallets underperform baseline out-of-sample, or observed lead time is too short to act even in paper simulation. | `weather_pm/wallet_intel.py`, `weather_pm/traders.py`, trade-event snapshots, wallet cohort reports. |
| Bot homogenization produces detectable crowd-flow clusters. | Bot/crowd archetypes do not cluster consistently, or clusters do not precede price/outcome movement. | Future Panoptique shadow-bot outputs, orderbook snapshots, trade events, crowd-flow observations. |
| Existing weather winning patterns are robust outside their discovery sample. | Patterns fail on new resolved markets or degrade below baseline after transaction-cost assumptions. | `weather_pm/winning_patterns.py`, paper watchlists, resolved market reports. |
| Strategy extraction can produce stable archetypes instead of overfit narratives. | Extracted strategies are not reproducible across runs, markets, or time windows. | `weather_pm/strategy_extractor.py`, archived strategy configs, shadow prediction logs. |
| Event surface features add information beyond raw price and volume. | Event-surface features do not improve Brier score, calibration, or paper PnL versus simple baselines. | `weather_pm/event_surface.py`, `prediction_core/analytics`, `prediction_core/evaluation`. |
| Phase gates reduce unsafe migration pressure. | Operators bypass gates, gates are ambiguous, or sample thresholds fail to catch unstable results. | `docs/strategy/GATES.md`, test outputs, phase reports, audit logs. |
| Paper-only experiments can be audited reliably from artifacts. | Missing raw payloads, inconsistent IDs, or non-replayable reports prevent reconstruction of decisions. | JSONL/Parquet artifacts, future DB rows, paper execution reports. |

## Review cadence

Assumptions should be revisited at each phase boundary. Any assumption falsified by data should stop dependent phases until the plan is revised.
