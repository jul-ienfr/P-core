# Weather paper cron monitor — 20260427T091921Z

Paper only — no real orders placed. No fresh add unless Julien explicitly asks.

Summary: active=5, closed_preserved=3, spend=44.7552 USDC, EV=18.3216 USDC, MTM_bid=9.9370 USDC, actions={'SETTLED_WON': 2, 'SETTLED_LOST': 2, 'HOLD_CAPPED': 1}, alerts=4

## Portfolio PnL
- Counts: open=1, settled=4, exit_paper=3, total=8
- Realized: 7.135920 USDC (settled=3.522800, exit_paper=3.613120)
- Open MTM bid: 4.339623 USDC
- Realized + open MTM: 11.475543 USDC
- If open loses: -2.864080 USDC; if open wins full payout: 16.003845 USDC
- Official hold-to-settlement PnL for EXIT_PAPER rows: -19.240000 USDC (postmortem only; does not rewrite exit PnL)

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
| Karachi April 27 NO36 | HOLD_CAPPED | 0.9938 | 0.76/0.8 | 8.750944 | 4.339623 | 32.0°C via Ramswamy Quarters | https://www.wunderground.com/history/daily/pk/karachi/OPKC |

## Closed / exited positions
| Position | Action | Exit PnL | Official final | Official hold-to-settlement PnL |
|---|---:|---:|---:|---:|
| Seoul April 27 NO19 | EXIT_PAPER | -0.24384 | UNSETTLED  | None |
| Beijing April 26 NO24 | EXIT_PAPER | -0.0488 | SETTLED_LOST Yes | -2.0 |
| Seoul April 26 NO20 | EXIT_PAPER | 3.90576 | SETTLED_LOST Yes | -17.24 |

Artifacts: `/home/jul/prediction_core/data/polymarket/weather_paper_cron_monitor_20260427T091921Z.json`, `/home/jul/prediction_core/data/polymarket/weather_paper_cron_monitor_20260427T091921Z.csv`, `/home/jul/prediction_core/data/polymarket/weather_paper_cron_monitor_20260427T091921Z.md`
