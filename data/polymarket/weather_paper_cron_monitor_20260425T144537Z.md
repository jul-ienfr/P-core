# Polymarket météo — monitor paper-only 20260425T144537Z

- Mode: manual continuation monitor, paper only; no real orders; no fresh adds
- Positions: 8
- Spend: 74.00 USDC
- EV modèle: 70.59 USDC
- MTM bid: -2.04 USDC
- Actions: EXIT_PAPER: 1, HOLD_CAPPED: 5, HOLD_MONITOR: 2

## Décision

Alertes: **EXIT_PAPER Beijing April 26 NO24**

| Position | Forecast | Bid/Ask | P side | EV | MTM bid | Action | Raison |
|---|---:|---:|---:|---:|---:|---|---|
| Seoul April 26 NO20 C higher | 16.0 | 0.26/0.29 | 0.9979 | 53.09 | 1.086 | HOLD_CAPPED | large position; no further add |
| Beijing April 26 NO25 C exact | 25.0 | 0.61/0.62 | 0.7210 | 2.44 | -0.242 | HOLD_CAPPED | large position; no further add |
| Munich April 26 NO18 C exact | 16.0 | 0.68/0.69 | 0.8951 | 2.61 | -0.423 | HOLD_CAPPED | large position; no further add |
| Seoul April 27 NO19 C exact | 17.0 | 0.8/0.82 | 0.8951 | 0.92 | -0.244 | HOLD_CAPPED | large position; no further add |
| Shanghai April 26 NO23 C exact | 23.0 | 0.65/0.68 | 0.7210 | 0.60 | 0.074 | HOLD_MONITOR | OK |
| Munich April 26 NO19 C exact | 16.0 | 0.65/0.68 | 0.9691 | 2.46 | -0.0 | HOLD_MONITOR | OK |
| Beijing April 26 NO24 C exact | 25.0 | 0.81/0.84 | 0.7815 | -0.09 | -0.024 | EXIT_PAPER | p_side 0.7815 < hard_stop 0.7900 |
| Karachi April 27 NO36 C higher | 33.0 | 0.41/0.52 | 0.9839 | 8.56 | -2.264 | HOLD_CAPPED | large position; no further add |

## Règles
- Paper-only: aucun ordre réel, aucun nouvel add automatique.
- Si EXIT/TRIM apparaît: décision de bookkeeping papier uniquement.
- Garder le runbook exécution séparé pour le candidat Hong Kong 2065028; ce monitor suit le ledger paper existant.

Artifacts: `weather_paper_cron_monitor_20260425T144537Z.json`, `weather_paper_cron_monitor_20260425T144537Z.csv`
