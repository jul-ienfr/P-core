# Polymarket météo — next steps opérateur

## Ce qu’on sait déjà
- Les comptes gagnants convergent surtout sur des **surfaces ville/date complètes**.
- Le pattern dominant est **event_surface_grid_specialist**.
- Les bons comptes donnent une **priorisation**, pas un feu vert d’exécution.
- Les marchés live utiles sont surtout bloqués par `extreme_price` ou `missing_tradeable_quote`.

## Priorité immédiate
| rang | marché | surface | ask | tradability | décision |
|---|---|---|---:|---|---|
| 1 | 2065210 | Moscow April 26 12°C | 0.987 | ok | strict-limit paper seulement |
| 2 | 2065032 | Shanghai April 26 21°C | 0.954 | ok | validation source+carnet |
| 3 | 2065108 | Beijing April 26 22°C | 0.995 | extreme_or_missing | micro-only / pas de taille normale |
| 4 | 2064990 | Munich April 26 16°C | 0.991 | ok | micro-only / pas de taille normale |
| 5 | 2074474 | Shanghai April 27 24°C | 0.965 | ok | validation source+carnet |

## Lecture opérateur
1. **Moscow / Shanghai / Munich** sont les meilleures surfaces de départ, mais encore proxy-aligned.
2. **Beijing 22°C** est trop extrême pour une exécution normale: à traiter en micro/paper uniquement.
3. **Dallas et Hong Kong live** ne sont pas des signaux de taille; ils sont surtout des surfaces à surveiller pour la liquidité et la résolution officielle.

## Règle de décision
- Si source officielle pendante: **watch/paper only**.
- Si quote manquante: **attendre profondeur exécutable**.
- Si ask extrême mais signal fort: **micro paper strict-limit**.
- Ne jamais transformer un match de comptes rentables en ordre normal sans carnet + source confirmés.

## Bref à réutiliser
Météo patterns gagnants: 85 comptes weather-heavy/mixed sur 10050 positifs. Pattern dominant: surface ville/date complète + source officielle + strict-limit. Top surface: Moscow April 26 NO 12°C.

## Surfaces consensus les plus fortes
| surface | side | comptes | signaux | statut |
|---|---:|---:|---:|---|
| Moscow April 26 12°C | NO | 9 | 32 | source_proxy_aligned_needs_official_check |
| Shanghai April 26 21°C | NO | 10 | 30 | source_proxy_aligned_needs_official_check |
| Beijing April 26 22°C | NO | 8 | 23 | source_proxy_aligned_needs_official_check |
| Seoul April 26 17°C | NO | 10 | 28 | source_proxy_aligned_needs_official_check |
| Munich April 26 16°C | NO | 11 | 38 | source_proxy_aligned_needs_official_check |

## Conclusion
Le vrai pattern gagnant n’est pas “prédire mieux”. C’est **repérer la bonne surface, attendre la bonne source, puis exécuter strictement**.