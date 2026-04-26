# Panoptique Evidence Register

This register classifies major empirical claims used by the Panoptique migration. It distinguishes verified repo facts from hypotheses and prevents strategic language from being treated as proven alpha.

## Classification scale

- **verified**: confirmed from this repository, local filesystem, tests, or generated artifacts.
- **plausible**: consistent with available context or common market mechanics, but not yet proven in this repo.
- **unverified**: an explicit claim to test with Panoptique measurement, or a claim without enough supporting evidence yet.
- **rejected**: contradicted by plan constraints, measurements, or repository facts.

## Major empirical claims

Compatibility summary for legacy docs checks:

| Claim | Classification | Evidence status | Phase impact |
|---|---|---|---|
| bot homogenization | unverified | tracked by source URL and confidence | measurement gate before claims |
| Polymarket volume/efficiency | plausible | tracked by source URL and confidence | research target only |
| weather bot degradation | unverified | tracked by source URL and confidence | weather-specific measurements required |
| copy-trading decay | unverified | tracked by source URL and confidence | cohort evidence required |
| phase gates | plausible | tracked by source URL and confidence | gates remain conservative |

## Evidence schema

Each claim uses a stable claim ID, a source URL, a status, and confidence from `0.0` to `1.0`. Local repo paths use `file://` URLs so future reports can link back to exact evidence.

| Claim ID | Claim | Source URL | Status | Confidence | Notes / phase impact |
|---|---|---|---:|---:|---|
| EV-PAN-001 | Existing repo has weather/paper/analytics/calibration/evaluation/execution modules that can be mapped to Panoptique concepts. | `file:///home/jul/prediction_core/docs/plans/2026-04-26-panoptique-migration-plan.md#contexte-verifie` | verified | 0.95 | Phase 0 documented mappings without runtime changes. |
| EV-PAN-002 | Current weather monitoring and paper workflows are paper-only and should be preserved. | `file:///home/jul/prediction_core/README.md` | verified | 0.90 | Reinforces no real-money expansion and paper-only language. |
| EV-PAN-003 | Bot homogenization may create predictable crowd-flow patterns. | `file:///home/jul/prediction_core/docs/strategy/PANOPTIQUE_STRATEGY.md` | unverified | 0.25 | Strategic claim only; Phase 2-4 measurements are required before use. |
| EV-PAN-004 | Polymarket volume/efficiency leaves exploitable pockets in some markets. | `file:///home/jul/prediction_core/docs/strategy/PANOPTIQUE_STRATEGY.md` | plausible | 0.45 | Treat as research target, not a trading fact or profit claim. |
| EV-PAN-005 | Weather bot degradation creates measurable edge decay or fade opportunities. | `file:///home/jul/prediction_core/python/src/weather_pm/weather_latency_edge.py` | unverified | 0.30 | Existing weather instrumentation is relevant, but robust degradation is unproven. |
| EV-PAN-006 | Copy-trading decay reduces the value of following visible profitable wallets over time. | `file:///home/jul/prediction_core/python/src/weather_pm/wallet_intel.py` | unverified | 0.20 | Requires wallet cohorts, timestamps, and out-of-sample tracking. |
| EV-PAN-007 | Phase gates improve migration safety by blocking later phases until evidence thresholds pass. | `file:///home/jul/prediction_core/docs/strategy/GATES.md` | plausible | 0.70 | Used as a process control even while statistical thresholds are refined. |
| EV-PAN-008 | Phase 2/3 paper samples can predict later live performance. | `file:///home/jul/prediction_core/docs/plans/2026-04-26-panoptique-migration-plan.md#phase-10--future-live-micro-test-plan-separate-approval-required` | unverified | 0.10 | Paper evidence can justify later review only; it does not authorize live trading. |
| EV-PAN-009 | Live trading is approved by this migration plan. | `file:///home/jul/prediction_core/docs/plans/2026-04-26-panoptique-migration-plan.md#non-negotiable-migration-principles` | rejected | 0.99 | Plan explicitly forbids real-money expansion without separate future approval. |
| EV-PAN-010 | Public GitHub repositories expose bot templates, common thresholds, prompts, or config patterns relevant to shadow archetypes. | `file:///home/jul/prediction_core/python/src/panoptique/github_repos.py` | unverified | 0.35 | Phase 6 crawler records public metadata only under `data/panoptique/ecosystem/`; no cloning by default. |

## GitHub ecosystem crawler v0 evidence policy

- Search terms v0: `polymarket bot`, `kalshi bot`, `prediction market trading bot`, `polymarket agent`.
- Default crawler path uses GitHub public metadata only and does **not** clone repositories.
- Recorded fields: name, URL, stars, forks, pushed_at, topics, README hash when visible/provided, detected keywords, and raw public metadata flags.
- Optional manual audit can print a shallow-clone command into `/tmp` for a selected repo; it must not run third-party code.
- Raw artifacts are written under `data/panoptique/ecosystem/github_repos_*.json`; report artifacts summarize likely templates, common parameters, and prompt/config exposure if visible.

## Maintenance rule

When later phases add measurements, update this register with sample size, date range, method, and whether each claim remains unverified, becomes plausible/verified, or is rejected.
