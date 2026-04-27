# Polymarket météo — Strategy Profiles Playbook

Ce playbook transforme l’analyse des comptes météo gagnants en profils opérables. Il ne copie pas les wallets : les profils servent de radar et de structure de décision. Une entrée papier reste bloquée tant que la source météo, le carnet, le coût d’exécution et l’edge ne confirment pas indépendamment.

## Règles globales

- Mode par défaut : paper only, limite stricte, jamais market buy aveugle.
- Un compte profitable ne suffit jamais : il ajoute un signal de contexte, pas une autorisation d’entrée.
- `source_direct` doit être privilégié ; sans source directe, traiter comme fallback/watchlist sauf cas manuel.
- Toujours respecter `profile_risk_caps` exposé dans la shortlist/operator watchlist.
- Les blockers d’exécution existants gagnent sur le profil : prix extrême, spread large, profondeur absente, résolution en cours.

## Profils canoniques

| Profil | Pattern observé | Utilisation | Mode | Risque |
| --- | --- | --- | --- | --- |
| `surface_grid_trader` | Grilles ville/date, thresholds voisins, anomalies de surface | Inspecter monotonicité / inversion / incohérences entre marchés voisins | `paper_strict_limit` | Petites tailles par ordre, cap par event |
| `exact_bin_anomaly_hunter` | Bins exacts, masse de probabilité excessive, tickets opportunistes | Chercher exact bins mal pricés uniquement avec carnet exécutable | `paper_micro_strict_limit` | Micro taille, éviter bins illiquides |
| `threshold_resolution_harvester` | Seuil proche de résolution avec source directe | Poll source directe, entrer micro si source confirme et prix pas déjà intégré | `paper_micro_strict_limit` | Très petit ordre, fenêtre courte |
| `profitable_consensus_radar` | Plusieurs traders profitables convergent sur une ville/surface | Radar de priorité ; exige confirmation edge/source/carnet | `watchlist_only` | Pas d’entrée autonome |
| `conviction_signal_follower` | Gros tickets ou traders sparse très profitables | À traiter comme signal faible d’attention, jamais copie | `operator_review` | Revue manuelle requise |
| `macro_weather_event_trader` | Hurricane, climate, global temp surfaces | Suivi événementiel macro, horizons plus longs, sources spécifiques | `operator_review` | Risque narratif / résolution complexe |

## Gates d’entrée

### Surface/grid
1. `surface_inconsistency_count > 0` ou inconsistency type exploitable.
2. Source directe ou source fallback fiable.
3. Carnet exécutable avec spread/profondeur acceptable.
4. Limit strict sous l’edge net.
5. Cap event respecté.

### Exact bin
1. Exact bin détecté (`exactly`, bin mass, ou type exact-bin).
2. Overround/mass ou inversion chiffrée.
3. Micro ordre seulement.
4. Ne pas entrer si le meilleur ask détruit l’edge.

### Threshold resolution
1. Marché proche de résolution.
2. Source directe pollable (`latest`/station/source officielle).
3. Le direct confirme le sens, ou le profil reste en watchlist.
4. Prix non extrême ; sinon `pending_limit`/skip.

### Consensus/profitable accounts
1. Minimum plusieurs comptes/profils alignés ou matched traders significatifs.
2. Utilisation = priorisation de recherche.
3. L’entrée doit venir d’un profil d’exécution séparé : grid, exact bin ou threshold.

### Conviction/macro
1. Toujours operator review.
2. Vérifier résolution, marché lié, liquidité et source primaire.
3. Ne pas transformer la taille historique du trader en sizing bot.

## Champs exposés par la shortlist/operator

Chaque row shortlist peut maintenant inclure :

- `strategy_profile_id`
- `strategy_profile`
- `profile_risk_caps`
- `profile_execution_mode`
- `next_actions` enrichi avec `enforce_profile_risk_caps` et le mode du profil

Le rapport opérateur expose aussi `summary.strategy_profile_counts` et reprend le profil dans chaque watch row.

## Pont paper-ledger des profils

La commande `strategy-profile-paper-orders` transforme seulement les rows déjà qualifiées en ordres papier strict-limit. Elle reste volontairement conservatrice :

- modes autorisés uniquement : `paper_strict_limit` et `paper_micro_strict_limit` ;
- `watchlist_only` / `operator_review` sont ignorés et comptés dans `skipped_counts` ;
- `source_direct=false`, absence de token, absence de limite ou absence d'orderbook bloquent l'ordre ;
- `profile_risk_caps.max_order_usdc` clamp le sizing avant simulation ;
- chaque ordre écrit `paper_only=true` et `live_order_allowed=false`, avec les métadonnées `strategy_profile_id`, `strategy_profile`, `profile_execution_mode`, `profile_risk_caps`.

Usage :

```bash
cd /home/jul/P-core/python
PYTHONPATH=src python3 -m weather_pm.cli strategy-profile-paper-orders \
  --shortlist-json ../data/polymarket/weather_strategy_shortlist_live.json \
  --ledger-json ../data/polymarket/weather_strategy_profile_paper_ledger.json \
  --output-dir ../data/polymarket
```

## Mapping comptes top météo → profils utiles

- `ColdMath`, `Hans323`, `BeefSlayer` : surtout `surface_grid_trader` / grilles ville-date.
- `BigMike11` : `exact_bin_anomaly_hunter` sur bins de température exacts.
- `automatedAItradingbot` : `profitable_consensus_radar`, utile pour repérer des surfaces actives.
- `Handsanitizer23` : `conviction_signal_follower`, à ne pas copier sans validation indépendante.
- `gopfan2`, `gopfan`, `bama124` : tendance `macro_weather_event_trader` / surfaces globales-climat-hurricane selon marchés actifs.

## Commandes utiles

```bash
cd /home/jul/P-core/python
PYTHONPATH=src python3 -m weather_pm.cli strategy-profiles --output-md ../docs/generated-weather-strategy-profile-matrix.md
PYTHONPATH=src python3 -m weather_pm.cli strategy-profile-paper-orders --shortlist-json <shortlist.json> --ledger-json <profile_ledger.json> --output-dir ../data/polymarket
PYTHONPATH=src python3 -m pytest tests/test_weather_strategy_profiles.py tests/test_weather_strategy_shortlist.py tests/test_weather_winning_patterns.py tests/test_weather_paper_ledger.py -q
PYTHONPATH=src python3 -m py_compile src/weather_pm/strategy_profiles.py src/weather_pm/strategy_shortlist.py src/weather_pm/winning_patterns.py src/weather_pm/paper_ledger.py src/weather_pm/cli.py
```
