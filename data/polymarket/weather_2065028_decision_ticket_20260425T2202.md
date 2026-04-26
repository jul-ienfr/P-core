# 2065028 decision ticket — 20260425T2202

## Decision
- Global action: `HOLD`
- Position action: `TRIM_REVIEW`
- Add size: `NO`
- Real order: `NO`
- Reason: official_daily_extract_pending; existing_paper_position_not_add_allowed; trim_review_active

## Fresh source
- HKO current: `23°C` at `2026-04-26T03:02:00+08:00`
- Official daily: `pending`
- Resolution action: `monitor_until_official_daily_extract`

## Existing paper position
- Side: `NO`; entry `0.977`; p_side_now `0.995`; EV `0.092 USDC`; shares `5.117707`
- Stop/trim/take-profit: hard_stop `0.947`, trim_review `0.997`, take_profit_review `0.98`

## Matched profitable weather accounts
- Poligarch / Maskache2 / HenryTheAtmoPhD / JoeTheMeteorologist / protrade3

## Next actions
- `wait_for_hko_official_daily_extract`
- `do_not_add_size`
- `review_trim_or_take_profit_if_bid_probability_moves`
- `keep_no_real_order`

## Artifacts
- `data/polymarket/weather_2065028_decision_ticket_20260425T2202.json`
- `data/polymarket/weather_2065028_decision_ticket_20260425T2202.md`
- `data/polymarket/weather_paper_operator_watchlist_with_2065028_20260425T2050.json`
