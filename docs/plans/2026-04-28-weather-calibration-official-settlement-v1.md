# Weather Calibration + Official Settlement V1 Implementation Plan

> **For Hermes:** Use phase-plan-executor skill to execute this plan phase-by-phase with strict TDD. Keep P-core paper/dry-run safe; do not enable live trading.

**Goal:** Add a minimal canonical weather calibration dataset/RMSE policy and official weather settlement resolver so P-core can improve weather probabilities and settle paper positions from official observed values before relying only on closed Polymarket outcome prices.

**Architecture:** P-core remains canonical under `/home/jul/P-core`. Add small pure modules under `python/src/weather_pm`; integrate into existing probability and settlement boundaries only after standalone tests pass. Official weather settlement must be deterministic from provided fixture/source payloads, with live fetching kept injectable and optional.

**Tech Stack:** Python stdlib dataclasses/csv/json/math/datetime, existing pytest suite, P-core `src/` layout via `PYTHONPATH=python/src`.

## Verified Context

- Canonical repo root: `/home/jul/P-core`.
- Current branch/status before this plan: `main...origin/main`, HEAD `c8d5db6`, no dirty files shown by `git status --short --branch`.
- Existing calibrated probability module: `python/src/weather_pm/calibrated_probability.py` with `LeadTimeRmsePolicy`, `CalibratedProbabilityInput`, `threshold_probability`, `exact_bin_probability`.
- Existing probability integration: `python/src/weather_pm/probability_model.py` uses calibrated Gaussian probability when `ForecastBundle.consensus_value` and `.dispersion` are present, otherwise safe fallback.
- Existing model structs: `python/src/weather_pm/models.py` has `MarketStructure`, `ResolutionMetadata`, `ForecastBundle`, `StationHistoryPoint`, `StationHistoryBundle`, `ModelOutput`.
- Existing source/routing tests: `python/tests/test_resolution_source_routing.py` covers NOAA, Wunderground, AviationWeather, IEM ASOS, Meteostat, AccuWeather, HKO routes.
- Existing Polymarket settlement: `python/src/weather_pm/polymarket_settlement.py` resolves paper positions from Gamma `closed=true` + final `outcomePrices`; tests in `python/tests/test_polymarket_settlement_resolver.py`.
- Existing final extraction doc: `docs/polymarket-weather-external-repo-extraction.md` records conceptual reuse from PolyWeather/weatherbot/polyBot, no vendoring and no live execution.
- External repo audit signal: useful next gaps are calibration data/RMSE by station/lead-time and official weather observed-value settlement. Do not vendor external repo files, secrets, dashboards, or live trading code.

## Execution Metadata

**Concurrency:** 1
**Parallel Mode:** serial
**Validation Mode:** standard
**Max Retries Per Task:** 1
**Resume:** true
**Commit Mode:** none

---

## Phase 1 — Calibration samples and grouped RMSE policy
**Progress:** 100%

- [x] Add failing tests in `python/tests/test_weather_calibration_dataset.py` covering: loading forecast-vs-observed samples from dicts/CSV rows, filtering by city/station/measurement/lead-time bucket, computing grouped RMSE, and falling back to global/default sigma when a group is missing.
- [x] Implement `python/src/weather_pm/calibration_dataset.py` with pure dataclasses/functions: `WeatherCalibrationSample`, `LeadTimeBucket`, `RmseEstimate`, `load_calibration_samples`, `group_rmse_estimates`, and `GroupedRmsePolicy.sigma(...)` compatible with `LeadTimeRmsePolicy` behavior.
- [x] Run validation: `PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_calibration_dataset.py python/tests/test_weather_calibrated_probability.py -q`.

### Phase Status
- [x] Phase 1 complete

---

## Phase 2 — Integrate calibration RMSE into probability safely
**Progress:** 100%

- [x] Add failing tests to `python/tests/test_weather_calibrated_probability.py` or `python/tests/test_weather_probability_model_calibration.py` proving `build_model_output` can accept a calibration/RMSE policy and widen/soften probability by city/station/lead-time while preserving the old fallback behavior when no policy/data is supplied.
- [x] Extend `ForecastBundle` only if needed with optional calibration context fields (`lead_time_hours`, `calibration_city`, `calibration_station_code`, or equivalent) without breaking existing constructors/tests; otherwise pass context directly to the probability builder.
- [x] Modify `python/src/weather_pm/probability_model.py` minimally so calibrated probability can use a supplied grouped RMSE policy; default behavior remains unchanged and paper/dry-run safe.
- [x] Run validation: `PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_calibrated_probability.py python/tests/test_weather_calibration_dataset.py python/tests/test_scoring.py python/tests/test_pipeline.py -q`.

### Phase Status
- [x] Phase 2 complete

---

## Phase 3 — Official observed weather value resolver
**Progress:** 100%

- [x] Add failing tests in `python/tests/test_weather_official_settlement.py` for extracting official observed high/low values from fixture payloads for NOAA daily summaries, Wunderground observations, HKO monthly extract, and generic station history bundles; include unsupported/missing-data behavior.
- [x] Implement `python/src/weather_pm/official_settlement.py` as pure helpers/dataclasses: `OfficialWeatherObservation`, `OfficialSettlementResult`, provider-specific parsers, unit conversion, high/low selection, and threshold/exact-bin outcome classification from `MarketStructure`.
- [x] Ensure resolver accepts already-fetched payloads/history bundles; any live network fetch must be behind an injectable client and not required by tests.
- [x] Run validation: `PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_official_settlement.py python/tests/test_resolution_source_routing.py -q`.

### Phase Status
- [x] Phase 3 complete

---

## Phase 4 — Paper settlement enrichment from official weather result
**Progress:** 100%

- [x] Add failing tests in `python/tests/test_polymarket_settlement_resolver.py` proving a paper position can be enriched/resolved from an `OfficialSettlementResult` when Polymarket is not final, while Gamma closed outcome prices remain authoritative when already final.
- [x] Extend `python/src/weather_pm/polymarket_settlement.py` with a pure function such as `resolve_position_from_official_weather(position, structure, official_result)` and/or optional enrichment helper; do not rewrite existing `EXIT_PAPER` PnL semantics.
- [x] Preserve strict paper-only behavior: no order placement, no cancellation, no wallet signing, no live trading path.
- [x] Run validation: `PYTHONPATH=python/src python3 -m pytest python/tests/test_polymarket_settlement_resolver.py python/tests/test_weather_official_settlement.py python/tests/test_paper_ledger.py python/tests/test_weather_paper_ledger.py -q`.

### Phase Status
- [x] Phase 4 complete

---

## Phase 5 — Operator documentation and final regression
**Progress:** 100%

- [x] Update `docs/polymarket-weather-external-repo-extraction.md` with the new V1 extraction: calibration samples/RMSE policy and official weather settlement resolver, explicitly noting no external code/credentials/live trading were imported.
- [x] Add or update a compact operator note under `docs/` if needed explaining the data contract for calibration sample rows and official settlement fixture payloads.
- [x] Run final targeted suite: `PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_calibration_dataset.py python/tests/test_weather_calibrated_probability.py python/tests/test_weather_official_settlement.py python/tests/test_polymarket_settlement_resolver.py python/tests/test_resolution_source_routing.py python/tests/test_paper_ledger.py python/tests/test_weather_paper_ledger.py -q`.
- [x] Run path-scoped git status/diff review to confirm only intended P-core files changed and no external repo files/secrets were copied.

### Phase Status
- [x] Phase 5 complete

---

## Global Status
**Overall Progress:** 100%
- [x] Plan complete
