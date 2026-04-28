# Polymarket Weather External Repo Extraction

This note records what P-core reused conceptually from the three audited weather/Polymarket bot repositories and what was deliberately not imported.

## Source audit summary

- `yangyuan-zhen/PolyWeather` was the strongest source of operational weather-market ideas: source routing, intraday alerting, settlement/source organization, and dashboard-oriented diagnostics.
- `alteregoeth-ai/weatherbot` was useful as a compact reference for simple expected-value, position, and exit-policy concepts.
- `hcharper/polyBot-Weather` was useful only as inspiration for portfolio risk/circuit-breaker style guards because its history and structure were much thinner.

## What was reused conceptually

### Calibrated probability

P-core now has a small calibrated weather-probability core that models forecast error with a Gaussian CDF, supports threshold and exact-bin markets, exposes edge/z-score diagnostics, and widens uncertainty by forecast lead time.

This is a conceptual extraction of the useful modelling direction from the external repos, not a wholesale port.

### Paper exit policy

P-core now has pure paper exit-policy annotations for stop-loss, trailing-stop, breakeven-after-profit, hold, and missing-price cases.

The policy is recommendation-only. It does not place, cancel, sell, or otherwise enable live execution.

### Portfolio risk guards

P-core now has pure portfolio guard evaluation for max open positions, daily paper loss cap, deployed capital cap, min liquidity, and circuit-breaker state.

The result is surfaced as blockers/reasons/diagnostics for weather runtime/profile decisions. It remains paper/dry-run safe.

### Intraday weather alerts

P-core now has pure intraday weather feature extraction for momentum spikes, peak-passed guard, stale observations, source-confirmed threshold margins, and no-data behavior.

Runtime/profile payloads include the summary only when recent observation rows are present, preserving existing behavior when absent.

### Calibration samples and grouped RMSE policy

P-core V1 now has a canonical weather calibration sample contract for forecast-vs-observed rows keyed by city, station, measurement, and lead-time bucket. The grouped RMSE policy widens calibrated probability sigma from matched historical errors, with global/default fallbacks when a group is missing.

This implements the useful calibration/RMSE idea identified during the external audit without importing external datasets, scripts, or model code.

### Official weather settlement resolver

P-core V1 now has a pure official weather settlement resolver that classifies threshold and exact-bin weather markets from already-fetched official payloads or station history bundles. Supported fixture contracts cover NOAA daily summaries, Wunderground observations, HKO monthly extracts, and generic station-history rows.

Paper settlement can be enriched from this official result when Polymarket is not final, while closed Polymarket outcome prices remain authoritative. The resolver does not require network access; any live fetch path must be explicitly injected by the caller.

### Weather operator cockpit

P-core now provisions a weather-specific Grafana cockpit backed by existing ClickHouse analytics tables. It focuses on city/date/source context, model probability vs market price, source freshness, intraday alerts, risk caps, paper position/action state, and official settlement status.

## What was deliberately not imported

- No external repository was vendored into P-core.
- No credentials, tokens, API keys, or account-specific config were copied.
- No Telegram/Discord notification behavior was copied.
- No live-trading path was enabled.
- No wallet signing, order placement, or cancellation behavior was added.
- No external calibration dataset, official-settlement fixture, dashboard, or frontend stack was imported.
- No broad architecture replacement was attempted; P-core remains the canonical implementation boundary.

## Validation

The extraction was implemented with test-first phases and targeted validation. The probability/risk/intraday suite is recorded in:

`docs/plans/2026-04-27-weather-probability-risk-intraday-extraction.md`

The calibration/official-settlement V1 suite and final regression are recorded in:

`docs/plans/2026-04-28-weather-calibration-official-settlement-v1.md`
