# Weather paper cron monitor

Generated: 2026-04-25T14:39:35Z
Mode: paper only; no real orders; no fresh adds
Spend: $73.9952 | EV: $61.294 | MTM bid: $-4.009
Actions: {'HOLD_CAPPED': 1, 'EXIT_PAPER': 3, 'HOLD': 3, 'HOLD_NEW_CAPPED': 1}
Alerts: 10

## Positions
- **HOLD_CAPPED** Seoul April 26 NO 20°C: forecast 18→16C (2026-04-26), p=0.9691, bid/ask=0.24/0.28, EV=$51.068, MTM=$-0.323 — OK; capped no-add
- **HOLD_NEW_CAPPED** Karachi April 27 NO 36°C: forecast 34→33C (2026-04-27), p=0.9691, bid/ask=0.37/0.54, EV=$8.285, MTM=$-3.019 — OK; capped no-add
- **HOLD** Munich April 26 NO 18°C: forecast 20→16C (2026-04-26), p=0.8951, bid/ask=0.69/0.7, EV=$2.607, MTM=$-0.282 — OK; no fresh add by cron rule
- **HOLD** Munich April 26 NO 19°C: forecast 20→16C (2026-04-26), p=0.9691, bid/ask=0.66/0.68, EV=$2.455, MTM=$0.077 — OK; no fresh add by cron rule
- **HOLD** Seoul April 27 NO 19°C: forecast 16→17C (2026-04-27), p=0.8951, bid/ask=0.81/0.82, EV=$0.916, MTM=$-0.122 — OK; no fresh add by cron rule
- **EXIT_PAPER** Beijing April 26 NO 24°C: forecast 26→25C (2026-04-26), p=0.7815, bid/ask=0.81/0.83, EV=$-0.094, MTM=$-0.024 — p_side below hard stop
- **EXIT_PAPER** Shanghai April 26 NO 23°C: forecast 22→23C (2026-04-26), p=0.5, bid/ask=0.63/0.68, EV=$-1.04, MTM=$-0.074 — p_side below hard stop
- **EXIT_PAPER** Beijing April 26 NO 25°C: forecast 26→25C (2026-04-26), p=0.5, bid/ask=0.61/0.62, EV=$-2.903, MTM=$-0.242 — p_side below hard stop

## Alerts
- {'position': 'Seoul April 26 NO20', 'type': 'RESOLUTION_SOURCE_AVAILABLE', 'source': 'https://www.wunderground.com/history/daily/kr/incheon/RKSI'}
- {'position': 'Beijing April 26 NO25', 'type': 'RESOLUTION_SOURCE_AVAILABLE', 'source': 'https://www.wunderground.com/history/daily/cn/beijing/ZBAA'}
- {'position': 'Beijing April 26 NO25', 'type': 'HARD_STOP', 'p_side': 0.5, 'stop': 0.59}
- {'position': 'Munich April 26 NO18', 'type': 'RESOLUTION_SOURCE_AVAILABLE', 'source': 'https://www.wunderground.com/history/daily/de/munich/EDDM'}
- {'position': 'Seoul April 27 NO19', 'type': 'RESOLUTION_SOURCE_AVAILABLE', 'source': 'https://www.wunderground.com/history/daily/kr/incheon/RKSI'}
- {'position': 'Shanghai April 26 NO23', 'type': 'RESOLUTION_SOURCE_AVAILABLE', 'source': 'https://www.wunderground.com/history/daily/cn/shanghai/ZSPD'}
- {'position': 'Shanghai April 26 NO23', 'type': 'HARD_STOP', 'p_side': 0.5, 'stop': 0.61}
- {'position': 'Munich April 26 NO19', 'type': 'RESOLUTION_SOURCE_AVAILABLE', 'source': 'https://www.wunderground.com/history/daily/de/munich/EDDM'}
- {'position': 'Beijing April 26 NO24', 'type': 'RESOLUTION_SOURCE_AVAILABLE', 'source': 'https://www.wunderground.com/history/daily/cn/beijing/ZBAA'}
- {'position': 'Beijing April 26 NO24', 'type': 'HARD_STOP', 'p_side': 0.7815, 'stop': 0.79}
