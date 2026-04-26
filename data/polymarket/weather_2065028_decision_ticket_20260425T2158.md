# 2065028 decision ticket — 20260425T2158

## Decision
- Global action: `HOLD`
- Position action: `TRIM_REVIEW`
- Add size: `NO`
- Real order: `NO`
- Reason: official daily extract still pending; existing paper position is review/trim, not add.

## Fresh source
- HKO current: `23°C` at `2026-04-26T03:02:00+08:00`
- Official daily: `pending`
- Resolution action: `monitor_until_official_daily_extract`

## Existing paper position
- Side: `NO`; entry `0.977`; p_side_now `0.995`; EV `0.092 USDC`; shares `5.117707`
- Stop/trim/take-profit: hard_stop `0.947`, trim_review `0.997`, take_profit_review `0.98`

## Matched accounts
- Poligarch / Maskache2 / HenryTheAtmoPhD / JoeTheMeteorologist / protrade3

## Next
- `wait_for_hko_official_daily_extract`
- `do_not_add_size`
- `review_trim_or_take_profit_if_bid_probability_moves`
- `keep_no_real_order`