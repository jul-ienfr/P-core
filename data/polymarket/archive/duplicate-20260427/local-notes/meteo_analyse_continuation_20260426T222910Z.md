# METEO ANALYSE — continuation 20260426T222910Z

Paper-only. Aucun ordre réel placé. Pas d'ajout frais sans instruction explicite de Julien.

## Vérification repo

- Repo: `/home/jul/prediction_core`
- Git: `main...origin/main`, avec changements non trackés sur la nouvelle zone `strategies/` et tests associés.
- Tests ciblés: `96 passed in 15.85s`
- Commande: `cd /home/jul/prediction_core/python && PYTHONPATH=src python3 -m pytest tests/test_server_smoke.py tests/test_paper_cycle_report.py tests/test_paper_watchlist_cli.py tests/test_resolution_monitor.py tests/test_station_history_client.py tests/test_weather_latency_edge.py -q`

## Monitor paper le plus récent

- Artifact source: `/home/jul/prediction_core/data/polymarket/weather_paper_cron_monitor_20260426T124621Z.md`
- Summary: active=5, closed_preserved=3, spend=44.7552 USDC, EV=18.4198 USDC, MTM_bid=5.9748 USDC, actions={'HOLD_CAPPED': 5}, alerts=0

## Crons / monitoring

- Cronjobs Hermes actifs: aucun job Polymarket météo visible dans cronjob list actuel; dernier monitor artifact disponible: weather_paper_cron_monitor_20260426T124621Z.md.

## Décision opérateur

- Action globale: **HOLD / HOLD_CAPPED**
- Ajout: **non autorisé maintenant**
- Valeur espérée positive: contexte modèle, pas permission d'ajouter.
- Valorisation au marché actuel: à suivre séparément de l'EV.
- Prochain déclencheur: source officielle publiée, alerte de trim/exit, ou demande explicite de Julien.

## Positions actives vues dans le dernier monitor

| Position | Action | p_side | bid/ask | EV | MTM | Forecast | Official source |
|---|---:|---:|---:|---:|---:|---:|---|
| Beijing April 26 NO25 | HOLD_CAPPED | 0.7815 | 0.997/None | 3.90722 | 9.120919 | 24.0°C via Beijing | https://www.wunderground.com/history/daily/cn/beijing/ZBAA |
| Munich April 26 NO18 | HOLD_CAPPED | 0.8951 | 0.999/None | 2.607036 | 4.070416 | 16.0°C via Munich | https://www.wunderground.com/history/daily/de/munich/EDDM |
| Shanghai April 26 NO23 | HOLD_CAPPED | 0.721 | 0.001/0.004 | 0.60183 | -4.74777 | 23.0°C via Pootung | https://www.wunderground.com/history/daily/cn/shanghai/ZSPD |
| Munich April 26 NO19 | HOLD_CAPPED | 0.9691 | 0.28/0.31 | 2.454608 | -2.846156 | 16.0°C via Munich | https://www.wunderground.com/history/daily/de/munich/EDDM |
| Karachi April 27 NO36 | HOLD_CAPPED | 0.999 | 0.55/0.59 | 8.849057 | 0.377359 | 31.0°C via Ramswamy Quarters | https://www.wunderground.com/history/daily/pk/karachi/OPKC |
