# Panoptique Paper Strategy Research Report

Paper-only research simulation for front-run/fade/skip strategy experiments.
No real orders were placed, no wallet credentials were used, and no live trading is enabled.
Results are research/paper observations only, never monetary-return claims.

## Run status

- Status: `not_enough_data`
- Artifact: `/home/jul/prediction_core/data/panoptique/paper_strategies/panoptique-paper-strategies-20260426T174249Z.jsonl`
- Decisions: `0`
- Paper candidates: `0`
- Skips: `0`
- Out-of-sample fraction: `0.000`

## Simulated entry/exit assumptions

- Entry: simulated taker interaction with archived order-book depth only.
- Exit: simulated after the crowd-flow horizon using measured or predicted crowd move.
- Safety: no real order language is operational; all actions are `paper_only` / `trading_action=none`.

## Failure modes

- crowd-flow forecast may be wrong out-of-sample
- spread, depth, or slippage may be worse than conservative paper assumptions
- source leakage or lookahead would invalidate research conclusions
- paper simulation omits real venue latency and fill uncertainty

## Decision details

- not_enough_data: strategy output is skip/not_enough_data, which is valid.
## Errors

- fixture not found: /tmp/nonexistent-panoptique-paper.jsonl
