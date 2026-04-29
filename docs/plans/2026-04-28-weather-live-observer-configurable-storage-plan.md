# Plan d’implémentation — Observer live météo configurable + stockage paramétrable

> **Pour Hermes :** utiliser `subagent-driven-development` pour implémenter ce plan tâche par tâche, en TDD strict. Ce plan complète `docs/plans/2026-04-28-polymarket-weather-shadow-profiles-references.md`.

**Date :** 2026-04-28
**Repo canonique :** `/home/jul/P-core`
**Branche vérifiée :** `main`
**Objectif :** ajouter un observer live météo Polymarket qui enregistre uniquement les données impossibles ou fragiles à reconstruire après coup, avec un réglage facile du scénario `minimal / realistic / aggressive` et du backend de stockage. L’observer valide/corrige les shadow profiles historiques ; il ne bloque pas leur création initiale.

**Architecture :**
- `weather_pm` garde la logique météo/Polymarket : marchés, surfaces de bins, forecast/source-at-time.
- `panoptique` garde l’observation, les snapshots, les profils fantômes et les artifacts auditables.
- `prediction_core.storage` garde la configuration de stockage générique : local filesystem, Postgres/Timescale, ClickHouse, S3/MinIO.

**Non-goals stricts :**
- pas d’ordre réel ;
- pas de wallet ;
- pas de signature ;
- pas de copy-trading ;
- pas de full orderbook continu sur tous les marchés ;
- pas de boucle LLM continue.

---

## 1. Contexte vérifié

### 1.1 Repo

Commande vérifiée :

```bash
cd /home/jul/P-core
date +%F
git status --short
git branch --show-current
```

Résultat observé :

```text
2026-04-28
?? docs/plans/2026-04-28-polymarket-weather-shadow-profiles-references.md
main
```

Le repo est sur `main`. Un plan précédent est non suivi par git.

### 1.2 Modules existants utiles

Modules météo existants :

```text
python/src/weather_pm/polymarket_live.py
python/src/weather_pm/polymarket_client.py
python/src/weather_pm/forecast_client.py
python/src/weather_pm/history_client.py
python/src/weather_pm/market_parser.py
python/src/weather_pm/event_surface.py
python/src/weather_pm/strategy_shortlist.py
python/src/weather_pm/paper_ledger.py
python/src/weather_pm/cli.py
```

Modules Panoptique existants :

```text
python/src/panoptique/snapshots.py
python/src/panoptique/artifacts.py
python/src/panoptique/storage_exports.py
python/src/panoptique/repositories.py
python/src/panoptique/contracts.py
python/src/panoptique/cli.py
```

Configuration stockage existante :

```text
python/src/prediction_core/storage/config.py
python/tests/test_storage_config.py
```

Faits importants :

- `prediction_core.storage.config` lit déjà Postgres, ClickHouse, Redis, NATS et S3 depuis l’environnement.
- `panoptique.artifacts.JsonlArtifactWriter` existe déjà pour écrire des artifacts JSONL locaux append-only.
- `panoptique.artifacts.S3ArtifactWriter` existe déjà pour écrire vers S3/MinIO si configuré.
- `panoptique.snapshots` sait déjà normaliser des snapshots Gamma et CLOB, mais le défaut actuel pointe encore vers `/home/jul/prediction_core/data/panoptique/snapshots`, à corriger vers P-core ou à rendre configurable.

---

## 2. Besoin fonctionnel

Décision produit actualisée : les premiers shadow profiles doivent être construits **backfill-first** depuis l’historique déjà disponible. L’observer live n’est pas là pour découvrir les top villes/marchés/timing, mais pour enregistrer les variables manquantes : orderbook exact, abstentions propres, forecast-at-time, surface complète et microstructure.

Julien veut pouvoir :

1. choisir facilement le scénario de collecte **quand l’enregistrement est actif** :
   - `minimal` ;
   - `realistic` ;
   - `aggressive` ;
2. pouvoir mettre l’enregistrement des futures données sur **OFF total**, indépendamment du scénario sélectionné ;
3. choisir facilement où les données sont stockées :
   - local filesystem ;
   - Postgres/Timescale ;
   - ClickHouse ;
   - S3/MinIO ;
   - combinaison de plusieurs backends ;
4. changer ces réglages sans modifier le code ;
5. avoir une interface opérateur simple, appelée ici **onglet de configuration** ;
6. garder une collecte bornée, paper-only et audit-friendly ;
7. pouvoir désactiver seulement certains streams (`orderbook`, `forecast`, `surfaces`, `trades`) ;
8. pouvoir désactiver certains profils/comptes suivis sans supprimer leur historique.

---

## 2.1 Contrôle opérateur obligatoire — stop global, streams et profils

La config doit séparer clairement deux notions :

- `active_scenario` = intensité qui sera utilisée **si** l’enregistrement est actif (`minimal`, `realistic`, `aggressive`) ;
- `collection.enabled` = interrupteur maître de l’enregistrement futur.

Règle produit obligatoire : **le scénario ne démarre jamais l’enregistrement à lui seul**. On peut garder `active_scenario: aggressive` en configuration tout en ayant `collection.enabled: false`. Dans ce cas le mode agressif est seulement le scénario préparé pour la prochaine réactivation, pas un mode actif.

La config doit permettre trois niveaux d’arrêt sans modifier le code :

1. **OFF total enregistrement futur / stop global collecte live** : aucune récupération réseau, aucune écriture de snapshot, quel que soit `active_scenario`.
2. **Stop par stream** : désactiver seulement `market_snapshots`, `bin_surfaces`, `forecasts`, `account_trades`, `full_books` ou `microstructure`.
3. **Stop par profil/compte** : désactiver un shadow profile ou un compte suivi tout en gardant ses données historiques et ses rapports.

Sémantique obligatoire :

```yaml
collection:
  enabled: false        # kill switch global : rien ne collecte
  dry_run: true         # calcule ce qui serait fait, n’écrit pas de snapshot live
  reason: operator_pause
```

Quand `collection.enabled=false` :

- `active_scenario` peut rester `aggressive`, `realistic` ou `minimal`, mais il est inactif ;
- `run-once --source live` doit sortir proprement avec `collection_disabled=true` ;
- le scheduler doit être no-op ;
- aucun appel Gamma/CLOB/weather live ne doit être fait ;
- aucune écriture data snapshot ne doit être faite ;
- aucune rotation/partition de nouveaux fichiers live ne doit être créée ;
- les commandes `show`, `estimate`, `validate` et les analyses historiques restent autorisées ;
- les backfills historiques restent possibles uniquement via commandes explicites de backfill, jamais via le scheduler live.

Quand un stream est désactivé, seul ce stream est no-op ; les autres peuvent continuer si `collection.enabled=true`.

Quand un profil est désactivé :

- il ne génère plus de décisions paper live ;
- il n’est plus utilisé comme trigger de capture riche ;
- son historique reste lisible et backtestable ;
- les rapports doivent afficher `enabled=false` et la raison.

---

## 3. Données live à enregistrer

### 3.1 Indispensable live

Seulement ces trois familles sont vraiment indispensables en direct :

```text
1. compact_market_snapshot
2. weather_bin_surface_snapshot
3. forecast_source_snapshot
```

### 3.2 Trigger léger recommandé

Ajouter un quatrième flux léger :

```text
4. followed_account_trade_trigger
```

Il n’est pas strictement impossible à récupérer après coup, mais il sert à déclencher des snapshots plus riches autour d’un événement.

### 3.3 Récupérable après coup

À récupérer en backfill au besoin :

```text
historical trades
wallet histories
market metadata
market resolutions
historical observed weather
partial historical orderbook via PMXT/Telonex when available
```

---

## 4. Scénarios de collecte

Créer trois profils configurables.

### 4.1 `minimal`

Objectif : coût disque minimal, démarrage prudent.

```yaml
scenario: minimal
market_limit: 100
surface_limit: 25
followed_account_limit: 10
compact_market_snapshot_interval_seconds: 300
bin_surface_snapshot_interval_seconds: 300
forecast_snapshot_interval_seconds: 1800
trade_trigger_poll_interval_seconds: 300
full_book_policy: event_only
retention:
  raw_days: 30
  compact_days: 180
  aggregate_days: 365
estimated_storage:
  per_day_mb: 36
  per_month_gb: 1.05
```

### 4.2 `realistic`

Objectif : scénario par défaut recommandé.

```yaml
scenario: realistic
market_limit: 300
surface_limit: 60
followed_account_limit: 25
compact_market_snapshot_interval_seconds: 180
bin_surface_snapshot_interval_seconds: 300
forecast_snapshot_interval_seconds: 1800
trade_trigger_poll_interval_seconds: 180
full_book_policy: event_only
retention:
  raw_days: 45
  compact_days: 180
  aggregate_days: 730
estimated_storage:
  per_day_mb: 129
  per_month_gb: 3.8
```

### 4.3 `aggressive`

Objectif : recherche plus dense, stockage encore raisonnable mais à surveiller.

```yaml
scenario: aggressive
market_limit: 1000
surface_limit: 150
followed_account_limit: 80
compact_market_snapshot_interval_seconds: 60
bin_surface_snapshot_interval_seconds: 120
forecast_snapshot_interval_seconds: 900
trade_trigger_poll_interval_seconds: 60
full_book_policy: event_plus_high_movement
retention:
  raw_days: 30
  compact_days: 120
  aggregate_days: 730
estimated_storage:
  per_day_mb: 1107
  per_month_gb: 32.4
```

---

## 5. Stockage configurable

### 5.1 Backends supportés v1

Supporter ces backends :

```text
local_jsonl
local_parquet
postgres_timescale
clickhouse
s3_archive
```

### 5.2 Backends recommandés par défaut

Sur cette machine, le défaut cible doit être **TrueNAS + scénario agressif ciblé météo**, car le stockage local système ne doit pas recevoir les snapshots lourds.

```yaml
active_scenario: aggressive
storage:
  primary: local_parquet
  analytics: clickhouse
  archive: local_parquet
  mirror: []
paths:
  base_dir: /mnt/truenas/p-core/polymarket/live_observer
safety:
  require_mountpoint: /mnt/truenas
  refuse_if_not_mounted: true
```

Pourquoi :

- `local_parquet` sur TrueNAS = compact et relisible pour backtests ;
- `clickhouse` = dashboard/analytics ;
- `local_jsonl` reste utile pour petits artifacts audit immédiat, mais pas comme seul stockage agressif ;
- `postgres_timescale` = source de vérité opérationnelle si on veut hypertables/retention ;
- `s3_archive`/MinIO = archivage long terme alternatif.

Fallback obligatoire : si `/mnt/truenas` n’est pas monté, l’observer doit refuser de démarrer ou repasser explicitement en `minimal` vers un chemin local temporaire validé. Il ne doit jamais écrire silencieusement dans `/mnt/truenas` non monté.

### 5.3 Emplacements configurables

Valeurs par défaut P-core :

```yaml
paths:
  base_dir: /home/jul/P-core/data/polymarket/live_observer
  jsonl_dir: /home/jul/P-core/data/polymarket/live_observer/jsonl
  parquet_dir: /home/jul/P-core/data/polymarket/live_observer/parquet
  reports_dir: /home/jul/P-core/data/polymarket/live_observer/reports
  manifests_dir: /home/jul/P-core/data/polymarket/live_observer/manifests
```

TrueNAS local mount par défaut prévu :

```yaml
paths:
  base_dir: /mnt/truenas/p-core/polymarket/live_observer
safety:
  require_mountpoint: /mnt/truenas
  refuse_if_not_mounted: true
```

Préflight opérationnel :

```bash
mountpoint /mnt/truenas
test -w /mnt/truenas
```

Si `mountpoint /mnt/truenas` échoue, ne pas créer de données sous ce chemin.

Exemple S3/MinIO :

```yaml
storage:
  archive: s3_archive
s3:
  bucket_env: PREDICTION_CORE_S3_BUCKET
  prefix: polymarket/live_observer
```

Ne jamais stocker de secret dans le YAML. Les secrets restent en variables d’environnement.

---

## 6. Onglet de configuration opérateur

Il y a deux niveaux.

### 6.1 V1 immédiate : CLI + fichier YAML

Créer un fichier :

```text
config/weather_live_observer.yaml
```

Créer une CLI :

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config show
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config set-scenario realistic
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config set-storage --primary local_jsonl --analytics clickhouse --archive local_parquet
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config set-path --base-dir /home/jul/P-core/data/polymarket/live_observer
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config estimate
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config validate
```

### 6.2 V2 cockpit : onglet Grafana / dashboard config

Ajouter un panneau dans Grafana, ou un dashboard dédié :

```text
infra/analytics/grafana/dashboards/weather-live-observer-config.json
```

Panels souhaités :

```text
current scenario
current storage backend
base path
market/surface/account limits
snapshot intervals
estimated MB/day
estimated GB/month
last run status
last snapshot age
errors by source
retention policy
```

Important : Grafana peut afficher l’état et les instructions, mais il ne doit pas forcément modifier la config lui-même en v1. La modification peut rester CLI/YAML pour éviter une surface d’écriture risquée.

### 6.3 V3 optionnelle : mini API admin guarded

Seulement si nécessaire plus tard :

```text
POST /api/weather-live-observer/config/scenario
POST /api/weather-live-observer/config/storage
```

Avec garde-fous :

- auth locale ;
- audit log ;
- dry-run avant apply ;
- pas de modification de secrets ;
- pas d’activation live trading.

---

## 7. Fichiers à créer/modifier

### 7.1 Configuration

Créer :

```text
config/weather_live_observer.yaml
python/src/weather_pm/live_observer_config.py
python/tests/test_weather_live_observer_config.py
```

### 7.2 Estimation stockage

Créer :

```text
python/src/weather_pm/live_observer_storage_estimator.py
python/tests/test_weather_live_observer_storage_estimator.py
```

### 7.3 Writer multi-backend

Créer :

```text
python/src/panoptique/live_observer_storage.py
python/tests/test_panoptique_live_observer_storage.py
```

Réutiliser :

```text
python/src/panoptique/artifacts.py
python/src/prediction_core/storage/config.py
```

### 7.4 Snapshot contracts

Créer ou compléter :

```text
python/src/weather_pm/live_observer_snapshots.py
python/tests/test_weather_live_observer_snapshots.py
```

Types :

```text
CompactMarketSnapshot
WeatherBinSurfaceSnapshot
ForecastSourceSnapshot
FollowedAccountTradeTrigger
LiveObserverRunSummary
```

### 7.5 Runner live observer

Créer :

```text
python/src/weather_pm/live_observer.py
python/tests/test_weather_live_observer.py
```

### 7.6 CLI

Modifier :

```text
python/src/weather_pm/cli.py
```

Tests :

```text
python/tests/test_weather_live_observer_cli.py
```

### 7.7 Docs

Créer :

```text
docs/weather-live-observer-config.md
```

Modifier si besoin :

```text
docs/prediction-core-clickhouse-grafana.md
```

### 7.8 Dashboard

Créer :

```text
infra/analytics/grafana/dashboards/weather-live-observer-config.json
```

Modifier tests :

```text
python/tests/test_grafana_provisioning.py
python/tests/test_prediction_core_analytics_docs.py
```

---

## 8. Modèle YAML cible

Créer `config/weather_live_observer.yaml` :

```yaml
version: 1
active_scenario: aggressive   # scénario préparé ; n’enregistre que si collection.enabled=true

collection:
  enabled: false              # OFF total : aucune future donnée live enregistrée
  dry_run: true               # même si quelqu’un lance run-once, pas d’écriture live
  reason: operator_off_default

streams:
  market_snapshots:
    enabled: true
  bin_surfaces:
    enabled: true
  forecasts:
    enabled: true
  account_trades:
    enabled: true
  full_books:
    enabled: true
  microstructure:
    enabled: true

profiles:
  shadow_coldmath_v0:
    enabled: true
    source_account: ColdMath
  shadow_poligarch_v0:
    enabled: true
    source_account: Poligarch
  shadow_railbird_v0:
    enabled: true
    source_account: Railbird

followed_accounts:
  ColdMath:
    enabled: true
  Poligarch:
    enabled: true
  Railbird:
    enabled: true

scenarios:
  minimal:
    market_limit: 100
    surface_limit: 25
    followed_account_limit: 10
    compact_market_snapshot_interval_seconds: 300
    bin_surface_snapshot_interval_seconds: 300
    forecast_snapshot_interval_seconds: 1800
    trade_trigger_poll_interval_seconds: 300
    full_book_policy: event_only
    retention:
      raw_days: 30
      compact_days: 180
      aggregate_days: 365

  realistic:
    market_limit: 300
    surface_limit: 60
    followed_account_limit: 25
    compact_market_snapshot_interval_seconds: 180
    bin_surface_snapshot_interval_seconds: 300
    forecast_snapshot_interval_seconds: 1800
    trade_trigger_poll_interval_seconds: 180
    full_book_policy: event_only
    retention:
      raw_days: 45
      compact_days: 180
      aggregate_days: 730

  aggressive:
    market_limit: 1000
    surface_limit: 150
    followed_account_limit: 80
    compact_market_snapshot_interval_seconds: 60
    bin_surface_snapshot_interval_seconds: 120
    forecast_snapshot_interval_seconds: 900
    trade_trigger_poll_interval_seconds: 60
    full_book_policy: event_plus_high_movement
    retention:
      raw_days: 30
      compact_days: 120
      aggregate_days: 730

storage:
  enabled: true
  primary: local_parquet
  analytics: clickhouse
  archive: local_parquet
  mirror: []

paths:
  base_dir: /mnt/truenas/p-core/polymarket/live_observer
  jsonl_dir: /mnt/truenas/p-core/polymarket/live_observer/jsonl
  parquet_dir: /mnt/truenas/p-core/polymarket/live_observer/parquet
  reports_dir: /mnt/truenas/p-core/polymarket/live_observer/reports
  manifests_dir: /mnt/truenas/p-core/polymarket/live_observer/manifests

s3:
  enabled: false
  bucket_env: PREDICTION_CORE_S3_BUCKET
  prefix: polymarket/live_observer

safety:
  paper_only: true
  live_order_allowed: false
  allow_wallet: false
  allow_signing: false
  require_mountpoint: /mnt/truenas
  refuse_if_not_mounted: true
  max_full_book_markets_per_run: 25
```

---

## 9. Tâches TDD détaillées

## Phase 0 — Préparer le plan et vérifier le périmètre

### Task 0.1 — Ajouter ce plan

**Objectif :** sauvegarder le plan dans le repo.

**Files :**
- Create: `docs/plans/2026-04-28-weather-live-observer-configurable-storage-plan.md`

**Validation :**

```bash
cd /home/jul/P-core
git diff --check -- docs/plans/2026-04-28-weather-live-observer-configurable-storage-plan.md
```

---

## Phase 1 — Configuration scénario/storage

**Note d’exécution Phase 1 (2026-04-28) :** implémenté en TDD strict sans commit. Ajout du YAML opérateur `config/weather_live_observer.yaml`, du loader dataclass `weather_pm.live_observer_config`, des validations scénario/storage/safety, des overrides d’environnement et de `live_collection_active` pour matérialiser que `active_scenario` reste seulement une intensité préparée tant que `collection.enabled=false` ou `dry_run=true`. Validation ciblée : `python/tests/test_weather_live_observer_config.py` passe.

### Task 1.1 — Créer le YAML par défaut

**Objectif :** ajouter une config lisible et modifiable par Julien.

**Files :**
- Create: `config/weather_live_observer.yaml`
- Test: `python/tests/test_weather_live_observer_config.py`

**Step 1 — Test RED :**

```python
from pathlib import Path
from weather_pm.live_observer_config import load_live_observer_config


def test_default_config_uses_realistic_scenario():
    config = load_live_observer_config(Path("config/weather_live_observer.yaml"))

    assert config.active_scenario == "realistic"
    assert config.active.market_limit == 300
    assert config.storage.primary == "local_jsonl"
    assert config.storage.analytics == "clickhouse"
    assert config.safety.paper_only is True
    assert config.safety.live_order_allowed is False
```

**Step 2 — Run RED :**

```bash
cd /home/jul/P-core
PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_live_observer_config.py::test_default_config_uses_realistic_scenario -q
```

Expected : FAIL — module missing.

**Step 3 — Implement GREEN :**

Créer `python/src/weather_pm/live_observer_config.py` avec dataclasses pures et loader YAML. Utiliser `yaml.safe_load` si PyYAML existe, sinon JSON-compatible fallback ou erreur claire.

**Step 4 — Run GREEN :**

```bash
PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_live_observer_config.py -q
```

### Task 1.2 — Valider les scénarios autorisés

**Objectif :** empêcher une config typo ou dangereuse.

**Test :**

```python
def test_unknown_active_scenario_is_rejected(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("version: 1\nactive_scenario: turbo\nscenarios: {}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown active_scenario"):
        load_live_observer_config(path)
```

Contraintes :

- scénarios autorisés : `minimal`, `realistic`, `aggressive` ;
- `paper_only` doit être `true` ;
- `live_order_allowed` doit être `false` ;
- `allow_wallet` doit être `false` ;
- `allow_signing` doit être `false`.

### Task 1.3 — Ajouter l’override par variable d’environnement

**Objectif :** changer de scénario facilement sans éditer le YAML.

Variables :

```text
WEATHER_LIVE_OBSERVER_ENABLED=0|1|false|true|off|on
WEATHER_LIVE_OBSERVER_SCENARIO=minimal|realistic|aggressive
WEATHER_LIVE_OBSERVER_BASE_DIR=/path/to/storage
WEATHER_LIVE_OBSERVER_PRIMARY_STORAGE=local_jsonl|local_parquet|postgres_timescale|clickhouse|s3_archive
```

`WEATHER_LIVE_OBSERVER_ENABLED=0` doit avoir priorité sur le scénario : même avec `WEATHER_LIVE_OBSERVER_SCENARIO=aggressive`, aucun enregistrement futur ne démarre si enabled vaut off/false/0.

**Test :**

```python
def test_env_override_can_switch_to_minimal(monkeypatch):
    monkeypatch.setenv("WEATHER_LIVE_OBSERVER_SCENARIO", "minimal")
    config = load_live_observer_config(Path("config/weather_live_observer.yaml"))

    assert config.active_scenario == "minimal"
    assert config.active.market_limit == 100
```

```python
def test_env_override_can_turn_collection_off_even_when_scenario_is_aggressive(monkeypatch):
    monkeypatch.setenv("WEATHER_LIVE_OBSERVER_SCENARIO", "aggressive")
    monkeypatch.setenv("WEATHER_LIVE_OBSERVER_ENABLED", "0")
    config = load_live_observer_config(Path("config/weather_live_observer.yaml"))

    assert config.active_scenario == "aggressive"
    assert config.collection.enabled is False
    assert config.live_collection_active is False
```

---

### Task 1.4 — Ajouter kill switch global et désactivation par stream/profil

**Objectif :** permettre à Julien d’arrêter toute collecte ou seulement une partie sans changer le code.

**Files:**
- Modify: `config/weather_live_observer.yaml`
- Modify: `python/src/weather_pm/live_observer_config.py`
- Test: `python/tests/test_weather_live_observer_config.py`

Tests à ajouter :

```python
def test_collection_disabled_makes_live_runner_noop(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("""
version: 1
active_scenario: aggressive
collection:
  enabled: false
  dry_run: false
  reason: operator_pause
scenarios:
  aggressive:
    market_limit: 1000
storage:
  enabled: true
safety:
  paper_only: true
  live_order_allowed: false
""", encoding="utf-8")

    config = load_live_observer_config(path)

    assert config.active_scenario == "aggressive"
    assert config.collection.enabled is False
    assert config.collection.reason == "operator_pause"
    assert config.live_collection_active is False
```

```python
def test_active_scenario_is_prepared_but_inactive_when_collection_is_off(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("""
version: 1
active_scenario: aggressive
collection:
  enabled: false
scenarios:
  aggressive:
    market_limit: 1000
storage:
  enabled: true
safety:
  paper_only: true
  live_order_allowed: false
""", encoding="utf-8")

    config = load_live_observer_config(path)

    assert config.active_scenario == "aggressive"
    assert config.active.market_limit == 1000
    assert config.live_collection_active is False
```

```python
def test_stream_and_profile_disable_flags_are_loaded(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("""
version: 1
active_scenario: aggressive
collection:
  enabled: true
streams:
  forecasts:
    enabled: false
profiles:
  shadow_coldmath_v0:
    enabled: false
    reason: noisy_profile
followed_accounts:
  ColdMath:
    enabled: false
    reason: pause_account
scenarios:
  aggressive:
    market_limit: 1000
storage:
  enabled: true
safety:
  paper_only: true
  live_order_allowed: false
""", encoding="utf-8")

    config = load_live_observer_config(path)

    assert config.streams["forecasts"].enabled is False
    assert config.profiles["shadow_coldmath_v0"].enabled is False
    assert config.followed_accounts["ColdMath"].enabled is False
```

CLI à prévoir :

```bash
weather-pm live-observer-config set-scenario aggressive
weather-pm live-observer-config disable-collection --reason operator_pause
weather-pm live-observer-config enable-collection
weather-pm live-observer-config status --json   # doit afficher scenario préparé + collection_active=false/true
weather-pm live-observer-config disable-stream forecasts --reason source_issue
weather-pm live-observer-config enable-stream forecasts
weather-pm live-observer-config disable-profile shadow_coldmath_v0 --reason noisy_profile
weather-pm live-observer-config enable-profile shadow_coldmath_v0
weather-pm live-observer-config disable-account ColdMath --reason pause_account
weather-pm live-observer-config enable-account ColdMath
```

Critères d’acceptation :

- `collection.enabled=false` coupe toute récupération live, même si `active_scenario=aggressive` ;
- `set-scenario aggressive` ne réactive jamais l’enregistrement si la collection est OFF ;
- `enable-collection` réactive l’enregistrement avec le scénario déjà préparé ;
- les analyses historiques/backfills restent utilisables ;
- un stream désactivé n’écrit rien et n’appelle pas son endpoint ;
- un profil désactivé ne produit plus de décision paper live ;
- les raisons de désactivation apparaissent dans `show --json` et les rapports.

## Phase 2 — Estimation stockage

### Task 2.1 — Ajouter estimateur déterministe

**Objectif :** afficher la taille estimée avant de lancer.

**Files :**
- Create: `python/src/weather_pm/live_observer_storage_estimator.py`
- Test: `python/tests/test_weather_live_observer_storage_estimator.py`

**Constantes v1 :**

```python
COMPACT_MARKET_SNAPSHOT_BYTES = 600
BIN_SURFACE_SNAPSHOT_BYTES = 2500
FORECAST_SOURCE_SNAPSHOT_BYTES = 1800
TRADE_TRIGGER_BYTES = 1000
```

**Test :**

```python
def test_realistic_storage_estimate_is_about_four_gb_per_month():
    config = load_live_observer_config(Path("config/weather_live_observer.yaml"))
    estimate = estimate_live_observer_storage(config.active)

    assert 120 <= estimate.mb_per_day <= 140
    assert 3.5 <= estimate.gb_per_month <= 4.1
```

### Task 2.2 — Inclure estimation dans config show

CLI souhaitée :

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config estimate
```

Sortie JSON :

```json
{
  "scenario": "realistic",
  "collection_enabled": false,
  "collection_active": false,
  "estimate_applies_if_enabled": true,
  "mb_per_day": 128.7,
  "gb_per_month": 3.8,
  "storage_primary": "local_jsonl",
  "base_dir": "/home/jul/P-core/data/polymarket/live_observer",
  "paper_only": true,
  "live_order_allowed": false
}
```

### Note d’exécution Phase 2 — 2026-04-28

Implémenté en TDD strict : tests estimateur/CLI ajoutés d’abord puis validés en RED sur module manquant. Ajout de `weather_pm.live_observer_storage_estimator` avec constantes déterministes v1, estimation par stream, prise en compte de `collection.enabled`, `collection_active`, `estimate_applies_if_enabled`, et streams désactivés à zéro dans l’estimation active. Ajout d’une surface CLI minimale `live-observer-config estimate` qui charge `config/weather_live_observer.yaml` et sort le JSON d’estimation opérateur. Validation ciblée passée :

```bash
PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_live_observer_config.py python/tests/test_weather_live_observer_storage_estimator.py -q
PYTHONPATH=python/src python3 -m py_compile python/src/weather_pm/live_observer_config.py python/src/weather_pm/live_observer_storage_estimator.py python/src/weather_pm/cli.py
git diff --check -- config/weather_live_observer.yaml python/src/weather_pm/live_observer_config.py python/src/weather_pm/live_observer_storage_estimator.py python/tests/test_weather_live_observer_config.py python/tests/test_weather_live_observer_storage_estimator.py python/src/weather_pm/cli.py docs/plans/2026-04-28-weather-live-observer-configurable-storage-plan.md
```

Résultat : `19 passed` et aucune erreur `diff --check`.

---

## Phase 3 — Écriture multi-backend

### Task 3.1 — Créer writer local JSONL configuré

**Objectif :** écrire les snapshots dans le chemin choisi par config.

**Files :**
- Create: `python/src/panoptique/live_observer_storage.py`
- Test: `python/tests/test_panoptique_live_observer_storage.py`

**Test :**

```python
def test_local_jsonl_writer_uses_configured_base_dir(tmp_path):
    writer = create_live_observer_writer(
        backend="local_jsonl",
        base_dir=tmp_path,
        stream="compact_market_snapshot",
    )
    result = writer.write_many([{"market_id": "m1", "observed_at": "2026-04-28T00:00:00Z"}])

    assert result.row_count == 1
    assert str(tmp_path) in result.path
    assert Path(result.path).exists()
```

Implementation : réutiliser `JsonlArtifactWriter`.

### Task 3.2 — Ajouter writer local parquet avec fallback JSONL

**Objectif :** préparer archives compactes sans imposer pyarrow.

Règle :

- si `pyarrow` existe : écrire parquet réel ;
- sinon : écrire `.jsonl` ou `.parquet.jsonl` explicitement, pas mentir.

### Task 3.3 — Ajouter dispatch ClickHouse/Postgres/S3 en mode safe

**Objectif :** supporter plusieurs destinations sans tout implémenter lourdement dès v1.

V1 acceptable :

- `local_jsonl` : réel ;
- `local_parquet` : réel/fallback ;
- `s3_archive` : réel via `S3ArtifactWriter` si env configuré ;
- `clickhouse` : writer analytique si tables existent, sinon dry-run manifest ;
- `postgres_timescale` : repository si configuré, sinon dry-run manifest.

Chaque backend doit retourner :

```json
{
  "backend": "local_jsonl",
  "status": "written|dry_run|skipped|error",
  "path_or_uri": "...",
  "row_count": 123,
  "paper_only": true
}
```

### Note d’exécution Phase 3 — 2026-04-28

Implémenté en TDD strict : tests storage ajoutés d’abord puis validés en RED sur module manquant. Ajout de `panoptique.live_observer_storage` avec manifest `LiveObserverStorageResult`, writer `local_jsonl`, writer `local_parquet` avec fallback JSONL explicite si `pyarrow` manque (`backend=local_jsonl`, `requested_backend=local_parquet`, `status=fallback_jsonl`), dispatch safe, et manifests `skipped_not_configured`/`dry_run=true` pour `clickhouse`, `postgres_timescale`/`postgres` et `s3_archive` sans credentials ni réseau. Les résultats restent `paper_only=true` et refusent une config live-order/non-paper.

---

## Phase 4 — Snapshot contracts indispensables

### Task 4.1 — Compact market snapshot

**Files :**
- Create: `python/src/weather_pm/live_observer_snapshots.py`
- Test: `python/tests/test_weather_live_observer_snapshots.py`

Fields :

```python
@dataclass(frozen=True)
class CompactMarketSnapshot:
    market_id: str
    token_id: str | None
    observed_at: datetime
    best_bid: float | None
    best_ask: float | None
    mid: float | None
    spread: float | None
    top_depth: float | None
    volume_recent: float | None
    price_change_5m: float | None
    price_change_15m: float | None
    price_change_1h: float | None
    time_to_resolution_seconds: int | None
    source: str
```

### Task 4.2 — Weather bin surface snapshot

Fields :

```python
@dataclass(frozen=True)
class WeatherBinSurfaceSnapshot:
    surface_id: str
    city: str
    market_date: str
    measurement_type: str
    observed_at: datetime
    bins: list[dict[str, object]]
    implied_probability_total: float | None
    source: str
```

### Task 4.3 — Forecast source snapshot

Fields :

```python
@dataclass(frozen=True)
class ForecastSourceSnapshot:
    city: str
    market_date: str
    measurement_type: str
    observed_at: datetime
    source_name: str
    source_published_at: datetime | None
    freshness_seconds: int | None
    forecast_value: float | None
    distance_to_threshold: float | None
    distance_to_bin_center: float | None
```

### Task 4.4 — Followed-account trade trigger

Fields :

```python
@dataclass(frozen=True)
class FollowedAccountTradeTrigger:
    wallet: str
    handle: str | None
    market_id: str
    token_id: str | None
    observed_at: datetime
    trade_timestamp: datetime | None
    side: str | None
    price: float | None
    size: float | None
    tx_hash: str | None
    trigger_full_book: bool
```

### Note d’exécution Phase 4 — 2026-04-28

Implémenté en TDD strict : tests snapshot ajoutés d’abord puis validés en RED sur module manquant. Ajout de `weather_pm.live_observer_snapshots` avec contrats `CompactMarketSnapshot`, `WeatherBinSurfaceSnapshot`, `ForecastSourceSnapshot`, `FollowedAccountTradeTrigger`, sérialisation `to_dict()` JSON-compatible, datetimes/dates en ISO, champs `snapshot_type`, `paper_only=true` et `live_order_allowed=false`. Ajout d’un helper `assert_paper_only_storage_result` pour vérifier que les manifests storage restent compatibles avec la sémantique paper-only/no live order.

Validation Phases 3-4 + Phases 1-2 :

```bash
PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_live_observer_config.py python/tests/test_weather_live_observer_storage_estimator.py python/tests/test_panoptique_live_observer_storage.py python/tests/test_weather_live_observer_snapshots.py -q
PYTHONPATH=python/src python3 -m py_compile python/src/weather_pm/live_observer_config.py python/src/weather_pm/live_observer_storage_estimator.py python/src/panoptique/live_observer_storage.py python/src/weather_pm/live_observer_snapshots.py python/src/weather_pm/cli.py
```

Résultat : `29 passed` pour pytest ciblé, py_compile OK.

---

## Phase 5 — Runner observer

### Task 5.1 — Runner fixture-only

**Objectif :** prouver le pipeline sans réseau.

**Files :**
- Create: `python/src/weather_pm/live_observer.py`
- Test: `python/tests/test_weather_live_observer.py`

API :

```python
def run_live_observer_once(
    config: LiveObserverConfig,
    *,
    source: str = "fixture",
    dry_run: bool = False,
) -> LiveObserverRunSummary:
    ...
```

Résumé :

```json
{
  "scenario": "realistic",
  "source": "fixture",
  "dry_run": false,
  "paper_only": true,
  "live_order_allowed": false,
  "snapshots": {
    "compact_market_snapshot": 3,
    "weather_bin_surface_snapshot": 1,
    "forecast_source_snapshot": 1,
    "followed_account_trade_trigger": 0
  },
  "storage_results": [...],
  "errors": []
}
```

### Task 5.2 — Runner live read-only

Source live :

- Gamma markets via `weather_pm.polymarket_live` / `polymarket_client` ;
- CLOB top book only where token_id exists ;
- forecast via existing weather clients where available.

Garde-fous :

- pas de wallet import ;
- pas de py-clob-client live extra obligatoire ;
- timeout borné ;
- limit appliqué depuis scénario ;
- erreurs par source capturées dans summary.

### Note d’exécution Phase 5 — 2026-04-29

Implémenté en TDD strict sans commit : tests runner ajoutés puis RED sur module manquant, création de `weather_pm.live_observer` avec `run_live_observer_once(config, source="fixture", dry_run=False)` et `LiveObserverRunSummary`. Le pipeline fixture est sans réseau, JSON-compatible, paper-only/no-live-order, respecte les toggles de streams et écrit via le dispatcher storage seulement quand `collection.enabled=true`, `collection.dry_run=false` et `dry_run=false`. Quand `collection.enabled=false`, seul `source="fixture" --dry-run` est autorisé à exercer le pipeline sans écriture ; les autres runs retournent un résumé `collection_disabled` sans créer de dossier. Le mode `source="live"` v1 est explicitement différé avec erreur `read_only_unavailable`, sans import wallet/py-clob, sans appel réseau et sans écriture.

---

## Phase 6 — CLI opérateur

### Task 6.1 — Ajouter `live-observer-config show`

Commande :

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config show --json
```

Sortie : config redacted + estimation.

### Task 6.2 — Ajouter `set-scenario`

Commande :

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config set-scenario minimal
```

Règle : modifier seulement `active_scenario` dans le YAML.

### Task 6.3 — Ajouter `set-storage`

Commande :

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config set-storage \
  --primary local_jsonl \
  --analytics clickhouse \
  --archive local_parquet
```

Backends autorisés :

```text
local_jsonl
local_parquet
postgres_timescale
clickhouse
s3_archive
none
```

### Task 6.4 — Ajouter `set-path`

Commande :

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config set-path \
  --base-dir /mnt/truenas/p-core/polymarket/live_observer
```

La commande doit recalculer :

```text
jsonl_dir
parquet_dir
reports_dir
manifests_dir
```

### Task 6.5 — Ajouter `live-observer run-once`

Commande :

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer run-once --source fixture --dry-run
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer run-once --source live
```

---

### Task 6.5 — Ajouter commandes enable/disable

**Objectif :** exposer les kill switches opérateur en CLI.

Commandes :

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config disable-collection --reason operator_pause
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config enable-collection
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config disable-stream forecasts --reason source_issue
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config enable-stream forecasts
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config disable-profile shadow_coldmath_v0 --reason noisy_profile
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config enable-profile shadow_coldmath_v0
```

Validation : `show --json` doit refléter les flags et raisons.

### Note d’exécution Phase 6 — 2026-04-29

Implémenté en TDD strict sans commit : ajout de `python/tests/test_weather_live_observer_cli.py` sur copies temporaires du YAML, puis extension de `weather_pm.cli`. `live-observer-config show --json` retourne config redacted + estimation ; `set-scenario` remplace seulement la ligne `active_scenario` en préservant le reste du YAML ; `set-storage` et `set-path` modifient les champs attendus ; `live-observer run-once --source fixture --dry-run` sort le summary JSON du runner. Les commandes génériques `live-observer-config enable|disable collection|stream <name>|profile <name> --reason ...` exposent les kill switches opérateur, et `show --json` reflète flags et raisons. Les tests n’altèrent pas `config/weather_live_observer.yaml`.

Validation Phases 1-6 :

```bash
PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_live_observer_config.py python/tests/test_weather_live_observer_storage_estimator.py python/tests/test_panoptique_live_observer_storage.py python/tests/test_weather_live_observer_snapshots.py python/tests/test_weather_live_observer.py python/tests/test_weather_live_observer_cli.py -q
PYTHONPATH=python/src python3 -m py_compile python/src/weather_pm/live_observer_config.py python/src/weather_pm/live_observer_storage_estimator.py python/src/panoptique/live_observer_storage.py python/src/weather_pm/live_observer_snapshots.py python/src/weather_pm/live_observer.py python/src/weather_pm/cli.py
```

Résultat : `38 passed`, py_compile OK.

## Phase 7 — Onglet dashboard config

### Task 7.1 — Ajouter dashboard Grafana config

**Files :**
- Create: `infra/analytics/grafana/dashboards/weather-live-observer-config.json`
- Modify: `python/tests/test_grafana_provisioning.py`

Dashboard :

```text
Title: Weather Live Observer Config
UID: prediction-core-weather-live-observer-config
```

Panels :

1. Active scenario
2. Estimated GB/month
3. Storage primary/backend
4. Base directory / archive target
5. Snapshot intervals
6. Market/surface/account limits
7. Last run status
8. Snapshot freshness
9. Error count by source
10. Paper-only guardrails

### Task 7.2 — Ajouter doc opérateur

Créer :

```text
docs/weather-live-observer-config.md
```

Doit expliquer :

- comment passer `minimal → realistic → aggressive` ;
- comment changer chemin local ;
- comment activer NAS/MinIO ;
- comment vérifier taille estimée ;
- comment lancer un dry-run ;
- comment revenir au local.

### Note d’exécution Phase 7 — 2026-04-29

Implémenté en TDD strict sans commit : extension de `python/tests/test_grafana_provisioning.py` en RED sur dashboard manquant, puis création de `infra/analytics/grafana/dashboards/weather-live-observer-config.json` avec titre `Weather Live Observer Config`, UID `prediction-core-weather-live-observer-config`, timezone Paris, datasource ClickHouse et panneaux requis : scénario actif, estimation GB/mois, storage primary/backend, base/archive target, intervalles, limites, dernier statut, fraîcheur, erreurs par source, garde-fous paper-only. Ajout de `docs/weather-live-observer-config.md`, runbook opérateur pratique couvrant changements de scénario, chemins local/NAS, NAS/MinIO, estimation, dry-run, rollback local, kill switches et sécurité paper-only.

---

## Phase 8 — Scheduler

### Task 8.1 — Script wrapper idempotent

Créer :

```text
scripts/weather_live_observer_run_once.py
```

Rôle :

- charger config ;
- lancer `run_live_observer_once(source="live")` ;
- écrire summary JSON/MD ;
- exit code 0 si snapshot partiel mais utilisable ;
- exit code non-zero si config invalide ou aucune écriture possible.

### Task 8.2 — Cron Hermes ou systemd user

Option recommandée : Hermes cronjob ou systemd user timer.

Fréquence : dépend du scénario actif.

Prudence : pour les intervalles différents entre market/surface/forecast, le script peut être appelé toutes les 60 secondes et décider quoi faire selon `last_run` par stream, ou plus simple v1 : un run toutes les 3 minutes en `realistic` qui collecte ce qui est dû.

### Note d’exécution Phase 8 — 2026-04-29

Implémenté en TDD strict sans commit : ajout de `python/tests/test_weather_live_observer_run_once_script.py` en RED sur script/doc manquants, puis création de `scripts/weather_live_observer_run_once.py`. Le wrapper charge la config, lance `run_live_observer_once` (`--source live` par défaut, `--source fixture` pour smoke), écrit des rapports summary JSON/MD optionnels, crée les parents de rapports par défaut, et échoue clairement sur config invalide ou chemin de rapport non écrivable. Les exits restent `0` pour résumé utilisable, y compris `collection_disabled` et `read_only_unavailable` v1 sans réseau. La doc recommande une commande cron/systemd externe, mais aucun cron, timer ou unit systemd n’a été installé.

---

## 10. Validation globale

Commandes ciblées :

```bash
cd /home/jul/P-core
PYTHONPATH=python/src python3 -m pytest \
  python/tests/test_weather_live_observer_config.py \
  python/tests/test_weather_live_observer_storage_estimator.py \
  python/tests/test_panoptique_live_observer_storage.py \
  python/tests/test_weather_live_observer_snapshots.py \
  python/tests/test_weather_live_observer.py \
  python/tests/test_weather_live_observer_cli.py \
  -q
```

Non-régression stockage/dashboard :

```bash
PYTHONPATH=python/src python3 -m pytest \
  python/tests/test_storage_config.py \
  python/tests/test_grafana_provisioning.py \
  python/tests/test_prediction_core_analytics_docs.py \
  -q
```

Syntaxe :

```bash
python3 -m py_compile \
  python/src/weather_pm/live_observer_config.py \
  python/src/weather_pm/live_observer_storage_estimator.py \
  python/src/weather_pm/live_observer_snapshots.py \
  python/src/weather_pm/live_observer.py \
  python/src/panoptique/live_observer_storage.py \
  python/src/weather_pm/cli.py \
  scripts/weather_live_observer_run_once.py
```

Diff :

```bash
git diff --check
```

Safety scan :

```bash
grep -RInE "private_key|wallet_secret|signing|place_order|cancel_order|live_order_allowed.*true|allow_wallet.*true|allow_signing.*true" \
  python/src/weather_pm/live_observer* \
  python/src/panoptique/live_observer_storage.py \
  config/weather_live_observer.yaml \
  scripts/weather_live_observer_run_once.py || true
```

Expected : aucun signal dangereux, sauf mentions de garde-fous explicitement à `false`.

---

## 11. Commandes opérateur finales attendues

Changer de scénario :

```bash
cd /home/jul/P-core
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config set-scenario minimal
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config set-scenario realistic
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config set-scenario aggressive
```

Changer stockage local :

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config set-path \
  --base-dir /home/jul/P-core/data/polymarket/live_observer
```

Changer stockage NAS :

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config set-path \
  --base-dir /mnt/truenas/p-core/polymarket/live_observer
```

Changer backends :

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config set-storage \
  --primary local_jsonl \
  --analytics clickhouse \
  --archive local_parquet
```

Voir la config :

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config show --json
```

Voir l’estimation :

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer-config estimate
```

Dry-run :

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer run-once --source fixture --dry-run
```

Live read-only :

```bash
PYTHONPATH=python/src python3 -m weather_pm.cli live-observer run-once --source live
```

---

## 12. Critères d’acceptation produit

La feature est prête quand :

- Julien peut passer de `minimal` à `realistic` ou `aggressive` avec une seule commande ;
- Julien peut changer le dossier de stockage avec une seule commande ;
- `show --json` affiche scénario, chemins, backends et estimation de taille ;
- `run-once --source fixture --dry-run` passe sans réseau ;
- `run-once --source live` collecte seulement des données read-only ;
- `collection.enabled=false` désactive complètement la récupération live et les écritures snapshots ;
- chaque stream/profil/compte peut être désactivé individuellement ;
- les snapshots indispensables sont écrits dans le backend configuré quand la collecte est activée ;
- la sortie résume les lignes écrites par stream ;
- tous les artifacts indiquent `paper_only: true` et `live_order_allowed: false` ;
- aucun secret n’est écrit dans les artifacts ;
- dashboard/config tab montre le scénario actif, le stockage et la taille estimée.

---

## 13. Décision recommandée

Démarrer en **aggressive ciblé météo sur TrueNAS**, pas en local système :

```yaml
active_scenario: aggressive
storage:
  primary: local_parquet
  analytics: clickhouse
  archive: local_parquet
paths:
  base_dir: /mnt/truenas/p-core/polymarket/live_observer
safety:
  require_mountpoint: /mnt/truenas
  refuse_if_not_mounted: true
```

Raison : les shadow profiles initiaux viennent du backfill historique déjà disponible ; l’observer live doit donc être plus dense dès le départ pour capturer les angles morts que l’historique ne donne pas.

Ne pas attendre 7 jours pour passer en agressif si TrueNAS est monté et writable. Le checkpoint 7 jours sert seulement à mesurer la taille réelle et ajuster les limites.

Si TrueNAS est absent :

```bash
weather-pm live-observer-config validate
# attendu: refus clair, pas d’écriture sous /mnt/truenas non monté
```

Si la charge est trop forte :

```bash
weather-pm live-observer-config set-scenario realistic
```

Le principe final reste :

```text
profils historiques immédiats, observer live pour angles morts,
TrueNAS par défaut pour agressif, mount guard obligatoire,
kill switch global + désactivation stream/profil/compte,
paper-only partout.
```
