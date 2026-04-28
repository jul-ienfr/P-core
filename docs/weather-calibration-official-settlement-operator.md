# Weather Calibration + Official Settlement Operator Note

P-core weather calibration and official settlement V1 are pure, paper-safe data contracts. They do not import external bot code, credentials, wallet signing, order placement, cancellation, or live trading behavior.

## Calibration sample rows

Calibration rows compare a historical forecast against the later official observation. They can be loaded from dict/CSV-style rows with canonical or alias field names:

| Canonical field | Accepted aliases | Meaning |
| --- | --- | --- |
| `city` | — | Market city label used for grouped calibration. |
| `station_code` | `station` | Weather station identifier when known. |
| `measurement_kind` | `measurement` | Weather measure such as `high`, `low`, or `temp`. |
| `lead_time_hours` | `lead_hours` | Forecast lead time before the target observation. |
| `forecast_value` | `forecast` | Forecast value in the market unit. |
| `observed_value` | `observed` | Official observed value in the same unit. |

`group_rmse_estimates(...)` groups samples by normalized city, station, measurement, and lead-time bucket. `GroupedRmsePolicy.sigma(...)` widens model dispersion with the matching group RMSE, then falls back to the global RMSE estimate or configured default sigma.

## Official settlement fixture payloads

Official settlement fixtures are already-fetched payloads passed to `resolve_official_weather_settlement(...)`. Tests and operators should keep them minimal and source-specific:

- NOAA daily summaries: list or `{ "results": [...] }`/`{ "data": [...] }` rows with `DATE`, `STATION`, and `TMAX` or `TMIN`.
- Wunderground observations: `{ "observations": [...] }` rows with a local/UTC timestamp, optional station id, and temperature under `imperial.temp`, `metric.temp`, or a direct temperature field.
- HKO monthly extracts: list or `{ "data": [...] }` rows with day/date plus `max`/`min` temperature fields.
- Generic station history: `StationHistoryBundle` with `StationHistoryPoint(timestamp, value, unit)` entries.

The resolver classifies threshold and exact-bin `MarketStructure` outcomes from the observed value. Live fetching is only possible through an explicit injectable client and is not required by the V1 fixtures or tests.
