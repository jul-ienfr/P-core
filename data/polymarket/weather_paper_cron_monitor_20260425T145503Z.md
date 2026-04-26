# Polymarket météo — monitor paper-only 20260425T145503Z

- Mode: cron monitor, paper only; no real orders; no fresh adds
- Positions: 8
- Spend: 74.00 USDC
- EV modèle: 69.91 USDC
- MTM bid: -1.93 USDC
- Actions: EXIT_PAPER: 1, HOLD_CAPPED: 5, HOLD_MONITOR: 2

## Décision

Alertes: **OFFICIAL_RESOLUTION_SOURCE_AVAILABLE Beijing April 26 NO24; EXIT_PAPER Beijing April 26 NO24**

| Position | Forecast | Bid/Ask | P side | EV | MTM bid | Action | Raison |
|---|---:|---:|---:|---:|---:|---|---|
| Seoul April 26 NO20 C higher | 16.0 | 0.27/0.29 | 0.9938 | 52.81 | 1.791 | HOLD_CAPPED | large/capped position; no further add |
| Beijing April 26 NO25 C exact | 25.0 | 0.61/0.62 | 0.7210 | 2.44 | -0.242 | HOLD_CAPPED | large/capped position; no further add |
| Munich April 26 NO18 C exact | 16.0 | 0.69/0.72 | 0.8951 | 2.61 | -0.282 | HOLD_CAPPED | large/capped position; no further add |
| Seoul April 27 NO19 C exact | 17.0 | 0.8/0.81 | 0.8951 | 0.92 | -0.244 | HOLD_CAPPED | large/capped position; no further add |
| Shanghai April 26 NO23 C exact | 23.0 | 0.63/0.66 | 0.7210 | 0.60 | -0.074 | HOLD_MONITOR | OK |
| Munich April 26 NO19 C exact | 16.0 | 0.65/0.68 | 0.9691 | 2.46 | -0.0 | HOLD_MONITOR | OK |
| Beijing April 26 NO24 C exact | 25.0 | 0.8/0.84 | 0.7815 | -0.09 | -0.049 | EXIT_PAPER | p_side 0.7815 < hard_stop 0.7900 |
| Karachi April 27 NO36 C higher | 33.0 | 0.38/0.55 | 0.9629 | 8.17 | -2.83 | HOLD_CAPPED | large/capped position; no further add |

## Règles
- Paper-only: aucun ordre réel, aucun nouvel add automatique.
- Seoul Apr26 NO20 et Karachi Apr27 NO36 restent capped/no-add.

Artifacts: `weather_paper_cron_monitor_20260425T145503Z.json`, `weather_paper_cron_monitor_20260425T145503Z.csv`