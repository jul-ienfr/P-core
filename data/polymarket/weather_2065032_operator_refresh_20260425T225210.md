# Polymarket météo 2065032 — refresh opérateur

- Généré UTC: 2026-04-25T22:52:10Z
- Mode: **paper-only / aucun ordre réel**
- Question: Will the highest temperature in Shanghai be 21°C on April 26?
- Source résolution: https://www.wunderground.com/history/daily/cn/shanghai/ZSPD

## Changement vs précédent
- aucun changement matériel vs refresh précédent

## Station ZSPD — observation partielle
- Shanghai local maintenant: **2026-04-26T06:52:10+08:00**
- Journée complète: **False** — reste ~**17.13h**
- Observations API: **13**
- Max vu: **12.8°C** / rounded 13°C
- Valeurs arrondies vues: `[12, 13]`
- Exact 21°C vu jusqu’ici: **False**

## Carnet NO
- NO best bid: `0.949`
- NO best ask: `0.954`
- Top ask size: `0.47`
- Limite paper stricte: `0.954`

## Décision
`WAIT_PARTIAL_DAY_STILL_RUNNING`

Règle: pas de fill final tant que la journée locale n’est pas complète et que l’historique officiel/source n’est pas finalisé. Si final rounded max ≠ 21°C et NO ask ≤ 0.954, seulement micro-fill paper max 0.45 USDC.