# Polymarket météo — refresh opérateur 2026-04-25 17:00 CEST

## Verdict

- Recommandation globale: **paper_micro_only**
- Marchés live matchant comptes météo rentables: **8**
- Comptes rentables uniques matchés: **10**
- Règle: **paper/micro uniquement**, aucun sizing normal tant que daily officiel pending ou blocker execution.

## Candidat principal

| market | ville/date | side | statut | source directe | latest | officiel | action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `2065028` | Hong Kong Apr 26 | NO | executable papier | HKO API | 24°C à 22:00 HKT | pending | paper order strict limit + fill tracking |

Lecture: seuil 30°C, latest HKO 24°C => outcome provisoire NO. Daily officiel pas publié, donc pas final.

## Autres signaux live

| market | ville/date | signal comptes | blocker | action |
| --- | --- | ---: | --- | --- |
| `2065018` | Hong Kong Apr 26 | 5 comptes heavy | extreme_price | micro paper diagnostic uniquement |
| `2074350` | Dallas Apr 27 | 5 comptes heavy | missing_tradeable_quote | attendre quote/depth |
| `2074460` | Hong Kong Apr 27 | 5 comptes heavy | missing_tradeable_quote | attendre quote/depth |
| `2064908` | Dallas Apr 26 | 5 comptes heavy | missing_tradeable_quote | attendre quote/depth |
| `2074470` | Hong Kong Apr 27 | 5 comptes heavy | missing_tradeable_quote | attendre quote/depth |
| `2074360` | Dallas Apr 27 | 5 comptes heavy | missing_tradeable_quote | attendre quote/depth |
| `2064918` | Dallas Apr 26 | 5 comptes heavy | high_slippage_risk | attendre spread plus serré |

## Comptes matchés live

Hong Kong: Poligarch, Maskache2, HenryTheAtmoPhD, JoeTheMeteorologist, protrade3.

Dallas: Handsanitizer23, Shoemaker34, khalidakup, David32534, Junhoo2.

## À faire maintenant

1. Re-poller HKO avant toute simulation sur `2065028`.
2. Vérifier orderbook: entrer papier seulement si NO ask <= `0.978`.
3. Logger timestamp source météo + prix limite + fill simulé.
4. Continuer monitoring daily officiel HKO; tant que pending, résultat non final.

Artifacts source:
- `data/polymarket/weather_operator_refresh_20260425T1700.json`
- `data/polymarket/weather_strategy_operator_report_refreshed_20260425T1700.json`
- `data/polymarket/weather_profitable_accounts_operator_summary_20260425T1700.json`
