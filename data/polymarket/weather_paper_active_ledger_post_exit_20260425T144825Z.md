# Polymarket météo — ledger actif post-exit paper-only

- Mode: active paper ledger after applying EXIT_PAPER bookkeeping; no real orders
- Positions actives: 7
- Position clôturée paper: 1
- Spend actif: 72.00 USDC
- EV actif modèle: 70.68 USDC
- MTM actif bid: -2.01 USDC
- PnL paper réalisé clôture: -0.0244 USDC
- Actions actives: HOLD_CAPPED: 5, HOLD_MONITOR: 2

## Bookkeeping appliqué

- EXIT_PAPER_APPLIED: Beijing April 26 NO24 exit paper à bid `0.81` → PnL `-0.0244` USDC

## Ledger actif

| Position | Forecast | Bid/Ask | P side | EV | MTM bid | Action |
|---|---:|---:|---:|---:|---:|---|
| Seoul April 26 NO20 C higher | 16.0 | 0.26/0.29 | 0.9979 | 53.09 | 1.086 | HOLD_CAPPED |
| Beijing April 26 NO25 C exact | 25.0 | 0.61/0.62 | 0.7210 | 2.44 | -0.242 | HOLD_CAPPED |
| Munich April 26 NO18 C exact | 16.0 | 0.68/0.69 | 0.8951 | 2.61 | -0.423 | HOLD_CAPPED |
| Seoul April 27 NO19 C exact | 17.0 | 0.8/0.82 | 0.8951 | 0.92 | -0.244 | HOLD_CAPPED |
| Shanghai April 26 NO23 C exact | 23.0 | 0.65/0.68 | 0.7210 | 0.60 | 0.074 | HOLD_MONITOR |
| Munich April 26 NO19 C exact | 16.0 | 0.65/0.68 | 0.9691 | 2.46 | -0.0 | HOLD_MONITOR |
| Karachi April 27 NO36 C higher | 33.0 | 0.41/0.52 | 0.9839 | 8.56 | -2.264 | HOLD_CAPPED |

## Prochaine règle
- Continuer monitor paper-only. Aucun add automatique.
- Re-check si nouvelle alerte EXIT/TRIM/TP ou changement source officielle.

Artifacts: `weather_paper_active_ledger_post_exit_20260425T144825Z.json`, `weather_paper_active_ledger_post_exit_20260425T144825Z.csv`
