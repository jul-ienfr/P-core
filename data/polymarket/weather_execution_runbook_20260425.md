# Polymarket météo — runbook exécution paper/micro

- Recommandation globale: **paper_micro_only**
- Raison: unique_profitable_weather_accounts_match_live_markets_but_extreme_price_blocks_normal_sizing
- Actions globales: poll_direct_resolution_source, paper_micro_order_with_strict_limit_and_fill_tracking, do_not_use_normal_size_until_extreme_price_clears
- Règle sécurité: **aucun ordre réel / aucun sizing normal** tant que `extreme_price`, quote manquante ou daily officiel pending.

## Décision immédiate

1. **Paper/micro candidate prioritaire**: `2065028` Hong Kong Apr 26 — side préféré `NO`, entrée papier si NO ask <= `0.978`; HKO latest 24C vs seuil 30C, daily officiel encore pending.
2. `2065018` Hong Kong Apr 26 — signal directionnel NO mais prix trop extrême; seulement micro paper/diagnostic, pas sizing.
3. Dallas: attendre quote/depth/tighter spread; les signaux météo vont plutôt vers YES sur high-threshold, mais coût/spread bloquant.

## Checklist avant toute paper exécution

- Re-poller HKO current weather et official daily extract.
- Re-poller order book Polymarket juste avant entrée.
- Refuser si ask dépasse la limite du plan.
- Logguer prix limite, fill simulé, timestamp source météo, et statut official daily.

## Table exécution

| market | city | date | side | rating | entry rule | blocker | verdict | latest value | latest ts | official available | top accounts | next |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2065018 | Hong Kong | April 26 | No but skip | C | skip; too priced-in. | extreme_price | paper_micro | 24.0 | 2026-04-25T21:00:00+08:00 | False | Poligarch $50,120.07 / Maskache2 $49,973.43 / HenryTheAtmoPhD $45,563.27 | poll_direct_resolution_source, paper_micro_order_with_strict_limit_and_fill_tracking |
| 2065028 | Hong Kong | April 26 | No | A | NO only if ask <=0.978 for paper; skip if >0.98; target hold to resolution only paper/micro. | none | watch_or_paper | 24.0 | 2026-04-25T21:00:00+08:00 | False | Poligarch $50,120.07 / Maskache2 $49,973.43 / HenryTheAtmoPhD $45,563.27 | poll_direct_resolution_source, paper_order_with_limit_and_fill_tracking |
| 2074350 | Dallas | April 27 | No but skip | C | skip; too priced-in. | missing_tradeable_quote | watch_or_paper |  |  | False | Handsanitizer23 $71,174.40 / Shoemaker34 $33,959.87 / khalidakup $29,585.79 | poll_direct_resolution_source, wait_for_executable_depth |
| 2074460 | Hong Kong | April 27 | No but skip | C | skip; too priced-in. | missing_tradeable_quote | watch_or_paper | 24.0 | 2026-04-25T21:00:00+08:00 | False | Poligarch $50,120.07 / Maskache2 $49,973.43 / HenryTheAtmoPhD $45,563.27 | poll_direct_resolution_source, wait_for_executable_depth |
| 2064908 | Dallas | April 26 | No but skip | C | skip; too priced-in. | missing_tradeable_quote | watch_or_paper |  |  | False | Handsanitizer23 $71,174.40 / Shoemaker34 $33,959.87 / khalidakup $29,585.79 | poll_direct_resolution_source, wait_for_executable_depth |
| 2074470 | Hong Kong | April 27 | No | A- | NO only if ask <=0.978 for paper; skip if >0.98; target hold to resolution only paper/micro. | missing_tradeable_quote | watch_or_paper | 24.0 | 2026-04-25T21:00:00+08:00 | False | Poligarch $50,120.07 / Maskache2 $49,973.43 / HenryTheAtmoPhD $45,563.27 | poll_direct_resolution_source, wait_for_executable_depth |
| 2074360 | Dallas | April 27 | Yes but skip/only tiny if discount | B- watch | YES only if ask materially below forecast fair; current ask too high/spread costly. | missing_tradeable_quote | watch_or_paper |  |  | False | Handsanitizer23 $71,174.40 / Shoemaker34 $33,959.87 / khalidakup $29,585.79 | poll_direct_resolution_source, wait_for_executable_depth |
| 2064918 | Dallas | April 26 | Yes but skip/only tiny if discount | B watch | YES only if ask materially below forecast fair; current ask too high/spread costly. | high_slippage_risk | watch_or_paper |  |  | False | Handsanitizer23 $71,174.40 / Shoemaker34 $33,959.87 / khalidakup $29,585.79 | poll_direct_resolution_source, wait_for_tighter_spread |

## Sources directes à surveiller

- Hong Kong: https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en
- Dallas: https://www.wunderground.com/history/daily/us/tx/dallas/KDAL

## Conclusion

Le seul candidat propre côté exécution papier est Hong Kong `2065028` NO sous limite stricte. Le reste sert au monitoring: soit prix extrême, soit quote manquante, soit spread trop coûteux.