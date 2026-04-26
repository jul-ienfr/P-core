# Weather paper cron monitor

Generated: 2026-04-25T14:38:55Z
Mode: paper only; no real orders; no fresh adds
Spend: $73.9952 | EV: $67.482 | MTM bid: $-2.642
Actions: {'HOLD_CAPPED': 1, 'HOLD': 5, 'EXIT_PAPER': 1, 'HOLD_NEW_CAPPED': 1}
Alerts: 8

## Positions
- **HOLD_CAPPED** Seoul April 26 NO 20°C: forecast 18→17C, p=0.9691, bid/ask=None/None, EV=$51.068, MTM=$None — OK; capped no-add
- **HOLD** Beijing April 26 NO 25°C: forecast 26→29C, p=0.9691, bid/ask=None/None, EV=$8.446, MTM=$None — OK; no fresh add by cron rule
- **HOLD_NEW_CAPPED** Karachi April 27 NO 36°C: forecast 34→34C, p=0.858, bid/ask=0.39/0.53, EV=$6.189, MTM=$-2.642 — OK; capped no-add
- **HOLD** Shanghai April 26 NO 23°C: forecast 22→20C, p=0.9691, bid/ask=None/None, EV=$2.445, MTM=$None — OK; no fresh add by cron rule
- **HOLD** Munich April 26 NO 19°C: forecast 20→18C, p=0.7815, bid/ask=None/None, EV=$1.012, MTM=$None — OK; no fresh add by cron rule
- **HOLD** Seoul April 27 NO 19°C: forecast 16→17C, p=0.8951, bid/ask=None/None, EV=$0.916, MTM=$None — OK; no fresh add by cron rule
- **HOLD** Beijing April 26 NO 24°C: forecast 26→29C, p=0.9691, bid/ask=None/None, EV=$0.364, MTM=$None — OK; no fresh add by cron rule
- **EXIT_PAPER** Munich April 26 NO 18°C: forecast 20→18C, p=0.5, bid/ask=None/None, EV=$-2.958, MTM=$None — p_side below hard stop

## Alerts
- {'position': 'Seoul April 26 NO20', 'type': 'RESOLUTION_SOURCE_AVAILABLE', 'source': 'https://www.wunderground.com/history/daily/kr/incheon/RKSI'}
- {'position': 'Beijing April 26 NO25', 'type': 'RESOLUTION_SOURCE_AVAILABLE', 'source': 'https://www.wunderground.com/history/daily/cn/beijing/ZBAA'}
- {'position': 'Munich April 26 NO18', 'type': 'RESOLUTION_SOURCE_AVAILABLE', 'source': 'https://www.wunderground.com/history/daily/de/munich/EDDM'}
- {'position': 'Munich April 26 NO18', 'type': 'HARD_STOP', 'p_side': 0.5, 'stop': 0.68}
- {'position': 'Seoul April 27 NO19', 'type': 'RESOLUTION_SOURCE_AVAILABLE', 'source': 'https://www.wunderground.com/history/daily/kr/incheon/RKSI'}
- {'position': 'Shanghai April 26 NO23', 'type': 'RESOLUTION_SOURCE_AVAILABLE', 'source': 'https://www.wunderground.com/history/daily/cn/shanghai/ZSPD'}
- {'position': 'Munich April 26 NO19', 'type': 'RESOLUTION_SOURCE_AVAILABLE', 'source': 'https://www.wunderground.com/history/daily/de/munich/EDDM'}
- {'position': 'Beijing April 26 NO24', 'type': 'RESOLUTION_SOURCE_AVAILABLE', 'source': 'https://www.wunderground.com/history/daily/cn/beijing/ZBAA'}
