# Polymarket météo — Strategy Profiles PhasePlanExecutor Board

**Repo Path:** `/home/jul/P-core`
**Created:** `20260427T101733Z`
**Concurrency:** 2
**Parallel Mode:** serial
**Validation Mode:** standard
**Max Retries Per Task:** 1
**Resume:** true
**Commit Mode:** none

## Scope

Implement the weather strategy-profile layer derived from the live top-10 profitable Polymarket weather account analysis.

The implementation must encode reusable decision structures, not wallet-copying:

- `surface_grid_trader`
- `exact_bin_anomaly_hunter`
- `threshold_resolution_harvester`
- `profitable_consensus_radar`
- `conviction_signal_follower`
- `macro_weather_event_trader`

Use strict TDD. Do not touch generated `data/` artifacts or Panoptique deletions. Do not stage or commit unless explicitly asked later.

## Phase 1 — Strategy profile domain
**Progress:** 100%

- [x] Add failing tests in `python/tests/test_weather_strategy_profiles.py` for the six canonical weather strategy profiles: IDs, inspirations, required inputs, entry gates, risk caps, execution modes, and do-not-trade rules.
- [x] Implement `python/src/weather_pm/strategy_profiles.py` with typed/deterministic profile definitions and helpers to list profiles, fetch by id, classify a candidate row, and produce a compact operator matrix.
- [x] Add CLI support in `python/src/weather_pm/cli.py` for `strategy-profiles`, outputting compact JSON and optional Markdown.
- [x] Validate Phase 1 with `cd /home/jul/P-core/python && PYTHONPATH=src python3 -m pytest tests/test_weather_strategy_profiles.py -q`.

### Phase Status
- [x] Phase 1 complete

## Phase 2 — Shortlist/operator integration
**Progress:** 100%

- [x] Add failing tests in `python/tests/test_weather_strategy_shortlist.py` proving shortlist rows receive `strategy_profile_id`, `strategy_profile`, `profile_risk_caps`, `profile_execution_mode`, and profile-specific next actions without overriding existing execution/source blockers.
- [x] Wire `weather_pm.strategy_shortlist` to annotate each row with the selected strategy profile using existing fields: surface anomalies, threshold watch, profitable trader consensus, direct source, orderbook/fill status, and matched trader archetypes.
- [x] Extend `build_operator_shortlist_report` watchlist rows and summary to expose strategy-profile counts and operator-readable profile labels.
- [x] Validate Phase 2 with `cd /home/jul/P-core/python && PYTHONPATH=src python3 -m pytest tests/test_weather_strategy_shortlist.py tests/test_weather_strategy_profiles.py -q`.

### Phase Status
- [x] Phase 2 complete

## Phase 3 — Playbook/docs and final validation
**Progress:** 100%

- [x] Add or update Markdown playbook docs under `docs/` describing each profile, entry gates, sizing/risk caps, and how profitable-account signals may be used only as radar unless source/orderbook/edge independently confirm.
- [x] Add/report profile matrix in winning-patterns output so the operator report links learned top-10 patterns to implemented strategy profiles.
- [x] Run targeted validation: `cd /home/jul/P-core/python && PYTHONPATH=src python3 -m pytest tests/test_weather_strategy_profiles.py tests/test_weather_strategy_shortlist.py tests/test_weather_winning_patterns.py -q`.
- [x] Run compile validation: `cd /home/jul/P-core/python && PYTHONPATH=src python3 -m py_compile src/weather_pm/strategy_profiles.py src/weather_pm/strategy_shortlist.py src/weather_pm/winning_patterns.py src/weather_pm/cli.py`.

### Phase Status
- [x] Phase 3 complete

## Global Status
**Overall Progress:** 100%
- [x] Plan complete
