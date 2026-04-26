# METEO ANALYSE continuation — 20260426T141337

## État vérifié

- Repo: `/home/jul/prediction_core`
- Tests ciblés lancés depuis `python/`:
  - `test_server_smoke.py`
  - `test_paper_cycle_report.py`
  - `test_paper_watchlist_cli.py`
  - `test_resolution_monitor.py`
  - `test_station_history_client.py`
  - `test_weather_latency_edge.py`
- Résultat: `96 passed in 15.79s`

## Monitoring actif

- Cron HKO officiel marché paper `2065028`: actif, toutes les 120 min, prochain run ~15:30 Paris.
- Cron portefeuille paper météo: actif, toutes les 60 min, prochain run ~14:46 Paris.

## Dernier snapshot portefeuille paper

# Weather paper cron monitor — 20260426T114535Z

Paper only — no real orders placed. No fresh add unless Julien explicitly asks.

Summary: active=5, closed_preserved=3, spend=44.7552 USDC, EV=18.4198 USDC, MTM_bid=4.4049 USDC, actions={'HOLD_CAPPED': 5}, alerts=0

## Active positions
| Position | Action | p_side | bid/ask | EV | MTM | Forecast | Official source |
|---|---:|---:|---:|---:|---:|---:|---|
| Beijing April 26 NO25 | HOLD_CAPPED | 0.7815 | 0.997/None | 3.90722 | 9.120919 | 24.0°C via Beijing | https://www.wunderground.com/history/daily/cn/beijing/ZBAA |
| Munich April 26 NO18 | HOLD_CAPPED | 0.8951 | 0.964/0.987 | 2.607036 | 3.577458 | 16.0°C via Munich | https://www.wunderground.com/history/daily/de/munich/EDDM |
| Shanghai April 26 NO23 | HOLD_CAPPED | 0.721 | 0.001/0.004 | 0.60183 | -4.74777 | 23.0°C via Pootung | https://www.wunderground.com/history/daily/cn/shanghai/ZSPD |
| Munich April 26 NO19 | HOLD_CAPPED | 0.9691 | 0.14/0.2 | 2.454608 | -3.923078 | 16.0°C via Munich | https://www.wunderground.com/history/daily/de/munich/EDDM |
| Karachi April 27 NO36 | HOLD_CAPPED | 0.999 | 0.55/0.59 | 8.849057 | 0.377359 | 31.0°C via Ramswamy Quarters | https://www.wunderground.com/history/daily/pk/karachi/OPKC |

Artifacts: `/home/jul/prediction_core/data/polymarket/weather_paper_cron_monitor_20260426T114535Z.json`, `/home/jul/prediction_core/data/polymarket/weather_paper_cron_monitor_20260426T114535Z.csv`, `/home/jul/prediction_core/data/polymarket/weather_paper_cron_monitor_20260426T114535Z.md`


## Décision opérateur actuelle

- Paper only: aucun ordre réel.
- Portefeuille: HOLD / HOLD_CAPPED.
- Pas d'ajout frais sans demande explicite Julien.
- Point clé: plusieurs positions ont EV papier positive, mais la règle reste de surveiller source officielle + book; EV positive ≠ permission d'ajouter.

## Prochaine action utile

Attendre le prochain poll officiel HKO / monitor hourly, puis décider uniquement si:
1. une source officielle quotidienne confirme une résolution, ou
2. une position passe en trim/take-profit/exit review, ou
3. Julien demande explicitement une nouvelle entrée paper.
