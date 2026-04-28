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
cd /home/jul/P-core/python
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
./scripts/prediction-core polymarket-stack
./scripts/prediction-core polymarket-stack --table
./scripts/prediction-core marketdata-plan
./scripts/prediction-core marketdata-replay --events-jsonl /tmp/clob-events.jsonl
./scripts/prediction-core marketdata-stream --token-id <clob-token-id> --dry-run-events-jsonl /tmp/clob-events.jsonl --max-events 10
./scripts/prediction-core marketdata-stream --token-id <clob-token-id> --live --max-events 10
./scripts/prediction-core polymarket-runtime-plan
./scripts/prediction-core polymarket-runtime-cycle --markets-json /tmp/markets.json --probabilities-json /tmp/probabilities.json --dry-run-events-jsonl /tmp/clob-events.jsonl --max-events 10
```

Après installation editable éventuelle :

```bash
cd /home/jul/P-core/python
prediction-core serve --host 127.0.0.1 --port 8080
prediction-core consume-markets --base-url http://127.0.0.1:8080 --source live --limit 3 --min-status watchlist
prediction-core polymarket-stack
prediction-core polymarket-stack --table
prediction-core marketdata-plan
prediction-core marketdata-replay --events-jsonl /tmp/clob-events.jsonl
prediction-core marketdata-stream --token-id <clob-token-id> --dry-run-events-jsonl /tmp/clob-events.jsonl --max-events 10
prediction-core marketdata-stream --token-id <clob-token-id> --live --max-events 10
prediction-core polymarket-runtime-plan
prediction-core polymarket-runtime-cycle --markets-json /tmp/markets.json --probabilities-json /tmp/probabilities.json --dry-run-events-jsonl /tmp/clob-events.jsonl --max-events 10
```

## Polymarket low-latency stack

Le choix canonique ajouté pour `prediction_core` est une architecture cible, pas une surface d'exécution réelle opérable aujourd'hui :

```text
Gamma REST      -> découverte marché + règles + clobTokenIds, en cache hors hot path
CLOB WebSocket  -> flux live orderbook/prix, hot path
CLOB REST       -> passage/annulation d'ordres, hot path auth futur ; submit/cancel réels non câblés aujourd'hui
Data API        -> analytics wallets/trades/positions, hors hot path
```

Le repo officiel `Polymarket/polymarket-cli` est conservé comme surface opérateur/script JSON rapide, mais pas comme boucle trading serrée : chaque commande relance un process. Pour le moteur live, la cible rapide est un daemon Rust long-running basé sur `Polymarket/rs-clob-client` avec feature WebSocket. Le passage et l'annulation d'ordres réels restent explicitement indisponibles dans ce scaffold.

Commandes de référence :

```bash
./scripts/prediction-core polymarket-stack
./scripts/prediction-core polymarket-stack --table
./scripts/prediction-core marketdata-plan
./scripts/prediction-core marketdata-plan --discovery-interval-seconds 45 --max-hot-markets 12
./scripts/prediction-core marketdata-replay --events-jsonl /tmp/clob-events.jsonl
./scripts/prediction-core marketdata-stream --token-id <clob-token-id> --dry-run-events-jsonl /tmp/clob-events.jsonl --max-events 10
./scripts/prediction-core marketdata-stream --token-id <clob-token-id> --live --max-events 10
./scripts/prediction-core polymarket-runtime-plan
./scripts/prediction-core polymarket-runtime-cycle --markets-json /tmp/markets.json --probabilities-json /tmp/probabilities.json --dry-run-events-jsonl /tmp/clob-events.jsonl --max-events 10
```

`marketdata-replay` lit un JSONL d’événements WebSocket CLOB simulés/capturés (`book`, `price_change`) et rejoue le flux dans le cache local read-only. C’est volontairement sans réseau ni ordre réel : on valide le contrat hot-path avant de brancher un worker WebSocket long-running.

`marketdata-stream` ajoute le worker async injectable qui consomme le même contrat dans un cache local. Par défaut il reste déterministe avec `--dry-run-events-jsonl`. Le mode réseau réel existe seulement derrière `--live` et impose `--max-events` pour éviter un run opérateur infini ; il reste read-only et ne place aucun ordre.

`polymarket-runtime-plan` et `polymarket-runtime-cycle` mettent en place le pipeline complet demandé, même si l’exécution réelle n’est pas utilisée : découverte Gamma-like locale, sélection des `clobTokenIds`, marketdata CLOB WebSocket/replay, décision sur cache local, puis exécution selon le mode choisi. En `paper`, le runtime planifie uniquement des intentions papier (`paper_intents`), avec `execution_enabled=false` et `orders_submitted=[]`. En `dry_run`, il emprunte le chemin d’exécution canonique avec risques/idempotence/audit, peut remplir `orders_submitted` avec des ids `dry-run:<idempotency_key>`, mais ne fait aucun appel réseau de placement d’ordre réel. `live` n’est pas un choix exposé par `polymarket-runtime-cycle` ; utiliser `polymarket-live-preflight` pour les vérifications opérateur read-only.

Le scaffold `marketdata-plan` formalise le prochain découpage rapide sans encore placer d'ordre réel :

- `discovery_worker` : Gamma API, refresh metadata hors hot path ;
- `marketdata_worker` : CLOB WebSocket, maintient bid/ask/spread/depth en mémoire ;
- `decision_worker` : lit uniquement le cache local dans la boucle rapide ;
- `execution_worker` : futur CLOB REST authentifié, désactivé dans ce scaffold ;
- `analytics_worker` : Data API batch/post-trade, hors hot path.

Le module `prediction_core.polymarket_marketdata` contient aussi un cache in-memory testable (`MarketDataCache`) qui calcule défensivement `best_bid=max(bids)` et `best_ask=min(asks)` au lieu de faire confiance à l'ordre des niveaux CLOB.

## Optional Rust orderbook path

`prediction_core.execution.book.estimate_fill_from_book` garde son API Python publique et utilise le chemin Python par défaut. Le chemin Rust orderbook est opt-in avec :

```bash
PREDICTION_CORE_RUST_ORDERBOOK=1
```

Si le module natif `prediction_core._rust_orderbook` est absent, si le flag n'est pas exactement `1`, si le carnet contient des niveaux non sûrs, ou si l'appel Rust échoue, le wrapper revient automatiquement au fallback Python. Le module natif source vit côté Rust dans `crates/py_orderbook`; il reste volontairement opt-in parce que le pont PyO3 unitaire mesuré est plus lent que le fallback Python, même si le noyau Rust pur est plus rapide. Pour désactiver Rust en cas de régression, supprimer la variable ou la mettre à `0`.

Vérifications ciblées :

```bash
cd /home/jul/P-core/python
uv run pytest tests/test_execution_book.py tests/test_execution_rust_orderbook_wrapper.py tests/contracts/test_orderbook_fill_parity_fixture_contract.py

cd /home/jul/P-core/rust
cargo test -p pm_book --lib
cargo test -p py_orderbook --lib
cargo run -p xtask -- orderbook-parity ../python/tests/fixtures/orderbook_fill_parity.json
```

Smoke test local avec le module natif importé par Python :

```bash
cd /home/jul/P-core
cargo build --manifest-path rust/Cargo.toml -p py_orderbook --release
cp rust/target/release/lib_rust_orderbook.so python/src/prediction_core/_rust_orderbook.so
cd python
PREDICTION_CORE_RUST_ORDERBOOK=1 uv run pytest tests/test_execution_book.py tests/test_execution_rust_orderbook_wrapper.py
rm -f src/prediction_core/_rust_orderbook.so
```

Les benchmarks orderbook restent manuels et non bloquants :

```bash
cd /home/jul/P-core/rust && cargo bench -p pm_book --bench orderbook_levels
cd /home/jul/P-core/python && uv run python benchmarks/orderbook_levels.py
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
- `POST /weather/station-source-plan` (construit le plan opérationnel `market_id -> station_binding -> source_selection` : meilleure source latest directe/fraîche, source finale officielle, action opérateur et fallbacks)
- `POST /weather/source-coverage` (retourne l’inventaire des providers météo intégrés par catégorie/support direct/fallback/manual-review avec caveat explicite : couverture large mais pas littéralement exhaustive)
- `POST /weather/resolution-status` (compare latest direct provisoire vs daily extract officiel final, expose `provisional_outcome`, `confirmed_outcome`, action opérateur et diagnostics de latence/polling)
- `POST /weather/monitor-paper-resolution` (écrit les artefacts paper-only JSON + markdown opérateur depuis `market_id`, `date`, `paper_side`, optionnellement notional/shares/output_dir ; retourne `should_repoll` et une proposition de cron bornée si le final officiel est encore pending)
- `POST /weather/paper-cycle` (construit une simulation paper + postmortem ; si `question` + `yes_price` sont fournis, il score le marché puis peut auto-dériver `requested_quantity` depuis `bankroll_usd`, puis `filled_quantity` et `fill_price` depuis la décision ; si `market_id` est absent/vide, lance un cycle live multi-marchés borné)

CLI screener compact :
- `python3 -m weather_pm.cli paper-cycle --run-id ... --source fixture|live --limit N`
- `python3 -m weather_pm.cli paper-cycle-report --run-id ... --source fixture|live --limit N`
- `python3 -m weather_pm.cli event-surface --markets-json markets.json` groupe les marchés météo par événement ville/date/kind/unité et signale les anomalies de seuil/bin ; ajouter `--output-json event-surface.json` pour écrire le rapport complet et ne printer qu’un résumé compact
- `python3 -m weather_pm.cli strategy-shortlist --strategy-report-json strategies.json --opportunity-report-json opportunities.json --event-surface-json event-surface.json` conserve les champs `source_*` pour que le shortlist garde la station/URL à poller en low-latency
- `python3 -m weather_pm.cli strategy-shortlist-report --reverse-engineering-json reverse.json --run-id ... --source fixture|live --operator-limit 10 --output-json shortlist.json` construit en une passe stratégie + opportunités + event surface + shortlist ; avec `--output-json`, stdout reste compact et le fichier contient les payloads complets ; `--operator-limit` embarque une watchlist opérateur avec station directe, URL latest, priorité de latence et diagnostic d’exécution
- `python3 -m weather_pm.cli operator-shortlist --shortlist-json shortlist.json --limit 10` compacte un shortlist sauvegardé en rapport d’action opérateur sans relancer le scan
- `python3 -m weather_pm.cli station-source-plan --market-id ... --source live --start-date YYYY-MM-DD --end-date YYYY-MM-DD` retourne le binding exact station/source, la meilleure source latest à poller, la source finale officielle et l’action opérateur associée
- `python3 -m weather_pm.cli source-coverage` retourne l’inventaire compact des sources météo intégrées, groupées par catégorie/support, sans prétendre à une exhaustivité mondiale impossible
- `python3 -m weather_pm.cli monitor-paper-resolution --market-id ... --source live --date YYYY-MM-DD --paper-side yes --paper-notional-usd 5 --paper-shares 17.24` sauvegarde un snapshot paper-only de résolution : JSON brut + markdown opérateur sous `/home/jul/P-core/data/polymarket`, en séparant latest direct provisoire et daily extract officiel final
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

## Panoptique Phase 1 optional dependencies

The Panoptique Phase 1 storage foundation keeps runtime imports lightweight for local tests. PostgreSQL/TimescaleDB production access expects optional packages when running against the real database:

- `SQLAlchemy>=2`
- `asyncpg`
- `alembic`

The repository contracts and JSONL audit archive are importable without those packages; SQLite-backed tests cover the write-path contract shape when TimescaleDB is unavailable.
