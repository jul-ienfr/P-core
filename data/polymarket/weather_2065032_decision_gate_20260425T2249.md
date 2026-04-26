# Shanghai 2065032 — decision gate

- Généré: 2026-04-25T22:41:34Z
- Mode: **paper-only / no real order**

## Source
- Wunderground ZSPD historique API répond bien.
- Observations récupérées: **13**.
- Max partiel observé API: **55°F ≈ 12.8°C**.
- Attention: journée pas finalisée; ce n’est pas encore le max final.

## Verdict provisoire
- Pour le marché exact **21°C**, le NO est supporté **jusqu’ici** par les observations partielles.
- Mais il faut attendre/repoller la journée complète finalisée avant de simuler un fill propre.

## Gate d’exécution paper
| condition | statut |
|---|---|
| Source station exacte | OK — Wunderground ZSPD |
| Historique API accessible | OK |
| Journée finalisée | NON |
| Carnet strict-limit | Dernier NO ask 0.954 |
| Top ask size | 0.47 — très fin |
| Ordre réel | NON |

## Action
`WAIT_FINAL_HISTORY_THEN_TINY_PAPER_IF_NO_21C_AND_ASK_LE_LIMIT`

Règle stricte: si le max final arrondi ≠ 21°C et NO ask ≤ 0.954, simuler au maximum **0.45 USDC** paper; sinon skip.