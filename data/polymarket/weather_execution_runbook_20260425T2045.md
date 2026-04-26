# Execution runbook — 20260425T2045

## Verdict
- Mode: `paper_only` / aucune transaction réelle.
- Reco globale: `paper_micro_only`.
- Candidat principal: `2065028` — Hong Kong April 26 — blocker `none` — verdict `watch_or_paper`.
- Action: si entrée papier, uniquement micro strict-limit après re-poll source + orderbook; refuser tout fill au-dessus de la limite.

## Candidat principal live
- Question: n/a
- Matched profitable weather: 5 comptes — top: Poligarch $50,120 / Maskache2 $49,973 / HenryTheAtmoPhD $45,563
- Source latest: https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en
- Source history: https://data.weather.gov.hk/weatherAPI/opendata/opendata.php?dataType=CLMMAXT&rformat=json&station=HKO&year=2026&month=4
- Polling focus: hko_current_weather_api_and_daily_extract / latency=direct_latest

## Source résolution
- Latest direct: `{'available': True, 'latency_tier': 'direct_latest', 'timestamp': '2026-04-26T02:00:00+08:00', 'value': 23.0}`
- Official daily extract: `{'available': False, 'latency_tier': 'direct_daily_extract', 'timestamp': None, 'value': None}`
- Action résolution: `monitor_until_official_daily_extract`
- HKO live fetch: `2026-04-26T02:02:00+08:00`

## Orderbook live
- n/a

## Pré-check avant papier
1. Re-poll direct source (`source_latest_url`) et noter timestamp/valeur.
2. Re-poll Gamma + CLOB pour les deux tokens.
3. Si `official_daily_extract` pending: garder provisoire, ne pas marquer final.
4. Si ask dépasse la limite stricte ou depth insuffisante: no-fill papier.
5. Logger fill simulé + source timestamp + book snapshot.

## Watchlist papier actuelle
- Positions: 8; total_spend=58.9952; total_ev_now=28.16
- Actions: `{'HOLD_CAPPED': 3, 'HOLD_MONITOR': 4, 'TRIM_REVIEW': 1}`
- Position existante sur candidat: aucune dans cette watchlist dérivée.

## Artefacts sources
- `data/polymarket/weather_profitable_accounts_operator_summary_20260425T2043.json`
- `data/polymarket/weather_operator_refresh_20260425T2043.json`
- `data/polymarket/weather_paper_operator_watchlist_with_2065028_20260425T2039.json`
- `data/polymarket/weather_execution_runbook_20260425T2045.md`