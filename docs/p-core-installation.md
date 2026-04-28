# P-core installation reproductible

Ce repo contient un script d'installation idempotent pour préparer une machine P-core avec le socle data nécessaire à l'ambition long terme : agents multiples, historique long, audit, dashboards, replay/backtest et future phase live gardée.

## Script principal

```bash
scripts/install_data_stack.sh
```

Le script est conçu pour être relancé sans casser l'existant :

- il crée `.venv` seulement s'il n'existe pas ;
- il vérifie les modules Python attendus avant de lancer `pip install` ;
- il démarre les services Docker existants avec `--no-recreate` quand il n'y a pas de mise à jour demandée ;
- il n'installe pas les paquets système par défaut ;
- il n'installe pas le client live Polymarket par défaut.

## Installation standard sur une machine déjà équipée Docker/Python

```bash
cd /home/jul/P-core
scripts/install_data_stack.sh
```

Cela installe ou complète :

- l'environnement Python local `.venv` ;
- les extras Python `.[storage]` : ClickHouse, Postgres, Redis, NATS, S3 ;
- les services Docker déclarés dans `infra/analytics/docker-compose.yml` ;
- les smoke checks ClickHouse/Grafana et imports Python.

## Nouvelle machine Ubuntu/Debian

Pour installer aussi les prérequis système manquants :

```bash
cd /home/jul/P-core
WITH_SYSTEM_PACKAGES=1 scripts/install_data_stack.sh
```

Le script installe uniquement les paquets apt manquants, sauf si `UPGRADE=1` est demandé.

## Mise à jour explicite

Pour mettre à jour les dépendances Python, les paquets système demandés et les images Docker :

```bash
cd /home/jul/P-core
WITH_SYSTEM_PACKAGES=1 UPGRADE=1 scripts/install_data_stack.sh
```

Sans `UPGRADE=1`, le script privilégie le mode idempotent : il saute ce qui est déjà présent.

## Phase live Polymarket / CLOB

Le client live n'est pas installé par défaut. Pour l'ajouter explicitement :

```bash
cd /home/jul/P-core
WITH_LIVE=1 scripts/install_data_stack.sh
```

Cela installe l'extra Python `.[polymarket-live]`, notamment `py-clob-client`. Cette étape ne donne pas à elle seule l'autorisation de placer des ordres live ; les garde-fous applicatifs restent séparés.

## Dry-run

Pour voir ce que le script ferait sans rien modifier :

```bash
cd /home/jul/P-core
DRY_RUN=1 WITH_SYSTEM_PACKAGES=1 WITH_LIVE=1 scripts/install_data_stack.sh
```

## Options

| Variable | Défaut | Effet |
|---|---:|---|
| `WITH_SYSTEM_PACKAGES` | `0` | installe les prérequis apt manquants |
| `UPGRADE` | `0` | met à jour paquets Python/images Docker/paquets apt |
| `WITH_LIVE` | `0` | installe l'extra live Polymarket/CLOB |
| `START_SERVICES` | `1` | démarre les services Docker data |
| `SMOKE` | `1` | vérifie imports Python + ClickHouse/Grafana |
| `DRY_RUN` | `0` | affiche les commandes sans les exécuter |
| `FORCE_RECREATE_VENV` | `0` | supprime puis recrée `.venv` |
| `VENV_DIR` | `.venv` | emplacement de l'environnement Python |
| `PYTHON_BIN` | `python3` | binaire Python utilisé pour créer `.venv` |

## Rôle des composants

- **Postgres/Timescale** : source de vérité opérationnelle, audit, état agents/jobs, ledgers.
- **ClickHouse** : historique analytique massif, dashboards, replay/backtest.
- **Grafana** : cockpit opérateur.
- **Redis/NATS** : coordination/cache/event bus pour agents multiples.
- **MinIO/S3 local** : artefacts volumineux, snapshots, exports.
- **JSON/CSV/MD** : rapports humains et snapshots lisibles.

## Après installation

```bash
source .venv/bin/activate
PYTHONPATH=python/src python3 scripts/weather_cron_monitor_refresh.py
```
