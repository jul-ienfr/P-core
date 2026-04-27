# Polymarket Weather Production Operator Report

Paper only: True | Live ready: False | Candidates: 5

## Implemented vs Missing Production Layers

| Layer | Status | Detail |
|---|---|---|
| source_first_event_surface | implemented | surface source status: source_confirmed_fixture |
| cross_market_inconsistency_engine | implemented | candidate inconsistency flags included |
| orderbook_strict_limit_simulation | implemented | strict-limit fill metrics included |
| near_resolution_threshold_watcher | implemented | threshold recommendations included |
| continuous_consensus_tracker | implemented | account consensus summary available |
| historical_replay_backtest | missing | backtest/replay readiness gate |
| strict_limit_paper_execution_ledger | missing | paper ledger health gate |
| portfolio_sizing_risk_caps | implemented | portfolio caps applied to candidates |
| guarded_live_execution | guarded | live execution refused unless all readiness checks pass |
| real_money_live_execution | missing | intentionally disabled until explicit operator approval |

## Top Current Candidates

| Market | Side | Action | Source | Limit | Top Ask | Risk |
|---|---|---|---|---:|---:|---|
| chicago-high-72f-or-higher-20260430 | YES | paper_limit_only_after_source_recheck | source_confirmed_fixture | 0.5000 | 0.4800 | paper_small_capped |
| chicago-high-70f-exact-20260430 | NO | paper_limit_only_after_source_recheck | source_confirmed_fixture | 0.2400 | 0.2200 | paper_micro_only |
| chicago-high-71f-exact-20260430 | YES | paper_limit_only_after_source_recheck | source_confirmed_fixture | 0.3300 | 0.3100 | paper_micro_only |
| chicago-high-72f-exact-20260430 | YES | paper_limit_only_after_source_recheck | source_confirmed_fixture | 0.2700 | 0.2500 | paper_micro_only |
| chicago-high-70f-or-below-20260430 | NO | avoid_or_wait_for_cap_capacity | source_confirmed_fixture | 0.4000 | 0.3800 | avoid |

## Blockers

- live_readiness:paper_ledger_healthy
- live_readiness:backtest_replay_available
- live_readiness:explicit_live_mode_enabled

## Strict Next Actions

- refresh profitable weather accounts and consensus signals
- confirm official source/station before any paper add
- simulate strict-limit fills from a fresh orderbook before placement
- place paper limits only within portfolio caps
- monitor paper ledger and postmortem every filled/settled order
- enable live mode only after explicit operator approval

## Guarded Live Readiness

Status: refuse_live_execution

- source_confirmed: PASS — official source/station confirmed
- book_fresh: PASS — orderbook/fill simulation available
- paper_ledger_healthy: FAIL — paper ledger exists and has no red source flags
- backtest_replay_available: FAIL — historical replay/backtest artifact available
- risk_caps_satisfied: PASS — portfolio caps not blocking candidates
- explicit_live_mode_enabled: FAIL — operator explicitly enabled live mode
