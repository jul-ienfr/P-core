# weather_pm -> prediction_core/python Integration Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** intégrer le noyau Python météo `weather_pm` dans `prediction_core/python` pour converger vers un parent autonome commun Python + Rust sous `prediction_core/`, sans déplacer `prediction_core/rust`.

**Architecture:** on garde `prediction_core/` comme parent commun. Rust reste dans `prediction_core/rust` inchangé. Le code météo Python est absorbé dans `prediction_core/python` en conservant d’abord le package `weather_pm` tel quel sous `src/weather_pm/` pour éviter une casse immédiate des imports et des tests. On ajoute le packaging Python manquant au niveau `prediction_core/python` afin que Python et Rust cohabitent proprement sous le même parent.

**Tech Stack:** Python `src/` layout, pytest, pyproject.toml, Cargo workspace Rust existant.

---

## Contexte vérifié

- Le repo git actif est `/home/jul/swarm`.
- `git status --short -- prediction_core subprojects/prediction/python` montre un worktree déjà **dirty** dans :
  - `prediction_core/python/src/prediction_core/...`
  - `prediction_core/python/tests/...`
  - `prediction_core/rust/crates/live_engine/src/lib.rs`
  - `prediction_core/rust/crates/pm_types/src/lib.rs`
  - `subprojects/prediction/python/` est actuellement **non tracké**.
- `prediction_core/README.md` définit déjà la doctrine cible :
  - `python/` = research / replay / paper / calibration / analytics / evaluation
  - `rust/` = moteur live canonique
  - `contracts/` = formats d’échange
- `prediction_core/python` existe déjà avec `src/prediction_core/...` et des tests ciblés pour `replay`, `paper`, `calibration`, `analytics`, `evaluation`.
- `prediction_core/python` n’a actuellement **aucun** `pyproject.toml`.
- `subprojects/prediction/python/src/weather_pm/` contient 12 modules Python réels :
  - `__init__.py`, `cli.py`, `models.py`, `market_parser.py`, `resolution_parser.py`, `polymarket_client.py`, `polymarket_live.py`, `execution_features.py`, `neighbor_context.py`, `scoring.py`, `decision.py`, `pipeline.py`
- `subprojects/prediction/python/tests/` contient 12 fichiers de tests + `conftest.py` qui ajoute `src/` au `sys.path`.
- `prediction_core/rust/Cargo.toml` est un vrai workspace avec membres :
  - `crates/live_engine`
  - `crates/pm_types`
  - `crates/pm_book`
  - `crates/pm_signal`
  - `crates/pm_storage`
  - `crates/pm_risk`
  - `crates/pm_executor`
  - `crates/pm_ledger`
  - `xtask`
- `prediction_core/rust/README.md` confirme que Rust est déjà la zone live canonique. Il ne faut donc pas le déplacer pour cette fusion.

## Décision de structure

### Move now
- Copier `subprojects/prediction/python/src/weather_pm/` vers `prediction_core/python/src/weather_pm/`.
- Copier `subprojects/prediction/python/tests/` vers `prediction_core/python/tests/`.
- Ajouter `prediction_core/python/pyproject.toml` pour rendre la zone Python installable/testable.
- Mettre à jour `prediction_core/python/README.md` pour documenter la coexistence de `prediction_core.*` et `weather_pm.*`.

### Leave in place
- Tout `prediction_core/rust/` reste en place.
- Tout `prediction_core/contracts/` reste en place.
- `subprojects/prediction` reste la surface cockpit/API/UI/bridge.

### Optional phase 2
- Renommer plus tard `weather_pm` vers `prediction_core.weather` ou `prediction_core.meteo`.
- Réécrire progressivement les imports et l’API publique une fois la fusion stabilisée.

## Mapping fichier par fichier

### Source -> destination Python

- `subprojects/prediction/python/src/weather_pm/__init__.py`
  -> `prediction_core/python/src/weather_pm/__init__.py`
- `subprojects/prediction/python/src/weather_pm/cli.py`
  -> `prediction_core/python/src/weather_pm/cli.py`
- `subprojects/prediction/python/src/weather_pm/models.py`
  -> `prediction_core/python/src/weather_pm/models.py`
- `subprojects/prediction/python/src/weather_pm/market_parser.py`
  -> `prediction_core/python/src/weather_pm/market_parser.py`
- `subprojects/prediction/python/src/weather_pm/resolution_parser.py`
  -> `prediction_core/python/src/weather_pm/resolution_parser.py`
- `subprojects/prediction/python/src/weather_pm/polymarket_client.py`
  -> `prediction_core/python/src/weather_pm/polymarket_client.py`
- `subprojects/prediction/python/src/weather_pm/polymarket_live.py`
  -> `prediction_core/python/src/weather_pm/polymarket_live.py`
- `subprojects/prediction/python/src/weather_pm/execution_features.py`
  -> `prediction_core/python/src/weather_pm/execution_features.py`
- `subprojects/prediction/python/src/weather_pm/neighbor_context.py`
  -> `prediction_core/python/src/weather_pm/neighbor_context.py`
- `subprojects/prediction/python/src/weather_pm/scoring.py`
  -> `prediction_core/python/src/weather_pm/scoring.py`
- `subprojects/prediction/python/src/weather_pm/decision.py`
  -> `prediction_core/python/src/weather_pm/decision.py`
- `subprojects/prediction/python/src/weather_pm/pipeline.py`
  -> `prediction_core/python/src/weather_pm/pipeline.py`

### Tests -> destination Python

- `subprojects/prediction/python/tests/conftest.py`
  -> `prediction_core/python/tests/conftest.py`
- `subprojects/prediction/python/tests/test_smoke.py`
  -> `prediction_core/python/tests/test_smoke.py`
- `subprojects/prediction/python/tests/test_market_parser.py`
  -> `prediction_core/python/tests/test_market_parser.py`
- `subprojects/prediction/python/tests/test_resolution_parser.py`
  -> `prediction_core/python/tests/test_resolution_parser.py`
- `subprojects/prediction/python/tests/test_polymarket_client.py`
  -> `prediction_core/python/tests/test_polymarket_client.py`
- `subprojects/prediction/python/tests/test_polymarket_live.py`
  -> `prediction_core/python/tests/test_polymarket_live.py`
- `subprojects/prediction/python/tests/test_execution_features.py`
  -> `prediction_core/python/tests/test_execution_features.py`
- `subprojects/prediction/python/tests/test_neighbor_context.py`
  -> `prediction_core/python/tests/test_neighbor_context.py`
- `subprojects/prediction/python/tests/test_scoring.py`
  -> `prediction_core/python/tests/test_scoring.py`
- `subprojects/prediction/python/tests/test_decision.py`
  -> `prediction_core/python/tests/test_decision.py`
- `subprojects/prediction/python/tests/test_pipeline.py`
  -> `prediction_core/python/tests/test_pipeline.py`
- `subprojects/prediction/python/tests/test_cli_score_market.py`
  -> `prediction_core/python/tests/test_cli_score_market.py`

## Task 1: Add packaging baseline for prediction_core/python

**Objective:** rendre `prediction_core/python` installable/testable sans dépendre uniquement d’un `PYTHONPATH=src` bricolé.

**Files:**
- Create: `prediction_core/python/pyproject.toml`
- Modify: `prediction_core/python/README.md`

**Step 1: Write failing packaging check**

Run:
```bash
cd /home/jul/swarm/prediction_core/python
python3 -m pytest tests/test_smoke.py -q
```

Expected before import copy: possible failure or incomplete coverage because `weather_pm` is absent.

**Step 2: Create minimal pyproject**

Use setuptools with `package-dir = {"" = "src"}` and package discovery under `src` so both `prediction_core` and `weather_pm` are discoverable.

Required content outline:
```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "prediction-core-python"
version = "0.1.0"
description = "Canonical Python packages for prediction_core"
requires-python = ">=3.11"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
include = ["prediction_core*", "weather_pm*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Step 3: Update README commands**

Document both styles:
```bash
cd /home/jul/swarm/prediction_core/python
PYTHONPATH=src pytest -q
python3 -m weather_pm.cli --help
```

**Step 4: Commit**

Do not commit yet if continuing in one working change; stage later as a single cohesive integration change.

## Task 2: Copy weather_pm package into prediction_core/python

**Objective:** injecter le noyau météo sans renommer le package.

**Files:**
- Create: `prediction_core/python/src/weather_pm/*.py`

**Step 1: Copy package files verbatim**

Copy all 12 files from `subprojects/prediction/python/src/weather_pm/` to `prediction_core/python/src/weather_pm/`.

**Step 2: Verify import surface**

Run:
```bash
cd /home/jul/swarm/prediction_core/python
PYTHONPATH=src python3 - <<'PY'
import weather_pm
from weather_pm.cli import build_parser
print(weather_pm.__version__)
print(build_parser().prog)
PY
```

Expected:
- version prints `0.1.0`
- prog prints `weather-pm`

## Task 3: Copy tests and path bootstrap

**Objective:** porter la preuve existante avec le minimum de changement.

**Files:**
- Create: `prediction_core/python/tests/conftest.py`
- Create: `prediction_core/python/tests/test_smoke.py`
- Create: `prediction_core/python/tests/test_market_parser.py`
- Create: `prediction_core/python/tests/test_resolution_parser.py`
- Create: `prediction_core/python/tests/test_polymarket_client.py`
- Create: `prediction_core/python/tests/test_polymarket_live.py`
- Create: `prediction_core/python/tests/test_execution_features.py`
- Create: `prediction_core/python/tests/test_neighbor_context.py`
- Create: `prediction_core/python/tests/test_scoring.py`
- Create: `prediction_core/python/tests/test_decision.py`
- Create: `prediction_core/python/tests/test_pipeline.py`
- Create: `prediction_core/python/tests/test_cli_score_market.py`

**Step 1: Copy tests verbatim**

Keep existing names because they do not collide with current `prediction_core/python/tests/*`.

**Step 2: Keep conftest path injection for now**

Use the copied `conftest.py` unchanged to preserve compatibility with existing subprocess tests and `src/` layout.

**Step 3: Verify narrow smoke**

Run:
```bash
cd /home/jul/swarm/prediction_core/python
PYTHONPATH=src pytest tests/test_smoke.py tests/test_market_parser.py -q
```

Expected: PASS.

## Task 4: Validate full Python integration

**Objective:** prove that old `prediction_core` tests and imported `weather_pm` tests coexist.

**Files:**
- No new files required

**Step 1: Run existing prediction_core tests**

Run:
```bash
cd /home/jul/swarm/prediction_core/python
PYTHONPATH=src pytest \
  tests/test_replay_signatures.py \
  tests/test_paper_simulation.py \
  tests/test_calibration_metrics.py \
  tests/test_analytics_scoring.py \
  tests/test_evaluation_metrics.py -q
```

Expected: PASS.

**Step 2: Run imported weather_pm tests**

Run:
```bash
cd /home/jul/swarm/prediction_core/python
PYTHONPATH=src pytest \
  tests/test_smoke.py \
  tests/test_market_parser.py \
  tests/test_resolution_parser.py \
  tests/test_polymarket_client.py \
  tests/test_polymarket_live.py \
  tests/test_execution_features.py \
  tests/test_neighbor_context.py \
  tests/test_scoring.py \
  tests/test_decision.py \
  tests/test_pipeline.py \
  tests/test_cli_score_market.py -q
```

Expected: PASS.

**Step 3: Run combined suite**

Run:
```bash
cd /home/jul/swarm/prediction_core/python
PYTHONPATH=src pytest tests -q
```

Expected: PASS.

## Task 5: Prove Rust stayed untouched functionally

**Objective:** vérifier que la fusion Python n’a pas cassé la zone Rust ni déplacé son rôle.

**Files:**
- No Rust file modifications expected

**Step 1: Verify Rust workspace still resolves**

Run:
```bash
cd /home/jul/swarm/prediction_core/rust
cargo test -q
```

Expected:
- workspace builds/tests pass, or
- if an existing Rust-local dirty-state failure already exists, failure is clearly attributable to pre-existing Rust changes rather than the Python fusion.

**Step 2: Verify no Rust files were edited by the integration**

Run:
```bash
git -C /home/jul/swarm status --short -- prediction_core/rust | cat
```

Expected:
- no new Rust diffs from the Python integration itself.

## Task 6: Document final doctrine

**Objective:** rendre le split clair pour la suite.

**Files:**
- Modify: `prediction_core/python/README.md`
- Optional modify later: `prediction_core/README.md`

**Step 1: State the current ownership clearly**

Add a short section:
- `prediction_core/python` hosts canonical Python research/eval packages plus imported `weather_pm` MVP package.
- `prediction_core/rust` remains the canonical live engine workspace.
- `subprojects/prediction` consumes outputs and provides cockpit/API/UI surfaces.

**Step 2: Capture phase-2 rename as future work, not current work**

Document that a later phase may rename `weather_pm` into the `prediction_core` namespace after import stabilization.

---

## Bottom line

- **Do now:** absorb `weather_pm` into `prediction_core/python`, add `pyproject.toml`, copy tests, validate Python + Rust.
- **Do not do now:** move `prediction_core/rust`, rename Python package, or create a new top-level repo.
- **Phase 2:** namespace cleanup and deeper convergence under a single canonical Python API.