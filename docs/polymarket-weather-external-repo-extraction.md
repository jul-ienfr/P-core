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

## What was deliberately not imported

- No external repository was vendored into P-core.
- No credentials, tokens, API keys, or account-specific config were copied.
- No Telegram/Discord notification behavior was copied.
- No live-trading path was enabled.
- No external dashboard/frontend stack was imported.
- No broad architecture replacement was attempted; P-core remains the canonical implementation boundary.

## Validation

The extraction was implemented with test-first phases and targeted validation. The final targeted suite is recorded in the execution plan at:

`docs/plans/2026-04-27-weather-probability-risk-intraday-extraction.md`
