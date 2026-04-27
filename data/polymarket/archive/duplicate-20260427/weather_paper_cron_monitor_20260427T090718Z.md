# Weather paper cron monitor — 20260427T090718Z

Paper only — no real orders placed. No fresh add unless Julien explicitly asks.

Summary: active=5, closed_preserved=3, spend=44.7552 USDC, EV=18.3216 USDC, MTM_bid=8.0502 USDC, actions={'SETTLED_WON': 2, 'SETTLED_LOST': 2, 'HOLD_CAPPED': 1}, alerts=4

## Alerts
- SETTLED_WON: Beijing April 26 NO25 — p=0.7815 bid/ask=None/None — official Polymarket final outcome: No
- SETTLED_WON: Munich April 26 NO18 — p=0.8951 bid/ask=None/None — official Polymarket final outcome: No
- SETTLED_LOST: Shanghai April 26 NO23 — p=0.721 bid/ask=None/None — official Polymarket final outcome: Yes
- SETTLED_LOST: Munich April 26 NO19 — p=0.9691 bid/ask=None/None — official Polymarket final outcome: Yes

## Active positions
| Position | Action | p_side | bid/ask | EV | MTM | Forecast | Official source |
|---|---:|---:|---:|---:|---:|---:|---|
| Beijing April 26 NO25 | SETTLED_WON | 0.7815 | None/None | 3.90722 | 9.120919 | 23.0°C via Beijing | https://www.wunderground.com/history/daily/cn/beijing/ZBAA |
| Munich April 26 NO18 | SETTLED_WON | 0.8951 | None/None | 2.607036 | 4.070416 | 18.0°C via Munich | https://www.wunderground.com/history/daily/de/munich/EDDM |
| Shanghai April 26 NO23 | SETTLED_LOST | 0.721 | None/None | 0.60183 | -4.74777 | 25.0°C via Pootung | https://www.wunderground.com/history/daily/cn/shanghai/ZSPD |
| Munich April 26 NO19 | SETTLED_LOST | 0.9691 | None/None | 2.454608 | -2.846156 | 18.0°C via Munich | https://www.wunderground.com/history/daily/de/munich/EDDM |
| Karachi April 27 NO36 | HOLD_CAPPED | 0.9938 | 0.66/0.71 | 8.750944 | 2.452831 | 32.0°C via Ramswamy Quarters | https://www.wunderground.com/history/daily/pk/karachi/OPKC |

Artifacts: `/home/jul/prediction_core/data/polymarket/weather_paper_cron_monitor_20260427T090718Z.json`, `/home/jul/prediction_core/data/polymarket/weather_paper_cron_monitor_20260427T090718Z.csv`, `/home/jul/prediction_core/data/polymarket/weather_paper_cron_monitor_20260427T090718Z.md`
