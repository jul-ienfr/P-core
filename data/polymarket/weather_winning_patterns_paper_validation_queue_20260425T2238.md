# Polymarket météo — paper validation queue

- Généré: 2026-04-25T22:37:18Z
- Mode: **paper-only / no real orders**
- Objectif: transformer les patterns gagnants en file de validation, pas en ordres live.

## Synthèse
- Candidats: 5
- Éligibles maintenant: 0
- Source-check first: 3
- Micro-only: 2

## Queue priorisée
| rank | market | surface | NO bid/ask | ask size | limit | budget | action | blockers |
|---:|---|---|---:|---:|---:|---:|---|---|
| 1 | 2065210 | Moscow April 26 12°C | 0.967/0.988 | 100.0 | 0.988 | 2.0 | SOURCE_CHECK_FIRST_THEN_PAPER_LIMIT | official_source_not_confirmed |
| 2 | 2065032 | Shanghai April 26 21°C | 0.95/0.954 | 0.47 | 0.954 | 5.0 | SOURCE_CHECK_FIRST_THEN_PAPER_LIMIT | thin_top_ask, official_source_not_confirmed |
| 3 | 2074474 | Shanghai April 27 24°C | 0.984/0.989 | 30.0 | 0.989 | 2.0 | SOURCE_CHECK_FIRST_THEN_PAPER_LIMIT | official_source_not_confirmed |
| 4 | 2065108 | Beijing April 26 22°C | 0.987/0.998 | 90.9 | 0.998 | 1.0 | MICRO_ONLY_AFTER_SOURCE_CHECK | extreme_price, official_source_not_confirmed |
| 5 | 2064990 | Munich April 26 16°C | 0.99/0.993 | 144.42 | 0.993 | 1.0 | MICRO_ONLY_AFTER_SOURCE_CHECK | extreme_price, official_source_not_confirmed |

## Règles de fill papier
- Ne simuler un fill que si la source officielle de résolution est confirmée.
- Ne jamais prendre au-dessus de `strict_limit`.
- Si `extreme_price`, budget paper limité à 1 USDC; aucun sizing normal.
- Si source non confirmée, priorité = trouver la règle/source officielle Polymarket du marché.

## Prochaine étape concrète
Résoudre `official_source_not_confirmed` pour le top candidat avant toute simulation: ouvrir la règle/résolution du marché et mapper la station/source officielle.