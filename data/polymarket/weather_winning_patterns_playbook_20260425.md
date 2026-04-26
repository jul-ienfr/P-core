# Polymarket météo — playbook patterns gagnants

## Principe central
Les comptes gagnants ne jouent pas un titre isolé. Ils construisent une surface `ville/date/unité`, cherchent les incohérences entre bins/seuils, puis n’entrent que si la source officielle et le carnet permettent une exécution stricte.

## 3 règles à suivre
1. **Surface d’abord** — regrouper tous les marchés météo d’une même ville/date avant de décider. Un exact bin seul est trompeur.
2. **Source officielle avant conviction** — forecast/proxy sert à filtrer; la décision vient de la station/source de résolution officielle.
3. **Strict-limit + micro-sizing** — ordre seulement si `ask <= limite`; si le prix bouge, on ne chase pas. Taille micro tant que la boucle n’est pas validée.

## 3 pièges à éviter
1. **Copier les comptes gagnants sans validation** — leur activité est une carte, pas un signal final.
2. **Confondre proxy et résolution** — un forecast aligné ne vaut pas une résolution officielle.
3. **Surpayer un NO quasi certain** — à `0.98–0.995`, un bon signal peut devenir mauvais si spread/slippage/risque source mangent l’edge.

## Playbook de lecture d’un marché météo
1. Identifier la surface complète: ville, date, unité, station/source de résolution.
2. Lister exact bins + thresholds voisins; vérifier la cohérence monotone et les trous de pricing.
3. Comparer avec les comptes rentables: nombre de comptes, weather-heavy vs généralistes, récence.
4. Déterminer le side par la source: YES/NO selon température officielle probable, pas selon l’intuition du titre.
5. Vérifier carnet: ask cible, spread, profondeur, fill moyen sur petite taille.
6. Classer: `watch_only`, `paper_micro`, `paper_strict_limit`, ou `skip`.
7. Après entrée paper: monitor source officielle + bid de sortie; pas d’ajout si watchlist dit HOLD/TRIM_REVIEW.

## Scoring opérateur simple
| Signal | Bon signe | Mauvais signe |
|---|---|---|
| Comptes rentables | plusieurs weather-heavy récents sur même surface | uniquement généralistes/inactifs |
| Source | station officielle directe disponible | proxy-only ou fetch error |
| Structure prix | bin/seuil incohérent avec voisins | prix déjà efficient ou contradictoire |
| Carnet | ask sous limite, spread serré, profondeur suffisante | missing quote, spread large, ask extrême |
| Timing | proche résolution avec source directe monitorable | loin résolution sans avantage info |

## Surfaces actuelles à surveiller — proxy aligned, pas ordre live
| surface | side | comptes | signaux | statut |
|---|---:|---:|---:|---|
| Moscow April 26 12°C | NO | 9 | 32 | source_proxy_aligned_needs_official_check |
| Shanghai April 26 21°C | NO | 10 | 30 | source_proxy_aligned_needs_official_check |
| Beijing April 26 22°C | NO | 8 | 23 | source_proxy_aligned_needs_official_check |
| Seoul April 26 17°C | NO | 10 | 28 | source_proxy_aligned_needs_official_check |
| Munich April 26 16°C | NO | 11 | 38 | source_proxy_aligned_needs_official_check |
| Shanghai April 27 24°C | NO | 3 | 29 | source_proxy_aligned_needs_official_check |
| Seoul April 27 15°C | NO | 6 | 23 | source_proxy_aligned_needs_official_check |
| London April 26 20°C | NO | 11 | 27 | source_proxy_aligned_needs_official_check |

## Candidats carnet à traiter en paper/validation
| market | surface | side | ask | tradability | note |
|---|---|---:|---:|---|---|
| 2065210 | Moscow April 26 12°C | NO | 0.987 | ok | micro seulement |
| 2065032 | Shanghai April 26 21°C | NO | 0.954 | ok | validation source+carnet |
| 2065108 | Beijing April 26 22°C | NO | 0.995 | extreme_or_missing | micro seulement |
| 2064990 | Munich April 26 16°C | NO | 0.991 | ok | micro seulement |
| 2074474 | Shanghai April 27 24°C | NO | 0.965 | ok | validation source+carnet |
| 2074308 | Seoul April 27 15°C | NO | 0.978 | ok | validation source+carnet |
| 2064828 | London April 26 20°C | NO | 0.975 | ok | validation source+carnet |
| 2074433 | Munich April 27 18°C | NO | 0.93 | ok | validation source+carnet |

## Décision standard
- **Source officielle absente/pending** → watch ou paper-only.
- **Quote manquante/profondeur faible** → aucun fill, attendre carnet exécutable.
- **Ask extrême mais signal fort** → micro paper strict-limit uniquement.
- **Source + carnet + edge net OK** → paper strict-limit; live seulement après validation répétée de la boucle.

## Formule mentale
`edge utilisable = signal comptes gagnants × anomalie de surface × source officielle × exécution stricte`
