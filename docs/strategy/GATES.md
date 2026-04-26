# Panoptique Gates

Panoptique gates are hard controls. Passing code tests is necessary but not sufficient for later phases when empirical evidence is required.

## Hard gates

| Gate | Minimum requirement | Blocks |
|---|---|---|
| Phase 0 doctrine gate | Required docs exist, README pointer exists, docs layout test passes, and no runtime behavior changes are introduced. | Phase 1 implementation. |
| Phase 1 storage gate | Local PostgreSQL/TimescaleDB design and migrations work, contract tests pass, raw artifact path remains available. | Phase 2 observation. |
| Phase 2 observation gate | Reliable read-only collection for the required window plus Phase 2 sample target: 200+ paper resolved trades before promotion to strategy evaluation. | Phase 3 live evaluation or any execution expansion. |
| Phase 3 shadow-bot gate | 100+ paper-only shadow predictions logged with deterministic versions and no real orders. | Crowd-flow measurement claims. |
| Level 2 statistical gate | Level 2 statistical gate: p<0.05 / 100+ markets with documented method, baseline, and failure cases. | Any claim that a signal is statistically reliable. |
| Phase 3 live constraints if ever later approved | Separate approval, explicit bankroll/risk limits, kill switch, wallet isolation, operator signoff, compliance review, and dry-run evidence. | Any real-money live execution. |
| Phase 10/live gate | No Phase 10/live without separate explicit approval. This plan cannot authorize live trading. | Live trading, wallet credentials, real orders. |

## Paper-only requirements

- All Phase 0 through pre-approved later work is paper-only/read-only unless a separate future approval says otherwise.
- Simulated orders must state that no real order was placed.
- No private keys, wallet credentials, or live execution configuration should be introduced by this migration phase.

## Sample-size requirements

- Phase 2 sample target: 200+ paper resolved trades.
- Phase 3 shadow-bot minimum: 100+ shadow predictions before crowd-flow claims are interpreted.
- Level 2 statistical gate: p<0.05 / 100+ markets, with methodology recorded before the result is promoted.

## Failure policy

A failed gate stops dependent work. The correct response is to document the failure, update assumptions/evidence, and revise the plan instead of weakening thresholds silently.
