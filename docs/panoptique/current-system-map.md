# Current System Map

This map links existing repo modules to Panoptique concepts. It is an inventory document only and does not change runtime behavior.

## Existing module mapping

| Existing module | Current role | Panoptique concept | Phase 0 note |
|---|---|---|---|
| `weather_pm/weather_latency_edge.py` | Weather-specific latency/edge analysis. | Latency signal observer and measurement candidate. | Treat edge claims as hypotheses until resolved paper samples support them. |
| `weather_pm/winning_patterns.py` | Pattern discovery/reporting for weather markets. | Strategy evidence candidate and baseline pattern library. | Requires out-of-sample validation before promotion. |
| `weather_pm/wallet_intel.py` | Wallet/account intelligence. | Agent/wallet registry input and copy-trading decay measurement source. | Wallet-following remains paper-only and unproven. |
| `weather_pm/traders.py` | Trader/account views and classifications. | Participant taxonomy for crowd-flow and shadow-bot archetypes. | Useful for observation; not a trading approval. |
| `weather_pm/strategy_extractor.py` | Extracts strategy-like descriptions from observed behavior. | Shadow-bot archetype seed and strategy-config source. | Must be deterministic and versioned in later phases. |
| `weather_pm/event_surface.py` | Event/market feature surface. | Market/event feature layer for measurement and calibration. | Candidate features need evaluation against baselines. |
| `prediction_core/analytics` | Analytics utilities and summaries. | Panoptique measurement/reporting layer. | Reuse for read models before adding new analytics. |
| `prediction_core/calibration` | Calibration tooling. | Probability calibration and Brier/reliability measurement. | Later phases should route shadow predictions through calibration checks. |
| `prediction_core/evaluation` | Evaluation logic. | Outcome scoring, baselines, and gate evidence. | Gate reports should prefer existing evaluation primitives where possible. |
| `prediction_core/execution` | Execution contracts/scaffolding. | Boundary object for paper/live separation. | Phase 0 introduces no execution changes; live remains unapproved. |

## Panoptique concept coverage

- **Observation**: weather latency, event surfaces, wallet/trader views, future market snapshots.
- **Shadow bots**: strategy extraction plus trader taxonomy can seed deterministic paper-only archetypes.
- **Crowd-flow measurement**: wallet/trader/event modules can become inputs once durable snapshots exist.
- **Evidence governance**: analytics, calibration, and evaluation packages should support gates and reports.
- **Execution boundary**: execution code is not expanded in Phase 0; paper-only language remains mandatory.

## Gaps for later phases

- Durable Panoptique data contracts and storage schema.
- Versioned shadow-bot outputs.
- Market snapshot ingestion and raw audit archive structure.
- Statistical reports tied to hard gates.
