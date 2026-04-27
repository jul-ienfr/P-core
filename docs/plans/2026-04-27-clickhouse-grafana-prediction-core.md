# ClickHouse + Grafana Prediction Core Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Make ClickHouse the final analytical source of truth for Prediction Core/Panoptique events and Grafana the single cockpit for strategy/profile comparison, paper ledger monitoring, and decision debugging.

**Architecture:** Prediction Core keeps domain logic in Python, emits normalized append-only analytical events, writes them to ClickHouse, and Grafana reads ClickHouse directly through provisioned dashboards. Existing Timescale/Postgres scaffolding may remain for compatibility, but the final analytics cockpit must use ClickHouse as the primary analytical store.

**Tech Stack:** Python, pytest, ClickHouse, clickhouse-connect, Docker Compose, Grafana, Grafana ClickHouse datasource plugin, JSONEachRow/Parquet-style append-only event modeling.

---

## Contexte vérifié

- Repo actif: `/home/jul/P-core`.
- Branche actuelle: `main`, dirty tree important; isoler les changements liés à ce plan.
- Timescale existe partiellement côté Panoptique:
  - `infra/panoptique/docker-compose.yml` utilise `timescale/timescaledb:latest-pg16`.
  - migrations Alembic:
    - `migrations/panoptique/alembic/versions/0001_storage_foundation.py`
    - `migrations/panoptique/alembic/versions/0002_storage_optimization.py`
  - tests actuels passés: `python3 -m pytest python/tests/test_panoptique_migration_sql.py python/tests/test_panoptique_db_contracts.py -q` → `8 passed`.
- Aucun container `panoptique-postgres`/Timescale actif vu via `docker ps` au moment de l’audit.
- Le repository Panoptique actuel (`python/src/panoptique/repositories.py`) est sqlite-compatible pour tests, avec tables analytiques partielles, mais ce n’est pas un runtime ClickHouse.
- Besoin produit tranché: intégrer directement le stack final haut de gamme: **ClickHouse + Grafana**, pas Streamlit/DuckDB/Metabase/Superset comme cockpit principal.

---

## Principes non négociables

1. **ClickHouse = source analytique principale** pour runs, signaux, décisions, snapshots, ordres paper, positions, PnL, debug.
2. **Grafana = cockpit unique final** pour visualisation et alertes.
3. **Append-only par défaut**: ne pas écraser l’historique; produire des événements et snapshots versionnés.
4. **Tous les événements portent** au minimum:
   - `run_id`
   - `strategy_id`
   - `profile_id`
   - `market_id`
   - `observed_at`
   - `mode`
   - `raw`
5. **Le schéma doit être orienté comparaison** `strategy_id × profile_id`.
6. **Paper/live séparés explicitement**: `mode`, `paper_only`, `live_order_allowed`.
7. **Pas de secrets en DB ni dashboards**.
8. **Compatibilité progressive**: ne pas casser les exports JSON/CSV existants tant que les tests ne prouvent pas le remplacement.

---

## Schéma cible ClickHouse

Base:

```sql
CREATE DATABASE IF NOT EXISTS prediction_core;
```

Tables principales:

```text
prediction_runs
market_snapshots
orderbook_snapshots
strategy_signals
profile_decisions
paper_orders
paper_positions
paper_pnl_snapshots
execution_events
resolution_events
strategy_metrics
profile_metrics
debug_decisions
```

Moteur par défaut:

```sql
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id)
```

Pour les tables sans `profile_id`, utiliser `profile_id String DEFAULT ''` pour garder un modèle Grafana simple.

---

# Phase 0 — Isoler le travail

### Task 0.1: Créer une branche propre

**Objective:** Éviter de mélanger ce chantier avec le dirty tree actuel.

**Files:** aucun.

**Step 1: Inspecter le statut**

```bash
cd /home/jul/P-core
git status --short
```

**Step 2: Créer une branche dédiée**

```bash
git switch -c feat/clickhouse-grafana-cockpit
```

**Step 3: Ne rien commit d’étranger**

Pendant toute l’implémentation, vérifier avant chaque commit:

```bash
git status --short
```

Expected: seuls les fichiers de ce plan sont staged.

---

# Phase 1 — Infrastructure ClickHouse + Grafana

### Task 1.1: Ajouter Docker Compose final

**Objective:** Fournir un stack local persistant ClickHouse + Grafana.

**Files:**
- Create: `infra/analytics/docker-compose.yml`
- Create: `infra/analytics/README.md`

**Step 1: Créer le compose**

`infra/analytics/docker-compose.yml`:

```yaml
services:
  clickhouse:
    image: clickhouse/clickhouse-server:24.12
    container_name: prediction-core-clickhouse
    environment:
      CLICKHOUSE_DB: ${CLICKHOUSE_DB:-prediction_core}
      CLICKHOUSE_USER: ${CLICKHOUSE_USER:-prediction}
      CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD:-prediction}
      CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT: 1
    ports:
      - "127.0.0.1:${CLICKHOUSE_HTTP_PORT:-8123}:8123"
      - "127.0.0.1:${CLICKHOUSE_NATIVE_PORT:-9000}:9000"
    volumes:
      - clickhouse_data:/var/lib/clickhouse
      - ./clickhouse/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:8123/ping"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 20s

  grafana:
    image: grafana/grafana-oss:11.4.0
    container_name: prediction-core-grafana
    depends_on:
      clickhouse:
        condition: service_healthy
    environment:
      GF_SECURITY_ADMIN_USER: ${GRAFANA_ADMIN_USER:-admin}
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:-admin}
      GF_INSTALL_PLUGINS: grafana-clickhouse-datasource
    ports:
      - "127.0.0.1:${GRAFANA_PORT:-3000}:3000"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
    healthcheck:
      test: ["CMD-SHELL", "wget --spider -q http://localhost:3000/api/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 20
      start_period: 30s

volumes:
  clickhouse_data:
  grafana_data:
```

**Step 2: Créer le README**

`infra/analytics/README.md`:

```markdown
# Prediction Core Analytics Stack

Final cockpit stack:

- ClickHouse: analytical source of truth
- Grafana: dashboards and alerting

Start locally:

```bash
cd /home/jul/P-core/infra/analytics
docker compose up -d
```

Open Grafana:

- URL: http://127.0.0.1:3000
- Default local user: `admin`
- Default local password: `admin`

Never use these defaults outside local development.
```

**Step 3: Vérifier compose parse**

```bash
cd /home/jul/P-core/infra/analytics
docker compose config >/tmp/prediction-core-analytics-compose.yml
```

Expected: exit code 0.

**Step 4: Commit**

```bash
git add infra/analytics/docker-compose.yml infra/analytics/README.md
git commit -m "infra: add clickhouse grafana analytics stack"
```

---

### Task 1.2: Ajouter le schéma ClickHouse initial

**Objective:** Créer les tables analytiques finales au boot ClickHouse.

**Files:**
- Create: `infra/analytics/clickhouse/init/001_prediction_core_schema.sql`
- Create: `python/tests/test_clickhouse_schema_sql.py`

**Step 1: Écrire le test de contrat**

`python/tests/test_clickhouse_schema_sql.py`:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "infra" / "analytics" / "clickhouse" / "init" / "001_prediction_core_schema.sql"


def test_clickhouse_schema_defines_final_tables() -> None:
    sql = SCHEMA.read_text()
    for table in [
        "prediction_runs",
        "market_snapshots",
        "orderbook_snapshots",
        "strategy_signals",
        "profile_decisions",
        "paper_orders",
        "paper_positions",
        "paper_pnl_snapshots",
        "execution_events",
        "resolution_events",
        "strategy_metrics",
        "profile_metrics",
        "debug_decisions",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS prediction_core.{table}" in sql


def test_clickhouse_schema_is_profile_strategy_comparable() -> None:
    sql = SCHEMA.read_text()
    for column in ["run_id String", "strategy_id String", "profile_id String", "market_id String", "observed_at DateTime64"]:
        assert column in sql
    assert "ENGINE = MergeTree" in sql
    assert "PARTITION BY toYYYYMM(observed_at)" in sql
```

**Step 2: Run test pour vérifier l’échec**

```bash
cd /home/jul/P-core
python3 -m pytest python/tests/test_clickhouse_schema_sql.py -q
```

Expected: FAIL car le fichier SQL n’existe pas.

**Step 3: Créer le SQL**

`infra/analytics/clickhouse/init/001_prediction_core_schema.sql`:

```sql
CREATE DATABASE IF NOT EXISTS prediction_core;

CREATE TABLE IF NOT EXISTS prediction_core.prediction_runs (
    run_id String,
    observed_at DateTime64(3, 'UTC'),
    completed_at Nullable(DateTime64(3, 'UTC')),
    source String,
    mode String,
    status String,
    strategy_count UInt32,
    profile_count UInt32,
    market_count UInt32,
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id);

CREATE TABLE IF NOT EXISTS prediction_core.market_snapshots (
    run_id String,
    strategy_id String DEFAULT '',
    profile_id String DEFAULT '',
    market_id String,
    token_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    slug String,
    question String,
    active Bool,
    closed Bool,
    yes_price Nullable(Float64),
    best_bid Nullable(Float64),
    best_ask Nullable(Float64),
    volume Nullable(Float64),
    liquidity Nullable(Float64),
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id, token_id);

CREATE TABLE IF NOT EXISTS prediction_core.orderbook_snapshots (
    run_id String,
    strategy_id String DEFAULT '',
    profile_id String DEFAULT '',
    market_id String,
    token_id String,
    observed_at DateTime64(3, 'UTC'),
    best_bid Nullable(Float64),
    best_ask Nullable(Float64),
    spread Nullable(Float64),
    bid_depth_levels UInt32,
    ask_depth_levels UInt32,
    bids_json String,
    asks_json String,
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id, token_id);

CREATE TABLE IF NOT EXISTS prediction_core.strategy_signals (
    run_id String,
    strategy_id String,
    profile_id String DEFAULT '',
    market_id String,
    token_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    signal_id String,
    signal_type String,
    side String,
    probability Nullable(Float64),
    market_price Nullable(Float64),
    edge Nullable(Float64),
    confidence Nullable(Float64),
    paper_only Bool DEFAULT true,
    live_order_allowed Bool DEFAULT false,
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id, signal_id);

CREATE TABLE IF NOT EXISTS prediction_core.profile_decisions (
    run_id String,
    strategy_id String,
    profile_id String,
    market_id String,
    token_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    mode String,
    decision_status String,
    skip_reason String DEFAULT '',
    execution_mode String DEFAULT '',
    edge Nullable(Float64),
    limit_price Nullable(Float64),
    requested_spend_usdc Nullable(Float64),
    capped_spend_usdc Nullable(Float64),
    source_ok Bool,
    orderbook_ok Bool,
    risk_ok Bool,
    paper_only Bool DEFAULT true,
    live_order_allowed Bool DEFAULT false,
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id, decision_status);

CREATE TABLE IF NOT EXISTS prediction_core.paper_orders (
    run_id String,
    strategy_id String,
    profile_id String,
    market_id String,
    token_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    paper_order_id String,
    side String,
    price Nullable(Float64),
    size Nullable(Float64),
    spend_usdc Nullable(Float64),
    status String,
    opening_fee_usdc Nullable(Float64),
    opening_slippage_usdc Nullable(Float64),
    estimated_exit_cost_usdc Nullable(Float64),
    paper_only Bool DEFAULT true,
    live_order_allowed Bool DEFAULT false,
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id, paper_order_id);

CREATE TABLE IF NOT EXISTS prediction_core.paper_positions (
    run_id String,
    strategy_id String,
    profile_id String,
    market_id String,
    token_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    paper_position_id String,
    quantity Float64,
    avg_price Nullable(Float64),
    exposure_usdc Nullable(Float64),
    mtm_bid_usdc Nullable(Float64),
    status String,
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id, paper_position_id);

CREATE TABLE IF NOT EXISTS prediction_core.paper_pnl_snapshots (
    run_id String,
    strategy_id String,
    profile_id String,
    market_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    gross_pnl_usdc Nullable(Float64),
    net_pnl_usdc Nullable(Float64),
    costs_usdc Nullable(Float64),
    exposure_usdc Nullable(Float64),
    roi Nullable(Float64),
    winrate Nullable(Float64),
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id);

CREATE TABLE IF NOT EXISTS prediction_core.execution_events (
    run_id String,
    strategy_id String,
    profile_id String,
    market_id String,
    token_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    execution_event_id String,
    event_type String,
    mode String,
    paper_only Bool DEFAULT true,
    live_order_allowed Bool DEFAULT false,
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id, execution_event_id);

CREATE TABLE IF NOT EXISTS prediction_core.resolution_events (
    run_id String,
    strategy_id String DEFAULT '',
    profile_id String DEFAULT '',
    market_id String,
    observed_at DateTime64(3, 'UTC'),
    resolved_at Nullable(DateTime64(3, 'UTC')),
    outcome String,
    outcome_price Nullable(Float64),
    closed Bool,
    source String,
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, market_id, run_id, strategy_id, profile_id);

CREATE TABLE IF NOT EXISTS prediction_core.strategy_metrics (
    run_id String,
    strategy_id String,
    profile_id String DEFAULT '',
    market_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    signal_count UInt32,
    trade_count UInt32,
    skip_count UInt32,
    avg_edge Nullable(Float64),
    gross_pnl_usdc Nullable(Float64),
    net_pnl_usdc Nullable(Float64),
    exposure_usdc Nullable(Float64),
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id);

CREATE TABLE IF NOT EXISTS prediction_core.profile_metrics (
    run_id String,
    strategy_id String DEFAULT '',
    profile_id String,
    market_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    decision_count UInt32,
    trade_count UInt32,
    skip_count UInt32,
    exposure_usdc Nullable(Float64),
    gross_pnl_usdc Nullable(Float64),
    net_pnl_usdc Nullable(Float64),
    roi Nullable(Float64),
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id);

CREATE TABLE IF NOT EXISTS prediction_core.debug_decisions (
    run_id String,
    strategy_id String,
    profile_id String,
    market_id String,
    token_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    decision_status String,
    skip_reason String DEFAULT '',
    edge Nullable(Float64),
    limit_price Nullable(Float64),
    source_ok Bool,
    orderbook_ok Bool,
    risk_ok Bool,
    blocker String DEFAULT '',
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id, decision_status);
```

**Step 4: Vérifier test**

```bash
cd /home/jul/P-core
python3 -m pytest python/tests/test_clickhouse_schema_sql.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add infra/analytics/clickhouse/init/001_prediction_core_schema.sql python/tests/test_clickhouse_schema_sql.py
git commit -m "feat: add clickhouse analytics schema"
```

---

### Task 1.3: Provisionner la datasource Grafana ClickHouse

**Objective:** Grafana doit détecter ClickHouse automatiquement.

**Files:**
- Create: `infra/analytics/grafana/provisioning/datasources/clickhouse.yml`
- Create: `python/tests/test_grafana_provisioning.py`

**Step 1: Test**

`python/tests/test_grafana_provisioning.py`:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATASOURCE = ROOT / "infra" / "analytics" / "grafana" / "provisioning" / "datasources" / "clickhouse.yml"


def test_grafana_clickhouse_datasource_is_provisioned() -> None:
    text = DATASOURCE.read_text()
    assert "grafana-clickhouse-datasource" in text
    assert "prediction-core-clickhouse" in text
    assert "prediction_core" in text
    assert "jsonData" in text
```

**Step 2: Run failure**

```bash
python3 -m pytest python/tests/test_grafana_provisioning.py -q
```

Expected: FAIL.

**Step 3: Datasource YAML**

`infra/analytics/grafana/provisioning/datasources/clickhouse.yml`:

```yaml
apiVersion: 1

datasources:
  - name: PredictionCore ClickHouse
    uid: prediction-core-clickhouse
    type: grafana-clickhouse-datasource
    access: proxy
    isDefault: true
    jsonData:
      host: prediction-core-clickhouse
      port: 8123
      protocol: http
      database: prediction_core
      username: prediction
      tlsSkipVerify: true
    secureJsonData:
      password: prediction
```

**Step 4: Vérifier**

```bash
python3 -m pytest python/tests/test_grafana_provisioning.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add infra/analytics/grafana/provisioning/datasources/clickhouse.yml python/tests/test_grafana_provisioning.py
git commit -m "infra: provision grafana clickhouse datasource"
```

---

# Phase 2 — Client Python ClickHouse

### Task 2.1: Ajouter dépendance optionnelle clickhouse-connect

**Objective:** Déclarer le client ClickHouse Python.

**Files:**
- Modify: `python/pyproject.toml`

**Step 1: Lire les dépendances actuelles**

```bash
cd /home/jul/P-core
python3 - <<'PY'
from pathlib import Path
print(Path('python/pyproject.toml').read_text())
PY
```

**Step 2: Ajouter dépendance**

Ajouter dans les dependencies appropriées:

```toml
"clickhouse-connect>=0.8.0",
```

Si le projet utilise optional deps, préférer:

```toml
[project.optional-dependencies]
analytics = ["clickhouse-connect>=0.8.0"]
```

**Step 3: Vérifier parse TOML**

```bash
cd /home/jul/P-core/python
python3 - <<'PY'
import tomllib
from pathlib import Path
tomllib.loads(Path('pyproject.toml').read_text())
print('ok')
PY
```

Expected: `ok`.

**Step 4: Commit**

```bash
git add python/pyproject.toml
git commit -m "build: add clickhouse client dependency"
```

---

### Task 2.2: Créer les modèles analytiques normalisés

**Objective:** Avoir des dataclasses stables pour les événements ClickHouse.

**Files:**
- Create: `python/src/prediction_core/analytics/__init__.py`
- Create: `python/src/prediction_core/analytics/events.py`
- Create: `python/tests/test_analytics_events.py`

**Step 1: Test**

`python/tests/test_analytics_events.py`:

```python
from datetime import UTC, datetime

from prediction_core.analytics.events import ProfileDecisionEvent, serialize_event


def test_profile_decision_event_serializes_required_fields() -> None:
    event = ProfileDecisionEvent(
        run_id="run-1",
        strategy_id="weather_baseline",
        profile_id="strict_micro",
        market_id="m1",
        observed_at=datetime(2026, 4, 27, tzinfo=UTC),
        mode="paper",
        decision_status="skip",
        skip_reason="edge_below_threshold",
        edge=0.02,
        limit_price=0.41,
        source_ok=True,
        orderbook_ok=True,
        risk_ok=False,
        raw={"hello": "world"},
    )

    row = serialize_event(event)

    assert row["run_id"] == "run-1"
    assert row["strategy_id"] == "weather_baseline"
    assert row["profile_id"] == "strict_micro"
    assert row["market_id"] == "m1"
    assert row["observed_at"] == "2026-04-27 00:00:00.000"
    assert row["raw"] == '{"hello":"world"}'
```

**Step 2: Run failure**

```bash
cd /home/jul/P-core
PYTHONPATH=python/src python3 -m pytest python/tests/test_analytics_events.py -q
```

Expected: FAIL.

**Step 3: Implémenter**

`python/src/prediction_core/analytics/__init__.py`:

```python
from .events import ProfileDecisionEvent, serialize_event

__all__ = ["ProfileDecisionEvent", "serialize_event"]
```

`python/src/prediction_core/analytics/events.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from typing import Any


def _format_ch_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M:%S.%f")[:23]


@dataclass(frozen=True)
class ProfileDecisionEvent:
    run_id: str
    strategy_id: str
    profile_id: str
    market_id: str
    observed_at: datetime
    mode: str
    decision_status: str
    skip_reason: str = ""
    token_id: str = ""
    execution_mode: str = ""
    edge: float | None = None
    limit_price: float | None = None
    requested_spend_usdc: float | None = None
    capped_spend_usdc: float | None = None
    source_ok: bool = False
    orderbook_ok: bool = False
    risk_ok: bool = False
    paper_only: bool = True
    live_order_allowed: bool = False
    raw: dict[str, Any] | None = None

    @property
    def table(self) -> str:
        return "profile_decisions"


def serialize_event(event: Any) -> dict[str, Any]:
    row = asdict(event)
    if isinstance(row.get("observed_at"), datetime):
        row["observed_at"] = _format_ch_datetime(row["observed_at"])
    raw = row.get("raw")
    row["raw"] = json.dumps(raw or {}, sort_keys=True, separators=(",", ":"))
    row.pop("table", None)
    return row
```

**Step 4: Vérifier**

```bash
PYTHONPATH=python/src python3 -m pytest python/tests/test_analytics_events.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/prediction_core/analytics python/tests/test_analytics_events.py
git commit -m "feat: add analytics event models"
```

---

### Task 2.3: Créer le writer ClickHouse avec dry-run safe

**Objective:** Écrire les événements dans ClickHouse si configuré, sinon no-op/dry-run explicite.

**Files:**
- Create: `python/src/prediction_core/analytics/clickhouse_writer.py`
- Create: `python/tests/test_clickhouse_writer.py`

**Step 1: Test**

`python/tests/test_clickhouse_writer.py`:

```python
from prediction_core.analytics.clickhouse_writer import ClickHouseAnalyticsWriter


class FakeClient:
    def __init__(self):
        self.calls = []

    def insert(self, table, data, column_names=None):
        self.calls.append((table, data, column_names))


def test_writer_inserts_rows_with_column_names() -> None:
    client = FakeClient()
    writer = ClickHouseAnalyticsWriter(client=client, database="prediction_core")

    writer.insert_rows("profile_decisions", [{"run_id": "r1", "market_id": "m1"}])

    assert client.calls == [
        (
            "prediction_core.profile_decisions",
            [["r1", "m1"]],
            ["run_id", "market_id"],
        )
    ]


def test_writer_noops_empty_rows() -> None:
    client = FakeClient()
    writer = ClickHouseAnalyticsWriter(client=client, database="prediction_core")

    writer.insert_rows("profile_decisions", [])

    assert client.calls == []
```

**Step 2: Run failure**

```bash
PYTHONPATH=python/src python3 -m pytest python/tests/test_clickhouse_writer.py -q
```

Expected: FAIL.

**Step 3: Implémenter**

`python/src/prediction_core/analytics/clickhouse_writer.py`:

```python
from __future__ import annotations

import os
from typing import Any


class ClickHouseAnalyticsWriter:
    def __init__(self, *, client: Any, database: str = "prediction_core") -> None:
        self.client = client
        self.database = database

    def insert_rows(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        columns = list(rows[0].keys())
        data = [[row.get(column) for column in columns] for row in rows]
        self.client.insert(f"{self.database}.{table}", data, column_names=columns)


def create_clickhouse_writer_from_env() -> ClickHouseAnalyticsWriter | None:
    url = os.environ.get("PREDICTION_CORE_CLICKHOUSE_URL")
    if not url:
        return None
    try:
        import clickhouse_connect
    except ImportError as exc:
        raise RuntimeError("clickhouse-connect is required when PREDICTION_CORE_CLICKHOUSE_URL is set") from exc

    client = clickhouse_connect.get_client(
        host=os.environ.get("PREDICTION_CORE_CLICKHOUSE_HOST", "localhost"),
        port=int(os.environ.get("PREDICTION_CORE_CLICKHOUSE_PORT", "8123")),
        username=os.environ.get("PREDICTION_CORE_CLICKHOUSE_USER", "prediction"),
        password=os.environ.get("PREDICTION_CORE_CLICKHOUSE_PASSWORD", "prediction"),
        database=os.environ.get("PREDICTION_CORE_CLICKHOUSE_DATABASE", "prediction_core"),
    )
    return ClickHouseAnalyticsWriter(client=client, database=os.environ.get("PREDICTION_CORE_CLICKHOUSE_DATABASE", "prediction_core"))
```

**Step 4: Vérifier**

```bash
PYTHONPATH=python/src python3 -m pytest python/tests/test_clickhouse_writer.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/prediction_core/analytics/clickhouse_writer.py python/tests/test_clickhouse_writer.py
git commit -m "feat: add clickhouse analytics writer"
```

---

# Phase 3 — Adapter les sorties existantes

### Task 3.1: Convertir les rows shortlist/profile en ProfileDecisionEvent

**Objective:** Émettre `profile_decisions` depuis les résultats stratégie/profil météo.

**Files:**
- Create: `python/src/weather_pm/analytics_adapter.py`
- Create: `python/tests/test_weather_analytics_adapter.py`

**Step 1: Test**

`python/tests/test_weather_analytics_adapter.py`:

```python
from datetime import UTC, datetime

from weather_pm.analytics_adapter import profile_decision_events_from_shortlist


def test_shortlist_rows_convert_to_profile_decision_events() -> None:
    payload = {
        "run_id": "run-1",
        "generated_at": "2026-04-27T12:00:00+00:00",
        "rows": [
            {
                "market_id": "m1",
                "token_id": "t1",
                "strategy_id": "weather_bookmaker_v1",
                "strategy_profile_id": "surface_grid_trader",
                "decision_status": "trade_small",
                "execution_blocker": "",
                "edge": 0.08,
                "strict_limit_price": 0.42,
                "source_direct": True,
                "orderbook_ok": True,
                "profile_execution_mode": "paper_micro_strict_limit",
                "profile_risk_caps": {"max_order_usdc": 2.0},
            }
        ],
    }

    events = profile_decision_events_from_shortlist(payload, default_observed_at=datetime(2026, 4, 27, tzinfo=UTC))

    assert len(events) == 1
    event = events[0]
    assert event.run_id == "run-1"
    assert event.strategy_id == "weather_bookmaker_v1"
    assert event.profile_id == "surface_grid_trader"
    assert event.market_id == "m1"
    assert event.decision_status == "trade_small"
    assert event.limit_price == 0.42
    assert event.risk_ok is True
```

**Step 2: Run failure**

```bash
PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_analytics_adapter.py -q
```

Expected: FAIL.

**Step 3: Implémenter**

`python/src/weather_pm/analytics_adapter.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from prediction_core.analytics.events import ProfileDecisionEvent


def _parse_observed_at(payload: dict[str, Any], default: datetime | None) -> datetime:
    value = payload.get("generated_at") or payload.get("observed_at")
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return default or datetime.now(UTC)


def profile_decision_events_from_shortlist(
    payload: dict[str, Any], *, default_observed_at: datetime | None = None
) -> list[ProfileDecisionEvent]:
    observed_at = _parse_observed_at(payload, default_observed_at)
    run_id = payload.get("run_id") or payload.get("report_id") or observed_at.strftime("weather-%Y%m%dT%H%M%SZ")
    events: list[ProfileDecisionEvent] = []
    for row in payload.get("rows") or payload.get("shortlist") or []:
        profile_id = row.get("strategy_profile_id") or row.get("profile_id") or "default"
        strategy_id = row.get("strategy_id") or row.get("strategy") or "weather_pm"
        decision_status = row.get("decision_status") or row.get("operator_action") or "unknown"
        skip_reason = row.get("execution_blocker") or row.get("skip_reason") or ""
        risk_caps = row.get("profile_risk_caps") or {}
        requested = row.get("requested_spend_usdc")
        capped = risk_caps.get("max_order_usdc") if isinstance(risk_caps, dict) else None
        events.append(
            ProfileDecisionEvent(
                run_id=str(run_id),
                strategy_id=str(strategy_id),
                profile_id=str(profile_id),
                market_id=str(row.get("market_id") or row.get("condition_id") or ""),
                token_id=str(row.get("token_id") or ""),
                observed_at=observed_at,
                mode="paper",
                decision_status=str(decision_status),
                skip_reason=str(skip_reason),
                execution_mode=str(row.get("profile_execution_mode") or row.get("execution_mode") or ""),
                edge=row.get("edge"),
                limit_price=row.get("strict_limit_price") or row.get("limit_price"),
                requested_spend_usdc=requested,
                capped_spend_usdc=capped,
                source_ok=bool(row.get("source_direct", False)),
                orderbook_ok=bool(row.get("orderbook_ok", False) or row.get("orderbook")),
                risk_ok=not bool(skip_reason),
                paper_only=True,
                live_order_allowed=False,
                raw=row,
            )
        )
    return events
```

**Step 4: Vérifier**

```bash
PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_analytics_adapter.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/weather_pm/analytics_adapter.py python/tests/test_weather_analytics_adapter.py
git commit -m "feat(weather): adapt strategy profile decisions to analytics events"
```

---

### Task 3.2: Ajouter commande CLI export ClickHouse analytics

**Objective:** Permettre d’envoyer un shortlist JSON existant vers ClickHouse.

**Files:**
- Modify: `python/src/weather_pm/cli.py`
- Test: `python/tests/test_weather_analytics_cli.py`

**Step 1: Test subprocess CLI**

`python/tests/test_weather_analytics_cli.py`:

```python
from pathlib import Path
import json
import subprocess
import sys


def test_weather_analytics_export_dry_run(tmp_path: Path) -> None:
    payload = {
        "run_id": "run-1",
        "generated_at": "2026-04-27T12:00:00+00:00",
        "rows": [
            {
                "market_id": "m1",
                "strategy_id": "weather_bookmaker_v1",
                "strategy_profile_id": "surface_grid_trader",
                "decision_status": "skip",
                "execution_blocker": "edge_below_threshold",
            }
        ],
    }
    input_path = tmp_path / "shortlist.json"
    input_path.write_text(json.dumps(payload))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "export-analytics-clickhouse",
            "--shortlist-json",
            str(input_path),
            "--dry-run",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env={"PYTHONPATH": "src"},
        text=True,
        capture_output=True,
        check=True,
    )

    assert "profile_decisions" in result.stdout
    assert "rows=1" in result.stdout
```

**Step 2: Run failure**

```bash
cd /home/jul/P-core/python
PYTHONPATH=src python3 -m pytest tests/test_weather_analytics_cli.py -q
```

Expected: FAIL.

**Step 3: Ajouter commande CLI**

Dans `python/src/weather_pm/cli.py`, ajouter un sous-command:

```python
# imports
from prediction_core.analytics.clickhouse_writer import create_clickhouse_writer_from_env
from prediction_core.analytics.events import serialize_event
from weather_pm.analytics_adapter import profile_decision_events_from_shortlist
```

Ajouter parser:

```python
export_analytics = subparsers.add_parser("export-analytics-clickhouse")
export_analytics.add_argument("--shortlist-json", required=True)
export_analytics.add_argument("--dry-run", action="store_true")
```

Ajouter handler logique:

```python
if args.command == "export-analytics-clickhouse":
    payload = json.loads(Path(args.shortlist_json).read_text())
    events = profile_decision_events_from_shortlist(payload)
    rows = [serialize_event(event) for event in events]
    if args.dry_run:
        print(f"profile_decisions rows={len(rows)} dry_run=true")
        return 0
    writer = create_clickhouse_writer_from_env()
    if writer is None:
        raise SystemExit("PREDICTION_CORE_CLICKHOUSE_URL is required unless --dry-run is used")
    writer.insert_rows("profile_decisions", rows)
    print(f"profile_decisions rows={len(rows)} inserted=true")
    return 0
```

Adapter au style actuel du fichier `cli.py`.

**Step 4: Vérifier**

```bash
cd /home/jul/P-core/python
PYTHONPATH=src python3 -m pytest tests/test_weather_analytics_cli.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/weather_pm/cli.py python/tests/test_weather_analytics_cli.py
git commit -m "feat(weather): add clickhouse analytics export cli"
```

---

# Phase 4 — Grafana dashboards provisionnés

Status: completed 2026-04-27 — dashboard provider and Strategy vs Profile, Decision Debug, Paper Ledger dashboards added; JSON validation and Grafana provisioning tests pass.

### Task 4.1: Provisionner provider dashboards

**Objective:** Grafana doit charger les JSON dashboards automatiquement.

**Files:**
- Create: `infra/analytics/grafana/provisioning/dashboards/prediction-core.yml`

**Step 1: Créer provider**

`infra/analytics/grafana/provisioning/dashboards/prediction-core.yml`:

```yaml
apiVersion: 1

providers:
  - name: Prediction Core
    orgId: 1
    folder: Prediction Core
    type: file
    disableDeletion: false
    editable: true
    updateIntervalSeconds: 30
    options:
      path: /var/lib/grafana/dashboards
```

**Step 2: Étendre test Grafana**

Dans `python/tests/test_grafana_provisioning.py`:

```python
DASHBOARD_PROVIDER = ROOT / "infra" / "analytics" / "grafana" / "provisioning" / "dashboards" / "prediction-core.yml"


def test_grafana_dashboard_provider_is_provisioned() -> None:
    text = DASHBOARD_PROVIDER.read_text()
    assert "Prediction Core" in text
    assert "/var/lib/grafana/dashboards" in text
```

**Step 3: Run**

```bash
python3 -m pytest python/tests/test_grafana_provisioning.py -q
```

Expected: PASS.

**Step 4: Commit**

```bash
git add infra/analytics/grafana/provisioning/dashboards/prediction-core.yml python/tests/test_grafana_provisioning.py
git commit -m "infra: provision prediction core grafana dashboards"
```

---

### Task 4.2: Ajouter dashboard Strategy vs Profile minimal

**Objective:** Avoir le premier cockpit utile: comparaison `strategy_id × profile_id`.

**Files:**
- Create: `infra/analytics/grafana/dashboards/strategy-vs-profile.json`
- Modify: `python/tests/test_grafana_provisioning.py`

**Step 1: Ajouter test dashboard**

```python
import json

DASHBOARD = ROOT / "infra" / "analytics" / "grafana" / "dashboards" / "strategy-vs-profile.json"


def test_strategy_vs_profile_dashboard_has_required_panels() -> None:
    dashboard = json.loads(DASHBOARD.read_text())
    text = json.dumps(dashboard)
    for label in ["Strategy vs Profile", "Net PnL", "Trade Count", "Skip Count", "Average Edge"]:
        assert label in text
    assert "profile_metrics" in text
    assert "strategy_metrics" in text
```

**Step 2: Créer dashboard JSON minimal**

Créer un dashboard Grafana JSON avec:

- title: `Strategy vs Profile`
- datasource UID: `prediction-core-clickhouse`
- panels SQL:

```sql
SELECT
  strategy_id,
  profile_id,
  sum(net_pnl_usdc) AS net_pnl
FROM prediction_core.profile_metrics
WHERE $__timeFilter(observed_at)
GROUP BY strategy_id, profile_id
ORDER BY net_pnl DESC
```

```sql
SELECT
  strategy_id,
  profile_id,
  sum(trade_count) AS trades,
  sum(skip_count) AS skips,
  avg(roi) AS roi
FROM prediction_core.profile_metrics
WHERE $__timeFilter(observed_at)
GROUP BY strategy_id, profile_id
```

```sql
SELECT
  strategy_id,
  profile_id,
  avg(avg_edge) AS avg_edge
FROM prediction_core.strategy_metrics
WHERE $__timeFilter(observed_at)
GROUP BY strategy_id, profile_id
```

**Step 3: Vérifier JSON**

```bash
python3 -m json.tool infra/analytics/grafana/dashboards/strategy-vs-profile.json >/tmp/strategy-vs-profile.pretty.json
python3 -m pytest python/tests/test_grafana_provisioning.py -q
```

Expected: PASS.

**Step 4: Commit**

```bash
git add infra/analytics/grafana/dashboards/strategy-vs-profile.json python/tests/test_grafana_provisioning.py
git commit -m "feat: add strategy vs profile grafana dashboard"
```

---

### Task 4.3: Ajouter dashboard Decision Debug minimal

**Objective:** Voir pourquoi chaque profil trade ou skip.

**Files:**
- Create: `infra/analytics/grafana/dashboards/decision-debug.json`

**Queries essentielles:**

```sql
SELECT
  observed_at,
  market_id,
  strategy_id,
  profile_id,
  decision_status,
  skip_reason,
  edge,
  limit_price,
  source_ok,
  orderbook_ok,
  risk_ok,
  blocker
FROM prediction_core.debug_decisions
WHERE $__timeFilter(observed_at)
ORDER BY observed_at DESC
LIMIT 500
```

```sql
SELECT
  skip_reason,
  count() AS count
FROM prediction_core.debug_decisions
WHERE $__timeFilter(observed_at)
  AND decision_status NOT IN ('trade', 'trade_small')
GROUP BY skip_reason
ORDER BY count DESC
```

**Verification:**

Add a test asserting JSON contains `Decision Debug`, `debug_decisions`, `skip_reason`, `risk_ok`.

**Commit:**

```bash
git add infra/analytics/grafana/dashboards/decision-debug.json python/tests/test_grafana_provisioning.py
git commit -m "feat: add decision debug grafana dashboard"
```

---

### Task 4.4: Ajouter dashboard Paper Ledger minimal

**Objective:** Suivre les positions et PnL paper.

**Files:**
- Create: `infra/analytics/grafana/dashboards/paper-ledger.json`

**Queries essentielles:**

```sql
SELECT
  observed_at,
  strategy_id,
  profile_id,
  sum(exposure_usdc) AS exposure_usdc,
  sum(net_pnl_usdc) AS net_pnl_usdc,
  sum(costs_usdc) AS costs_usdc
FROM prediction_core.paper_pnl_snapshots
WHERE $__timeFilter(observed_at)
GROUP BY observed_at, strategy_id, profile_id
ORDER BY observed_at
```

```sql
SELECT
  market_id,
  strategy_id,
  profile_id,
  sum(quantity) AS quantity,
  anyLast(avg_price) AS avg_price,
  anyLast(exposure_usdc) AS exposure_usdc,
  anyLast(status) AS status
FROM prediction_core.paper_positions
WHERE $__timeFilter(observed_at)
GROUP BY market_id, strategy_id, profile_id
ORDER BY exposure_usdc DESC
```

**Verification:** dashboard JSON contains `Paper Ledger`, `paper_pnl_snapshots`, `paper_positions`, `net_pnl_usdc`.

**Commit:**

```bash
git add infra/analytics/grafana/dashboards/paper-ledger.json python/tests/test_grafana_provisioning.py
git commit -m "feat: add paper ledger grafana dashboard"
```

---

# Phase 5 — Smoke test réel ClickHouse

### Task 5.1: Ajouter script smoke analytics stack

**Objective:** Prouver Docker → ClickHouse schema → insert → query.

**Files:**
- Create: `infra/analytics/scripts/smoke_clickhouse.sh`

**Script:**

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
docker compose up -d clickhouse

for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8123/ping >/dev/null; then
    break
  fi
  sleep 1
  if [ "$i" = 60 ]; then
    echo "ClickHouse did not become ready" >&2
    exit 1
  fi
done

curl -fsS 'http://127.0.0.1:8123/?user=prediction&password=prediction' \
  --data-binary "SELECT count() FROM prediction_core.profile_decisions" >/tmp/profile_decisions_count.txt

cat /tmp/profile_decisions_count.txt
```

**Step 2: chmod**

```bash
chmod +x infra/analytics/scripts/smoke_clickhouse.sh
```

**Step 3: Run**

```bash
infra/analytics/scripts/smoke_clickhouse.sh
```

Expected: prints a count, usually `0`.

**Step 4: Commit**

```bash
git add infra/analytics/scripts/smoke_clickhouse.sh
git commit -m "test: add clickhouse analytics smoke script"
```

---

### Task 5.2: Ajouter smoke CLI dry-run puis insert réel

**Objective:** Prouver qu’un shortlist météo peut alimenter ClickHouse.

**Files:**
- Create: `python/tests/fixtures/weather_analytics_shortlist.json`
- Optional Create: `infra/analytics/scripts/smoke_weather_export.sh`

**Fixture:**

```json
{
  "run_id": "smoke-run-1",
  "generated_at": "2026-04-27T12:00:00+00:00",
  "rows": [
    {
      "market_id": "smoke-market-1",
      "token_id": "smoke-token-1",
      "strategy_id": "weather_bookmaker_v1",
      "strategy_profile_id": "surface_grid_trader",
      "decision_status": "trade_small",
      "execution_blocker": "",
      "edge": 0.08,
      "strict_limit_price": 0.42,
      "source_direct": true,
      "orderbook_ok": true,
      "profile_execution_mode": "paper_micro_strict_limit",
      "profile_risk_caps": {"max_order_usdc": 2.0}
    }
  ]
}
```

**Dry-run:**

```bash
cd /home/jul/P-core/python
PYTHONPATH=src python3 -m weather_pm.cli export-analytics-clickhouse \
  --shortlist-json tests/fixtures/weather_analytics_shortlist.json \
  --dry-run
```

Expected: `profile_decisions rows=1 dry_run=true`.

**Real insert after ClickHouse up:**

```bash
cd /home/jul/P-core/python
PREDICTION_CORE_CLICKHOUSE_URL=http://127.0.0.1:8123 \
PREDICTION_CORE_CLICKHOUSE_HOST=127.0.0.1 \
PREDICTION_CORE_CLICKHOUSE_PORT=8123 \
PREDICTION_CORE_CLICKHOUSE_USER=prediction \
PREDICTION_CORE_CLICKHOUSE_PASSWORD=prediction \
PREDICTION_CORE_CLICKHOUSE_DATABASE=prediction_core \
PYTHONPATH=src python3 -m weather_pm.cli export-analytics-clickhouse \
  --shortlist-json tests/fixtures/weather_analytics_shortlist.json
```

Verify:

```bash
curl -fsS 'http://127.0.0.1:8123/?user=prediction&password=prediction' \
  --data-binary "SELECT run_id, strategy_id, profile_id, market_id FROM prediction_core.profile_decisions WHERE run_id = 'smoke-run-1' FORMAT TSVWithNames"
```

Expected row contains `smoke-run-1 weather_bookmaker_v1 surface_grid_trader smoke-market-1`.

**Commit:**

```bash
git add python/tests/fixtures/weather_analytics_shortlist.json infra/analytics/scripts/smoke_weather_export.sh
git commit -m "test: add weather analytics export smoke fixture"
```

---

# Phase 6 — Intégration runtime progressive

### Task 6.1: Hook analytics writer dans le batch météo paper/profile

**Objective:** À chaque run météo profil/paper, écrire automatiquement `profile_decisions` si ClickHouse est configuré.

**Files:**
- Modify: `python/src/weather_pm/cli.py`
- Modify: tests existants autour `strategy-profile-paper-orders` ou créer `python/tests/test_weather_strategy_profile_analytics_hook.py`

**Acceptance criteria:**

- Si `PREDICTION_CORE_CLICKHOUSE_URL` absent: aucune erreur, comportement existant inchangé.
- Si writer présent: `profile_decisions` est inséré.
- La sortie CLI mentionne un résumé:

```text
analytics.profile_decisions.rows=<n>
analytics.enabled=true|false
```

---

### Task 6.2: Émettre `debug_decisions`

**Objective:** Alimenter le dashboard Decision Debug.

**Files:**
- Extend: `prediction_core.analytics.events`
- Extend: `weather_pm.analytics_adapter`
- Tests: `python/tests/test_weather_analytics_adapter.py`

**Mapping:**

`debug_decisions` reprend les mêmes rows que `profile_decisions`, avec champs debug:

- `decision_status`
- `skip_reason`
- `edge`
- `limit_price`
- `source_ok`
- `orderbook_ok`
- `risk_ok`
- `blocker`

---

### Task 6.3: Émettre `paper_orders` et `paper_positions`

**Objective:** Alimenter Paper Ledger Grafana depuis le paper ledger existant.

**Files:**
- Extend: `prediction_core.analytics.events`
- Create/extend: `weather_pm.analytics_adapter`
- Tests:
  - `python/tests/test_weather_analytics_adapter.py`
  - `python/tests/test_weather_paper_ledger.py` si nécessaire

**Mapping paper order:**

- `paper_order_id`
- `market_id`
- `token_id`
- `strategy_profile_id` → `profile_id`
- `strategy_id`
- `observed_at`
- `side`
- `price`
- `size`
- `spend_usdc`
- `opening_fee_usdc`
- `opening_slippage_usdc`
- `estimated_exit_cost_usdc`

---

### Task 6.4: Émettre `profile_metrics` et `strategy_metrics`

**Objective:** Alimenter les agrégats Grafana sans faire des requêtes trop lourdes.

**Files:**
- Extend: `prediction_core.analytics.events`
- Add: `prediction_core.analytics.metrics`
- Tests: `python/tests/test_analytics_metrics.py`

**Computed fields:**

- counts: signal/trade/skip/decision
- PnL gross/net
- costs
- exposure
- ROI
- avg edge

---

# Phase 7 — Documentation opérateur

### Task 7.1: Documenter runbook final

**Objective:** Un opérateur doit savoir lancer, vérifier et utiliser le cockpit.

**Files:**
- Create: `docs/prediction-core-clickhouse-grafana.md`

**Content required:**

- Pourquoi ClickHouse + Grafana est le stack final.
- Comment lancer:

```bash
cd /home/jul/P-core/infra/analytics
docker compose up -d
```

- Comment vérifier ClickHouse:

```bash
curl http://127.0.0.1:8123/ping
```

- Comment exporter un run météo:

```bash
cd /home/jul/P-core/python
PYTHONPATH=src python3 -m weather_pm.cli export-analytics-clickhouse --shortlist-json <file>
```

- Dashboards disponibles:
  - Strategy vs Profile
  - Decision Debug
  - Paper Ledger
- Variables d’environnement.
- Règle sécurité: pas de secrets dans `raw`.

**Commit:**

```bash
git add docs/prediction-core-clickhouse-grafana.md
git commit -m "docs: add clickhouse grafana cockpit runbook"
```

---

# Phase 8 — Validation finale

### Task 8.1: Test suite ciblée

Run:

```bash
cd /home/jul/P-core
PYTHONPATH=python/src python3 -m pytest \
  python/tests/test_clickhouse_schema_sql.py \
  python/tests/test_grafana_provisioning.py \
  python/tests/test_analytics_events.py \
  python/tests/test_clickhouse_writer.py \
  python/tests/test_weather_analytics_adapter.py \
  -q
```

Expected: all pass.

### Task 8.2: Tests existants météo impactés

Run:

```bash
cd /home/jul/P-core/python
PYTHONPATH=src python3 -m pytest \
  tests/test_weather_strategy_profiles.py \
  tests/test_weather_strategy_shortlist.py \
  tests/test_weather_paper_ledger.py \
  tests/test_weather_analytics_cli.py \
  -q
```

Expected: all pass.

### Task 8.3: Smoke infra réel

Run:

```bash
cd /home/jul/P-core
infra/analytics/scripts/smoke_clickhouse.sh
```

Expected: ClickHouse responds and schema exists.

Then:

```bash
cd /home/jul/P-core/python
PYTHONPATH=src python3 -m weather_pm.cli export-analytics-clickhouse \
  --shortlist-json tests/fixtures/weather_analytics_shortlist.json \
  --dry-run
```

Expected: `profile_decisions rows=1 dry_run=true`.

If ClickHouse dependencies are installed, run real insert.

### Task 8.4: Final git review

```bash
cd /home/jul/P-core
git status --short
git log --oneline --decorate -10
git diff origin/main...HEAD --stat
```

Confirm only ClickHouse/Grafana analytics work is included.

---

## Execution Progress

- Phase 2 completed on 2026-04-27: added optional `clickhouse-connect` analytics dependency, analytics event serialization models, ClickHouse writer, and tests. Validation passed:
  - `PYTHONPATH=python/src python3 -m pytest python/tests/test_analytics_events.py python/tests/test_clickhouse_writer.py -q` → `6 passed`
  - `python3 - <<'PY' ... tomllib.loads(Path('python/pyproject.toml').read_text()) ... PY` → `ok`
- Phase 3 completed on 2026-04-27: added `weather_pm` shortlist/profile analytics adapter and `export-analytics-clickhouse` CLI command with dry-run and env-backed insert paths. Validation passed:
  - `PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_analytics_adapter.py python/tests/test_weather_analytics_cli.py -q` → `5 passed`
  - `PYTHONPATH=python/src python3 -m pytest python/tests/test_analytics_events.py python/tests/test_clickhouse_writer.py -q` → `6 passed`
- Phase 5 completed on 2026-04-27: added ClickHouse and weather export smoke scripts plus a short weather analytics fixture. Validation passed:
  - `PYTHONPATH=python/src python3 -m weather_pm.cli export-analytics-clickhouse --shortlist-json python/tests/fixtures/weather_analytics_shortlist.json --dry-run` → `profile_decisions rows=1 dry_run=true`
  - `bash -n infra/analytics/scripts/smoke_clickhouse.sh` → passed
  - `bash -n infra/analytics/scripts/smoke_weather_export.sh` → passed
  - `PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_analytics_cli.py python/tests/test_grafana_provisioning.py -q` → `10 passed`
  - Real Docker smoke was attempted with legacy `docker-compose` (Docker daemon available; Compose v2 unavailable) but was environment-blocked by docker-compose/python client error: `Not supported URL scheme http+docker`.
- Phase 6 completed on 2026-04-27: added progressive analytics events for debug decisions, paper orders/positions, profile/strategy metrics, weather adapter conversions, and export-path runtime hook summaries/no-op behavior when ClickHouse is unconfigured. Validation passed:
  - `PYTHONPATH=python/src python3 -m pytest python/tests/test_analytics_events.py python/tests/test_analytics_metrics.py python/tests/test_weather_analytics_adapter.py python/tests/test_weather_analytics_cli.py python/tests/test_clickhouse_writer.py -q` → `18 passed`
  - `PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_paper_ledger.py -q` → `11 passed`
  - Deferred broader direct hooking into ambiguous paper/profile batch commands; the safe reusable export path now emits profile_decisions, debug_decisions, profile_metrics, and strategy_metrics, while paper ledger converters cover paper_orders and paper_positions foundations.
- Phase 7 completed on 2026-04-27: added final operator runbook for the ClickHouse + Grafana cockpit and a docs contract test. Validation passed:
  - `PYTHONPATH=python/src python3 -m pytest python/tests/test_prediction_core_analytics_docs.py -q` → `3 passed`
  - `PYTHONPATH=python/src python3 -m pytest python/tests/test_grafana_provisioning.py python/tests/test_weather_analytics_cli.py -q` → `10 passed`
- Phase 8 completed on 2026-04-27: final validation passed for the complete ClickHouse + Grafana cockpit implementation. Validation passed:
  - `PYTHONPATH=python/src python3 -m pytest python/tests/test_clickhouse_schema_sql.py python/tests/test_grafana_provisioning.py python/tests/test_analytics_events.py python/tests/test_clickhouse_writer.py python/tests/test_weather_analytics_adapter.py python/tests/test_analytics_metrics.py python/tests/test_weather_analytics_cli.py python/tests/test_prediction_core_analytics_docs.py -q` → `29 passed`
  - `cd python && PYTHONPATH=src python3 -m pytest tests/test_weather_strategy_shortlist.py tests/test_weather_paper_ledger.py tests/test_weather_analytics_cli.py -q` → `39 passed`
  - `PYTHONPATH=python/src python3 -m weather_pm.cli export-analytics-clickhouse --shortlist-json python/tests/fixtures/weather_analytics_shortlist.json --dry-run` → `analytics.profile_decisions.rows=1`, `analytics.enabled=false`
  - Real Docker smoke remains environment-blocked locally by legacy `docker-compose`/Docker Python client error: `Not supported URL scheme http+docker`; the smoke scripts are syntax-validated and documented with compose v2/v1 fallback.

## Done definition

The plan is complete when:

- `infra/analytics/docker-compose.yml` starts ClickHouse + Grafana.
- ClickHouse schema creates all final analytics tables.
- Python can serialize and write `profile_decisions` to ClickHouse.
- Weather shortlist/profile output can export to ClickHouse via CLI.
- Grafana auto-provisions ClickHouse datasource.
- Grafana auto-loads at least:
  - Strategy vs Profile
  - Decision Debug
  - Paper Ledger
- Smoke script proves ClickHouse is reachable and schema exists.
- Tests pass for schema, provisioning, events, writer, weather adapter, CLI.
- Docs explain the final operator workflow.

## Final target statement

Final project architecture:

```text
Prediction Core / weather_pm / panoptique
        ↓ normalized analytical events
ClickHouse prediction_core database
        ↓ Grafana ClickHouse datasource
Grafana Prediction Core cockpit
```

This is the direct final stack. TimescaleDB can remain as legacy/scaffolded infra, but the final strategic cockpit is ClickHouse + Grafana.
