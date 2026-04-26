# Paper execution log — 2065028 Hong Kong NO

- Mode: **paper only** — no real order.
- Market: `2065028` — Will the highest temperature in Hong Kong be 30°C or higher on April 26?
- Side: **NO**
- Decision: **paper_order_eligible**
- Limit: `0.978`
- Observed NO ask: `0.975`
- Paper notional: `$5.0`
- Estimated shares: `5.1282`

## Weather source

- Latest HKO direct: `24.0C` at `2026-04-25T21:00:00+08:00`
- Threshold: `30C or higher`
- Provisional outcome: `no`
- Official daily extract: `False`
- Operator action: `monitor_until_official_daily_extract`

## Risk controls

- No real order.
- No normal sizing.
- Hold result as provisional until official daily extract.
- Recheck book before any follow-up paper fill.
