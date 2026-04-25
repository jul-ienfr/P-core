# prediction_core/python

Zone Python canonique pour les briques de recherche et d'évaluation autour de `prediction_core`.

## Rôle actuel

Cette zone héberge maintenant deux familles de packages sous le même parent Python :

- `prediction_core.*` : noyaux canoniques `replay`, `paper`, `calibration`, `analytics`, `evaluation`
- `weather_pm.*` : MVP météo Polymarket absorbé depuis `subprojects/prediction/python`

Le parent commun reste `prediction_core/` :
- `prediction_core/python` = research / replay / paper / calibration / analytics / évaluation
- `prediction_core/rust` = moteur live canonique
- `subprojects/prediction` = cockpit / API / UI / intégration

## Phase 2 scope for this extraction

Cette extraction prépare la Phase 2 avec deux premières extractions canoniques minimales pour `replay` et `paper`, tout en gardant le focus principal sur les domaines restants.

- `replay` (signature canonique minimale)
- `paper` (simulation canonique minimale)
- `calibration`
- `analytics`
- `evaluation`
- `weather_pm` (MVP météo importé tel quel pour convergence Python + Rust sous `prediction_core/`)

Les implémentations legacy de `replay` et `paper` ne sont pas migrées en bloc : seules des briques minimales et stables sont extraites ici pour ancrer le layout Python canonique.

## Principes de cadrage

- on documente les frontières minimales des domaines restants avant tout port de code ;
- on évite d'introduire une API publique prématurée ;
- on garde les chemins de modules stables pour faciliter l'extraction incrémentale future ;
- on garde provisoirement le package `weather_pm` sans renommage pour éviter une casse immédiate des imports et des tests.

## Layout actuel

- `src/prediction_core/replay/` (première extraction canonique : signatures replay)
- `src/prediction_core/paper/` (première extraction canonique : simulation paper)
- `src/prediction_core/calibration/`
- `src/prediction_core/analytics/`
- `src/prediction_core/evaluation/`
- `src/weather_pm/` (MVP météo Polymarket)
- `docs/reuse-map.md`

Cette zone réutilisera progressivement le Python utile déjà présent dans l’écosystème existant, domaine par domaine, avec TDD ciblé.

## Commandes

```bash
cd /home/jul/prediction_core/python
PYTHONPATH=src pytest -q
python3 -m weather_pm.cli --help
PYTHONPATH=src python3 -m weather_pm.cli paper-cycle-report \
  --run-id live-scan \
  --source live \
  --limit 25 \
  --min-edge 0.01 \
  --max-cost-bps 1000 \
  --min-depth-usd 0
./scripts/prediction-core serve --host 127.0.0.1 --port 8080
./scripts/prediction-core consume-markets --base-url http://127.0.0.1:8080 --source live --limit 3 --min-status watchlist
```

Après installation editable éventuelle :

```bash
cd /home/jul/prediction_core/python
prediction-core serve --host 127.0.0.1 --port 8080
prediction-core consume-markets --base-url http://127.0.0.1:8080 --source live --limit 3 --min-status watchlist
```

## Execution cost model

Le domaine canonique `prediction_core.execution` estime maintenant un coût d'exécution détaillé : sweep du carnet multi-niveaux, prix moyen de fill, spread/slippage, frais maker/taker, frais optionnels de dépôt/retrait, puis `edge_net_execution` et `edge_net_all_in`.

Les frais de trading et les frais de transfert sont volontairement séparés : le score microstructure utilise l'edge net d'exécution, tandis que les coûts dépôt/retrait servent à vérifier si le trade reste rentable en all-in. Voir `../docs/execution-cost-model.md` pour le détail et un exemple chiffré.

## Service HTTP local minimal

Le bootstrap Python expose une petite surface HTTP locale pour rendre `prediction_core` démarrable sans introduire de framework web supplémentaire.

Endpoints actuels :
- `GET /health`
- `POST /weather/parse-market`
- `POST /weather/score-market` (retourne aussi `source_route`, le chemin direct de résolution quand les règles exposent une station NOAA/Wunderground/HKO : URL latest/history, station, focus de polling, `latency_priority` et besoin éventuel de review manuelle ; accepte `source=fixture|live` et `infer_default_resolution=true` pour les flows paper/fixture)
- `POST /weather/station-history` (suit `market_id -> resolution_source -> station` et récupère l’historique direct quand supporté, avec diagnostics de latence et latest point)
- `POST /weather/station-latest` (suit la même station de résolution et retourne le dernier point direct pour le polling low-latency)
- `POST /weather/paper-cycle` (construit une simulation paper + postmortem ; si `question` + `yes_price` sont fournis, il score le marché puis peut auto-dériver `requested_quantity` depuis `bankroll_usd`, puis `filled_quantity` et `fill_price` depuis la décision ; si `market_id` est absent/vide, lance un cycle live multi-marchés borné)

CLI screener compact :
- `python3 -m weather_pm.cli paper-cycle --run-id ... --source fixture|live --limit N`
- `python3 -m weather_pm.cli paper-cycle-report --run-id ... --source fixture|live --limit N`
- `python3 -m weather_pm.cli event-surface --markets-json markets.json` groupe les marchés météo par événement ville/date/kind/unité et signale les anomalies de seuil/bin ; ajouter `--output-json event-surface.json` pour écrire le rapport complet et ne printer qu’un résumé compact
- `python3 -m weather_pm.cli strategy-shortlist --strategy-report-json strategies.json --opportunity-report-json opportunities.json --event-surface-json event-surface.json` conserve les champs `source_*` pour que le shortlist garde la station/URL à poller en low-latency
- `python3 -m weather_pm.cli strategy-shortlist-report --reverse-engineering-json reverse.json --run-id ... --source fixture|live --operator-limit 10 --output-json shortlist.json` construit en une passe stratégie + opportunités + event surface + shortlist ; avec `--output-json`, stdout reste compact et le fichier contient les payloads complets ; `--operator-limit` embarque une watchlist opérateur avec station directe, URL latest, priorité de latence et diagnostic d’exécution
- `python3 -m weather_pm.cli operator-shortlist --shortlist-json shortlist.json --limit 10` compacte un shortlist sauvegardé en rapport d’action opérateur sans relancer le scan
- par défaut, le report n’affiche que les candidats exécutables (`trade` / `trade_small`) pour éviter le bruit ; ajouter `--include-skipped` pour diagnostiquer les marchés ignorés
- filtres report : `--tradeable-only`, `--include-skipped`, `--min-edge`, `--max-cost-bps`, `--min-depth-usd`

Exemples de smoke test manuels :

```bash
curl http://127.0.0.1:8080/health
curl -X POST http://127.0.0.1:8080/weather/parse-market \
  -H 'Content-Type: application/json' \
  -d '{"question":"Will the highest temperature in Denver be 64F or higher?"}'
curl -X POST http://127.0.0.1:8080/weather/paper-cycle \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"run-http-1","market_id":"market-denver-64f","requested_quantity":4,"filled_quantity":3,"fill_price":0.53,"reference_price":0.5,"fee_paid":0.01}'
curl -X POST http://127.0.0.1:8080/weather/paper-cycle \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"run-http-2","market_id":"market-denver-64f","question":"Will the highest temperature in Denver be 64F or higher?","yes_price":0.53,"requested_quantity":4}'
curl -X POST http://127.0.0.1:8080/weather/paper-cycle \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"run-http-3","market_id":"market-denver-64f","question":"Will the highest temperature in Denver be 64F or higher?","yes_price":0.53,"bankroll_usd":1000}'
```

Portée explicite :
- `prediction_core/python` héberge maintenant les packages Python canoniques **et** un petit service local de bootstrap
- `prediction_core/rust` reste le moteur live canonique séparé, inchangé
- ce service n'est pas encore un orchestrateur complet multi-runtime ; c'est le plus petit chemin vers un vrai `prediction_core start`

## Suite prévue

- stabiliser la coexistence `prediction_core.*` + `weather_pm.*`
- converger ensuite vers un namespace Python plus unifié si utile
- ne pas déplacer `prediction_core/rust` pendant cette phase
