# Weather Probability/Risk/Intraday Extraction Implementation Plan

> **For Hermes:** Use phase-plan-executor skill to execute this plan phase-by-phase with strict TDD. Keep P-core paper/dry-run safe; do not enable live trading.

**Goal:** Improve P-core weather-market decision quality by selectively extracting ideas from PolyWeather, weatherbot, and polyBot-Weather: calibrated weather probability, paper exit policy, portfolio risk guards, and intraday alert features.

**Architecture:** P-core remains canonical. Add small, tested modules under `python/src/weather_pm` and `python/src/prediction_core` without importing external repo code wholesale. Integrate only through existing strategy/profile/paper boundaries after standalone unit tests pass.

**Tech Stack:** Python stdlib dataclasses/math, existing pytest suite, P-core `src/` layout via `PYTHONPATH=python/src`.

## Verified Context

- Canonical repo root: `/home/jul/P-core`.
- Current branch/status before this plan: `main...origin/main` with existing user/session modifications in Grafana dashboards, alerts, weather profile strategy files, cron tests, and scripts. Do not overwrite or stage unrelated dirty files.
- Existing P-core weather probability module: `python/src/weather_pm/probability_model.py` uses simple heuristic threshold/exact-bin probabilities.
- Existing entry policy: `python/src/prediction_core/decision/entry_policy.py` checks price window, min edge/confidence, spread, depth, and execution costs.
- Existing dynamic sizing: `python/src/weather_pm/dynamic_position_sizing.py` has per-market/surface/total exposure caps.
- Existing paper ledgers: `python/src/weather_pm/paper_ledger.py` and `python/src/prediction_core/paper/ledger.py` are strict-limit paper-only and require refreshed orderbooks.
- Existing source/routing and forecast clients: `python/src/weather_pm/source_routing.py`, `python/src/weather_pm/forecast_client.py`.
- Existing strategy profiles: `python/src/weather_pm/strategy_profiles.py`, `python/src/weather_pm/runtime_operator_profiles.py`.
- Targeted validation already passing before this work: `31 passed` for `test_weather_profile_strategies.py`, `test_runtime_operator_profiles.py`, `test_weather_cron_monitor_refresh.py`.
- External repo audit conclusion: use PolyWeather for weather/source/intraday ideas, weatherbot for simple EV/Kelly/calibration ideas, polyBot-Weather for risk/circuit-breaker/simulation patterns.

## Execution Metadata

**Concurrency:** 1
**Parallel Mode:** serial
**Validation Mode:** standard
**Max Retries Per Task:** 1
**Resume:** true
**Commit Mode:** none

---

## Phase 1 — Calibrated weather probability core
**Progress:** 100%

- [x] Add failing tests in `python/tests/test_weather_calibrated_probability.py` covering Gaussian CDF threshold probability, exact-bin probability, lead-time RMSE widening, and edge z-score.
- [x] Implement `python/src/weather_pm/calibrated_probability.py` with `LeadTimeRmsePolicy`, `CalibratedProbabilityInput`, `CalibratedProbabilityOutput`, Gaussian CDF helpers, exact-bin mass, threshold probability, edge, and z-score.
- [x] Integrate `weather_pm.probability_model.build_model_output` to use calibrated probability when forecast bundle/market structure data is sufficient, preserving existing `ModelOutput` shape and safe fallback.
- [x] Run validation: `PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_calibrated_probability.py python/tests/test_scoring.py python/tests/test_pipeline.py -q`.

### Phase Status
- [x] Phase 1 complete

---

## Phase 2 — Paper exit policy inspired by weatherbot
**Progress:** 100%

- [x] Add failing tests in `python/tests/test_paper_exit_policy.py` for stop-loss, trailing stop, breakeven-after-profit, hold, and missing-price behavior.
- [x] Implement `python/src/prediction_core/paper/exit_policy.py` as pure functions/dataclasses with no live execution side effects.
- [x] Add optional exit-policy annotation to paper ledger refresh output without changing strict-limit placement semantics.
- [x] Run validation: `PYTHONPATH=python/src python3 -m pytest python/tests/test_paper_exit_policy.py python/tests/test_paper_ledger.py python/tests/test_weather_paper_ledger.py -q`.

### Phase Status
- [x] Phase 2 complete

---

## Phase 3 — Portfolio risk guards / circuit breaker
**Progress:** 100%

- [x] Add failing tests in `python/tests/test_portfolio_risk_guards.py` for max open positions, daily paper loss cap, deployed capital cap, min liquidity, and circuit breaker state.
- [x] Implement `python/src/prediction_core/risk/portfolio_guards.py` with pure dataclasses/functions inspired by polyBot risk manager but adapted to P-core paper/dry-run boundaries.
- [x] Integrate risk guard output into weather runtime/profile decision payloads as blockers/reasons, without enabling live trading.
- [x] Run validation: `PYTHONPATH=python/src python3 -m pytest python/tests/test_portfolio_risk_guards.py python/tests/test_runtime_operator_profiles.py python/tests/test_weather_profile_strategies.py -q`.

### Phase Status
- [x] Phase 3 complete

---

## Phase 4 — Intraday weather alert features
**Progress:** 100%

- [x] Add failing tests in `python/tests/test_weather_intraday_alerts.py` for momentum spike, peak-passed guard, stale observation, source-confirmed threshold margin, and no-data behavior.
- [x] Implement `python/src/weather_pm/intraday_alerts.py` as pure feature extraction helpers inspired by PolyWeather alert engine.
- [x] Add intraday alert summary into runtime operator/profile payloads where recent observation rows are present, preserving existing behavior when absent.
- [x] Run validation: `PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_intraday_alerts.py python/tests/test_runtime_operator_profiles.py python/tests/test_weather_strategy_shortlist.py -q`.

### Phase Status
- [x] Phase 4 complete

---

## Phase 5 — Final regression and audit note
**Progress:** 100%

- [x] Add or update a short docs note `docs/polymarket-weather-external-repo-extraction.md` listing what was reused conceptually and what was deliberately not imported.
- [x] Run final targeted suite: `PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_calibrated_probability.py python/tests/test_paper_exit_policy.py python/tests/test_portfolio_risk_guards.py python/tests/test_weather_intraday_alerts.py python/tests/test_runtime_operator_profiles.py python/tests/test_weather_profile_strategies.py python/tests/test_weather_cron_monitor_refresh.py -q`.
- [x] Run path-scoped git status/diff review to confirm only intended P-core files changed and no external repo files/secrets were copied.

### Phase Status
- [x] Phase 5 complete

---

## Global Status
**Overall Progress:** 100%
- [x] Plan complete
