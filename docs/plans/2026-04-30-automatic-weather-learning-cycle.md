# Automatic Weather Learning Cycle Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Make P-core weather/Polymarket learning as automatic, reliable, and performant as possible while remaining strictly paper-only.

**Architecture:** Add a `weather_pm.learning_cycle` orchestration layer that composes existing CLI/domain bricks: account backfill, trade/no-trade dataset creation, shadow paper orders, profile evaluation, learning report, auto action plan, and high-information backfill plan. Persist every cycle as immutable JSON/Markdown artifacts plus an append-only experiment ledger so future cycles can deduplicate, evaluate hypotheses, and choose the next best experiment automatically.

**Tech Stack:** Python src layout under `/home/jul/P-core/python/src/weather_pm`, pytest, JSON/Markdown artifacts under `data/polymarket`, existing `weather_pm.cli`, current cron job `312c3b855271` running paper-only in `/home/jul/P-core/.parallel/weather-learning/integration`.

---

## Contexte vérifié

- Worktree propre vérifié: `/home/jul/P-core/.parallel/weather-learning/integration`.
- HEAD vérifié: `98634cb`, synchronisé avec `origin/main` (`0 0`).
- CLI existant vérifié avec `PYTHONPATH=python/src python3 -m weather_pm.cli --help`.
- Surfaces CLI déjà disponibles:
  - `backfill-account-trades`
  - `import-account-trades`
  - `shadow-profile-report`
  - `shadow-paper-runner`
  - `shadow-profile-evaluator`
  - `shadow-profile-learning-report`
  - `operator-refresh`
  - `paper-watchlist`
- Fichiers existants vérifiés:
  - `python/src/weather_pm/shadow_paper_runner.py`
  - `python/src/weather_pm/cli.py`
  - `scripts/weather_operator_daily.py`
  - `scripts/weather_operator_paper_cron_prompt.py`
  - `python/tests/test_weather_shadow_paper_runner.py`
  - `python/tests/test_weather_operator_daily.py`
- Artefacts récents vérifiés:
  - `data/polymarket/account-analysis/targeted-cpr-20260430T095132Z/shadow_paper_orders_coldmath_poligarch_railbird.json`
  - `data/polymarket/account-analysis/targeted-cpr-20260430T095132Z/shadow_profile_evaluation_coldmath_poligarch_railbird.json`
  - `data/polymarket/account-analysis/targeted-cpr-20260430T095132Z/shadow_profile_learning_report_coldmath_poligarch_railbird.json`
  - `data/polymarket/operator-daily/weather_operator_daily_20260430T215804Z.json`
  - `data/polymarket/operator-daily/weather_shadow_profile_learning_report_20260430T215804Z.json`
- Le dernier daily smoke vérifié contient `learning_report_present=true`, `profile_actions=1`, `high_information_cases=0`, `paper_only=true`, `live_order_allowed=false`, aucun `live_order_allowed=true` imbriqué.
- Cron actif vérifié: `312c3b855271`, nom `P-core weather operator paper-only READY monitor`, schedule `every 30m`, `deliver=local`, workdir `/home/jul/P-core/.parallel/weather-learning/integration`.
- Contrainte produit ferme: paper-only par défaut, jamais d’ordre live dans cette boucle.

---

## Principes non négociables

1. **Paper-only partout**
   - Tous les artefacts produits doivent inclure `paper_only: true` et `live_order_allowed: false`.
   - Toute présence imbriquée de `live_order_allowed: true` est une erreur P1.
   - Aucun chemin `learning-cycle` ne doit appeler `paper-ledger-place` ou une surface live.

2. **TDD strict**
   - Chaque nouveau helper/module/CLI commence par un test RED.
   - Vérifier le RED avec le node id exact.
   - Implémenter minimalement.
   - Relancer test ciblé puis suite pertinente.

3. **Artefacts immuables et traçables**
   - Chaque cycle écrit dans `data/polymarket/learning-cycles/<run_id>/`.
   - Ne jamais écraser les sorties d’un cycle précédent.
   - Inclure chemins source, hashes d’inputs, paramètres, résumé, et invariants sécurité.

4. **Automatique mais borné**
   - Limites explicites: comptes, trades par compte, marchés, timeout, taille des sorties.
   - Cache/réutilisation des artefacts existants avant nouveau réseau quand possible.
   - Mode `--no-network` pour tests et dry-runs.

5. **Performance réelle avant PnL naïf**
   - Évaluer calibration, source reliability, capturabilité/liquidité, slippage/frais, taille d’échantillon, stabilité profil.
   - Promotion seulement si les scores de confiance passent.

---

# Phase 1 — Cycle orchestrator minimal

## Task 1: Créer le module `weather_pm.learning_cycle`

**Objective:** Ajouter un module pur qui construit le squelette de cycle et le contrat de sécurité.

**Files:**
- Create: `python/src/weather_pm/learning_cycle.py`
- Test: `python/tests/test_weather_learning_cycle.py`

**Step 1: Write failing test**

```python
def test_build_learning_cycle_contract_is_paper_only_and_bounded(tmp_path):
    from weather_pm.learning_cycle import build_learning_cycle_contract

    contract = build_learning_cycle_contract(
        run_id="learn-20260430T220000Z",
        output_dir=tmp_path / "learn-20260430T220000Z",
        max_accounts=80,
        trades_per_account=200,
        lookback_days=30,
    )

    assert contract["run_id"] == "learn-20260430T220000Z"
    assert contract["paper_only"] is True
    assert contract["live_order_allowed"] is False
    assert contract["no_real_order_placed"] is True
    assert contract["limits"] == {
        "max_accounts": 80,
        "trades_per_account": 200,
        "lookback_days": 30,
    }
    assert contract["output_dir"].endswith("learn-20260430T220000Z")
```

**Step 2: Run test to verify failure**

```bash
cd /home/jul/P-core/.parallel/weather-learning/integration
PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py::test_build_learning_cycle_contract_is_paper_only_and_bounded
```

Expected: FAIL because `weather_pm.learning_cycle` does not exist.

**Step 3: Write minimal implementation**

```python
from __future__ import annotations

from pathlib import Path
from typing import Any


def build_learning_cycle_contract(
    *,
    run_id: str,
    output_dir: str | Path,
    max_accounts: int,
    trades_per_account: int,
    lookback_days: int,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "paper_only": True,
        "live_order_allowed": False,
        "no_real_order_placed": True,
        "output_dir": str(output_dir),
        "limits": {
            "max_accounts": int(max_accounts),
            "trades_per_account": int(trades_per_account),
            "lookback_days": int(lookback_days),
        },
    }
```

**Step 4: Run test to verify pass**

```bash
PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py::test_build_learning_cycle_contract_is_paper_only_and_bounded
```

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/weather_pm/learning_cycle.py python/tests/test_weather_learning_cycle.py
git commit -m "feat(weather): add paper-only learning cycle contract"
```

---

## Task 2: Ajouter la validation récursive de sécurité

**Objective:** Bloquer tout payload qui contient `live_order_allowed: true`, même imbriqué.

**Files:**
- Modify: `python/src/weather_pm/learning_cycle.py`
- Test: `python/tests/test_weather_learning_cycle.py`

**Step 1: Write failing test**

```python
def test_validate_learning_cycle_safety_rejects_nested_live_order_allowed_true():
    from weather_pm.learning_cycle import validate_learning_cycle_safety

    payload = {
        "paper_only": True,
        "live_order_allowed": False,
        "nested": {"orders": [{"live_order_allowed": True}]},
    }

    result = validate_learning_cycle_safety(payload)

    assert result["ok"] is False
    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False
    assert result["violations"] == ["nested.orders[0].live_order_allowed"]
```

**Step 2: Run RED**

```bash
PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py::test_validate_learning_cycle_safety_rejects_nested_live_order_allowed_true
```

Expected: FAIL because function missing.

**Step 3: Implement**

```python
def _find_live_order_allowed_true(value: Any, path: str = "") -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if key == "live_order_allowed" and child is True:
                violations.append(child_path)
            violations.extend(_find_live_order_allowed_true(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_find_live_order_allowed_true(child, f"{path}[{index}]"))
    return violations


def validate_learning_cycle_safety(payload: dict[str, Any]) -> dict[str, Any]:
    violations = _find_live_order_allowed_true(payload)
    top_paper = payload.get("paper_only") is True
    top_live_false = payload.get("live_order_allowed") is False
    return {
        "ok": top_paper and top_live_false and not violations,
        "paper_only": top_paper,
        "live_order_allowed": payload.get("live_order_allowed"),
        "violations": violations,
    }
```

**Step 4: Run tests**

```bash
PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/weather_pm/learning_cycle.py python/tests/test_weather_learning_cycle.py
git commit -m "feat(weather): enforce recursive learning cycle safety"
```

---

## Task 3: Ajouter le CLI `learning-cycle` en dry-run/no-network

**Objective:** Exposer un premier CLI qui écrit un contrat JSON sans lancer de backfill réseau.

**Files:**
- Modify: `python/src/weather_pm/cli.py`
- Modify: `python/src/weather_pm/learning_cycle.py`
- Test: `python/tests/test_weather_learning_cycle.py`

**Step 1: Write failing subprocess test**

```python
def test_cli_learning_cycle_dry_run_writes_contract(tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    project = Path(__file__).resolve().parents[1]
    output_dir = tmp_path / "cycle"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "weather_pm.cli",
            "learning-cycle",
            "--run-id",
            "learn-test",
            "--output-dir",
            str(output_dir),
            "--max-accounts",
            "5",
            "--trades-per-account",
            "10",
            "--lookback-days",
            "7",
            "--dry-run",
            "--no-network",
        ],
        cwd=project.parent,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout.splitlines()[-1])
    contract_path = Path(compact["artifacts"]["contract_json"])
    payload = json.loads(contract_path.read_text())
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    assert payload["limits"]["max_accounts"] == 5
```

**Step 2: Run RED**

```bash
PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py::test_cli_learning_cycle_dry_run_writes_contract
```

Expected: FAIL because CLI subcommand missing.

**Step 3: Implement minimal CLI**

Implementation should:
- add parser `learning-cycle`
- require `--output-dir`
- default `--run-id` to UTC stamp if omitted
- accept `--dry-run`, `--no-network`, `--max-accounts`, `--trades-per-account`, `--lookback-days`
- write `<output-dir>/learning_cycle_contract.json`
- print compact JSON with `ok`, `paper_only`, `live_order_allowed`, artifacts.

**Step 4: Run test**

```bash
PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py::test_cli_learning_cycle_dry_run_writes_contract
```

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/weather_pm/cli.py python/src/weather_pm/learning_cycle.py python/tests/test_weather_learning_cycle.py
git commit -m "feat(weather): expose paper-only learning cycle dry run"
```

---

# Phase 2 — Experiment ledger

## Task 4: Créer un ledger append-only d’expériences

**Objective:** Mémoriser les hypothèses testées et empêcher les répétitions inutiles.

**Files:**
- Modify: `python/src/weather_pm/learning_cycle.py`
- Test: `python/tests/test_weather_learning_cycle.py`

**Step 1: Write failing test**

```python
def test_append_learning_experiment_writes_jsonl_with_stable_hash(tmp_path):
    import json
    from weather_pm.learning_cycle import append_learning_experiment

    ledger = tmp_path / "learning_experiments.jsonl"
    experiment = {
        "profile_id": "coldmath_threshold_v1",
        "hypothesis": "threshold edge survives slippage",
        "market_id": "m-dallas-90",
        "inputs": {"price": 0.49, "model_probability": 0.57},
    }

    written = append_learning_experiment(ledger, experiment, run_id="learn-test")

    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["run_id"] == "learn-test"
    assert rows[0]["paper_only"] is True
    assert rows[0]["live_order_allowed"] is False
    assert rows[0]["experiment_hash"] == written["experiment_hash"]
    assert rows[0]["status"] == "awaiting_resolution"
```

**Step 2: Run RED**

```bash
PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py::test_append_learning_experiment_writes_jsonl_with_stable_hash
```

Expected: FAIL.

**Step 3: Implement**

Implementation details:
- canonical JSON hash of `profile_id`, `hypothesis`, `market_id`, `inputs`
- append JSON line with:
  - `run_id`
  - `experiment_hash`
  - `status: awaiting_resolution`
  - `paper_only: true`
  - `live_order_allowed: false`
  - original fields

**Step 4: Run tests**

```bash
PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/weather_pm/learning_cycle.py python/tests/test_weather_learning_cycle.py
git commit -m "feat(weather): add append-only learning experiment ledger"
```

---

## Task 5: Ajouter la déduplication par hash

**Objective:** Ne pas relancer une expérience déjà présente sauf `--force`.

**Files:**
- Modify: `python/src/weather_pm/learning_cycle.py`
- Test: `python/tests/test_weather_learning_cycle.py`

**Step 1: Write failing test**

```python
def test_append_learning_experiment_deduplicates_existing_hash(tmp_path):
    from weather_pm.learning_cycle import append_learning_experiment

    ledger = tmp_path / "learning_experiments.jsonl"
    experiment = {
        "profile_id": "p1",
        "hypothesis": "same",
        "market_id": "m1",
        "inputs": {"x": 1},
    }

    first = append_learning_experiment(ledger, experiment, run_id="r1")
    second = append_learning_experiment(ledger, experiment, run_id="r2")

    assert first["experiment_hash"] == second["experiment_hash"]
    assert second["deduplicated"] is True
    assert len(ledger.read_text().splitlines()) == 1
```

**Step 2: Run RED**

Expected: FAIL.

**Step 3: Implement**

- Read existing ledger if present.
- If same hash found and `force=False`, return existing row plus `deduplicated: true`.
- If `force=True`, append anyway with `deduplicated: false`.

**Step 4: Run test file**

```bash
PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/weather_pm/learning_cycle.py python/tests/test_weather_learning_cycle.py
git commit -m "feat(weather): deduplicate learning experiments"
```

---

# Phase 3 — Information scoring and backfill planner

## Task 6: Ajouter `score_high_information_case`

**Objective:** Prioriser automatiquement les cas les plus utiles à apprendre.

**Files:**
- Modify: `python/src/weather_pm/learning_cycle.py`
- Test: `python/tests/test_weather_learning_cycle.py`

**Step 1: Write failing test**

```python
def test_score_high_information_case_prioritizes_threshold_source_gap_and_disagreement():
    from weather_pm.learning_cycle import score_high_information_case

    case = {
        "market_id": "m1",
        "price": 0.49,
        "model_probability": 0.54,
        "learning_reason": "official_source_gap",
        "source_health": "published_empty",
        "profile_probabilities": {"p1": 0.40, "p2": 0.71},
        "depth_usd": 900,
    }

    scored = score_high_information_case(case)

    assert scored["market_id"] == "m1"
    assert scored["information_score"] > 0
    assert scored["components"]["near_threshold"] > 0
    assert scored["components"]["source_gap"] > 0
    assert scored["components"]["profile_disagreement"] > 0
    assert scored["paper_only"] is True
    assert scored["live_order_allowed"] is False
```

**Step 2: Run RED**

Expected: FAIL.

**Step 3: Implement scoring**

Suggested components:
- `near_threshold`: high if `abs(model_probability - price) <= 0.08` or price near `0.5`
- `source_gap`: high for `official_source_gap`, `published_empty`, fallback reason
- `profile_disagreement`: max-min profile probabilities
- `liquidity`: capped `depth_usd / 1000`
- `unresolved_uncertainty`: high if no resolved outcome

**Step 4: Run test**

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/weather_pm/learning_cycle.py python/tests/test_weather_learning_cycle.py
git commit -m "feat(weather): score high information learning cases"
```

---

## Task 7: Créer `build_learning_backfill_plan`

**Objective:** Transformer learning report + ledger en file de backfill/replay bornée.

**Files:**
- Modify: `python/src/weather_pm/learning_cycle.py`
- Test: `python/tests/test_weather_learning_cycle.py`

**Step 1: Write failing test**

```python
def test_build_learning_backfill_plan_prioritizes_new_high_score_cases(tmp_path):
    import json
    from weather_pm.learning_cycle import append_learning_experiment, build_learning_backfill_plan

    ledger = tmp_path / "learning_experiments.jsonl"
    append_learning_experiment(
        ledger,
        {"profile_id": "p-old", "hypothesis": "h", "market_id": "old", "inputs": {}},
        run_id="old-run",
    )
    report = {
        "paper_only": True,
        "live_order_allowed": False,
        "high_information_cases": [
            {"market_id": "old", "profile_id": "p-old", "learning_reason": "near_probability_threshold", "price": 0.5, "model_probability": 0.55},
            {"market_id": "new", "profile_id": "p-new", "learning_reason": "official_source_gap", "price": 0.49, "model_probability": 0.56},
        ],
    }

    plan = build_learning_backfill_plan(report, ledger_path=ledger, max_cases=5)

    assert plan["paper_only"] is True
    assert plan["live_order_allowed"] is False
    assert [case["market_id"] for case in plan["cases"]] == ["new"]
    assert plan["summary"]["deduplicated_cases"] == 1
```

**Step 2: Run RED**

Expected: FAIL.

**Step 3: Implement**

- Validate report safety.
- Score cases with `score_high_information_case`.
- Drop cases already in ledger.
- Sort desc by `information_score`.
- Limit to `max_cases`.
- Include safe replay commands but no live actions.

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/weather_pm/learning_cycle.py python/tests/test_weather_learning_cycle.py
git commit -m "feat(weather): plan automatic high information backfills"
```

---

# Phase 4 — Policy engine

## Task 8: Créer `build_learning_policy_actions`

**Objective:** Convertir learning report en actions paper-only: promote, reduce, collect more, backfill.

**Files:**
- Modify: `python/src/weather_pm/learning_cycle.py`
- Test: `python/tests/test_weather_learning_cycle.py`

**Step 1: Write failing test**

```python
def test_build_learning_policy_actions_maps_profile_actions_to_safe_policy():
    from weather_pm.learning_cycle import build_learning_policy_actions

    report = {
        "paper_only": True,
        "live_order_allowed": False,
        "profile_actions": [
            {"profile_id": "good", "action": "promote_candidate_paper_only", "resolved_orders": 12, "roi": 0.22, "winrate": 0.75},
            {"profile_id": "bad", "action": "disable_or_reduce_shadow_profile", "resolved_orders": 10, "roi": -0.18, "winrate": 0.2},
            {"profile_id": "thin", "action": "collect_more_resolutions", "resolved_orders": 2, "roi": 0.4, "winrate": 1.0},
        ],
    }

    policy = build_learning_policy_actions(report)

    assert policy["paper_only"] is True
    assert policy["live_order_allowed"] is False
    assert [a["type"] for a in policy["actions"]] == [
        "promote_shadow_profile_paper_only",
        "reduce_or_disable_shadow_profile",
        "request_resolution_backfill",
    ]
    assert all(a["live_order_allowed"] is False for a in policy["actions"])
```

**Step 2: Run RED**

Expected: FAIL.

**Step 3: Implement**

Policy rules:
- `promote_candidate_paper_only` -> `promote_shadow_profile_paper_only`
- `disable_or_reduce_shadow_profile` -> `reduce_or_disable_shadow_profile`
- `collect_more_resolutions` -> `request_resolution_backfill`
- ignore unknown actions but count them
- always add `paper_only`, `live_order_allowed=false`, `no_real_order_placed=true`

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/weather_pm/learning_cycle.py python/tests/test_weather_learning_cycle.py
git commit -m "feat(weather): derive safe learning policy actions"
```

---

## Task 9: Ajouter les seuils anti-faux-edge

**Objective:** Empêcher la promotion d’un profil avec trop peu d’échantillon ou une confiance faible.

**Files:**
- Modify: `python/src/weather_pm/learning_cycle.py`
- Test: `python/tests/test_weather_learning_cycle.py`

**Step 1: Write failing test**

```python
def test_learning_policy_blocks_promotion_when_sample_too_small():
    from weather_pm.learning_cycle import build_learning_policy_actions

    report = {
        "paper_only": True,
        "live_order_allowed": False,
        "profile_actions": [
            {"profile_id": "lucky", "action": "promote_candidate_paper_only", "resolved_orders": 2, "roi": 0.9, "winrate": 1.0},
        ],
    }

    policy = build_learning_policy_actions(report, min_resolved_for_promotion=8)

    assert policy["actions"][0]["type"] == "request_resolution_backfill"
    assert policy["actions"][0]["blocked_promotion_reason"] == "insufficient_resolved_sample"
```

**Step 2: Run RED**

Expected: FAIL.

**Step 3: Implement**

- Add parameters:
  - `min_resolved_for_promotion=8`
  - `min_roi_for_promotion=0.05`
  - `min_winrate_for_promotion=0.55`
- If profile asks promotion but fails thresholds, convert to `request_resolution_backfill` or `continue_shadow_observation`.

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/weather_pm/learning_cycle.py python/tests/test_weather_learning_cycle.py
git commit -m "feat(weather): guard learning promotion against false edge"
```

---

# Phase 5 — Full learning-cycle assembly

## Task 10: Build a pure `assemble_learning_cycle_result`

**Objective:** Combiner contract, learning report, policy, backfill plan, ledger writes en payload final.

**Files:**
- Modify: `python/src/weather_pm/learning_cycle.py`
- Test: `python/tests/test_weather_learning_cycle.py`

**Step 1: Write failing test**

```python
def test_assemble_learning_cycle_result_combines_report_policy_and_backfill(tmp_path):
    from weather_pm.learning_cycle import assemble_learning_cycle_result

    report = {
        "paper_only": True,
        "live_order_allowed": False,
        "profile_actions": [
            {"profile_id": "thin", "action": "collect_more_resolutions", "resolved_orders": 1, "roi": 0.1, "winrate": 1.0}
        ],
        "high_information_cases": [
            {"market_id": "m1", "profile_id": "thin", "learning_reason": "near_probability_threshold", "price": 0.49, "model_probability": 0.54}
        ],
    }

    result = assemble_learning_cycle_result(
        run_id="learn-test",
        output_dir=tmp_path,
        learning_report=report,
        max_accounts=80,
        trades_per_account=200,
        lookback_days=30,
    )

    assert result["ok"] is True
    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False
    assert result["policy"]["actions"]
    assert result["backfill_plan"]["cases"]
    assert result["safety"]["ok"] is True
```

**Step 2: Run RED**

Expected: FAIL.

**Step 3: Implement**

- Build contract.
- Build policy.
- Build backfill plan.
- Validate combined payload safety.
- Return compact summary.

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/weather_pm/learning_cycle.py python/tests/test_weather_learning_cycle.py
git commit -m "feat(weather): assemble automatic learning cycle result"
```

---

## Task 11: CLI writes full cycle artifacts from existing report inputs

**Objective:** Permettre au cron de lancer un cycle automatique à partir du dernier learning report safe.

**Files:**
- Modify: `python/src/weather_pm/cli.py`
- Modify: `python/src/weather_pm/learning_cycle.py`
- Test: `python/tests/test_weather_learning_cycle.py`

**Step 1: Write failing subprocess test**

```python
def test_cli_learning_cycle_from_learning_report_writes_policy_and_backfill(tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    project = Path(__file__).resolve().parents[1]
    report = tmp_path / "learning_report.json"
    report.write_text(json.dumps({
        "paper_only": True,
        "live_order_allowed": False,
        "profile_actions": [
            {"profile_id": "thin", "action": "collect_more_resolutions", "resolved_orders": 1, "roi": 0.1, "winrate": 1.0}
        ],
        "high_information_cases": [
            {"market_id": "m1", "profile_id": "thin", "learning_reason": "near_probability_threshold", "price": 0.49, "model_probability": 0.54}
        ],
    }))
    out = tmp_path / "cycle"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project / "src")

    result = subprocess.run(
        [
            sys.executable, "-m", "weather_pm.cli", "learning-cycle",
            "--run-id", "learn-report-test",
            "--learning-report-json", str(report),
            "--output-dir", str(out),
            "--no-network",
        ],
        cwd=project.parent,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    compact = json.loads(result.stdout.splitlines()[-1])
    assert compact["ok"] is True
    cycle_json = Path(compact["artifacts"]["cycle_json"])
    payload = json.loads(cycle_json.read_text())
    assert payload["policy"]["actions"]
    assert payload["backfill_plan"]["cases"]
```

**Step 2: Run RED**

Expected: FAIL.

**Step 3: Implement**

CLI should write:
- `learning_cycle_contract.json`
- `learning_cycle_result.json`
- `learning_policy_actions.json`
- `learning_backfill_plan.json`
- `learning_cycle_summary.md`
- `learning_experiments.jsonl`

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/weather_pm/cli.py python/src/weather_pm/learning_cycle.py python/tests/test_weather_learning_cycle.py
git commit -m "feat(weather): write automatic learning cycle artifacts"
```

---

# Phase 6 — Daily operator integration

## Task 12: Daily operator discovers latest safe learning cycle

**Objective:** Le daily operator doit afficher le dernier cycle automatique si présent.

**Files:**
- Modify: `scripts/weather_operator_daily.py`
- Test: `python/tests/test_weather_operator_daily.py`

**Step 1: Write failing test**

```python
def test_latest_safe_learning_cycle_ignores_unsafe_nested_live_payload(tmp_path):
    import json
    from scripts.weather_operator_daily import latest_safe_learning_cycle

    root = tmp_path / "data" / "polymarket"
    older = root / "learning-cycles" / "old" / "learning_cycle_result.json"
    older.parent.mkdir(parents=True)
    older.write_text(json.dumps({"paper_only": True, "live_order_allowed": False, "policy": {"actions": []}}))
    newer = root / "learning-cycles" / "new" / "learning_cycle_result.json"
    newer.parent.mkdir(parents=True)
    newer.write_text(json.dumps({"paper_only": True, "live_order_allowed": False, "nested": {"live_order_allowed": True}}))

    found = latest_safe_learning_cycle(root)

    assert found is not None
    path, payload = found
    assert path == older
    assert payload["paper_only"] is True
```

**Step 2: Run RED**

```bash
PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_operator_daily.py::test_latest_safe_learning_cycle_ignores_unsafe_nested_live_payload
```

Expected: FAIL.

**Step 3: Implement**

- Add helper `latest_safe_learning_cycle(data_root=DATA)` using existing safety style from daily operator.
- Reuse recursive safety scan.
- Return latest safe `learning-cycles/*/learning_cycle_result.json`.

**Step 4: Run test**

Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/weather_operator_daily.py python/tests/test_weather_operator_daily.py
git commit -m "feat(weather): discover safe automatic learning cycles in daily operator"
```

---

## Task 13: Render compact learning cycle summary in daily Markdown

**Objective:** Le daily report doit répondre clairement: quoi appris, quoi faire ensuite.

**Files:**
- Modify: `scripts/weather_operator_daily.py`
- Test: `python/tests/test_weather_operator_daily.py`

**Step 1: Write failing test**

```python
def test_render_daily_markdown_includes_learning_cycle_summary(tmp_path):
    from scripts.weather_operator_daily import render_learning_cycle_markdown

    payload = {
        "run_id": "learn-test",
        "paper_only": True,
        "live_order_allowed": False,
        "policy": {"actions": [{"type": "request_resolution_backfill"}]},
        "backfill_plan": {"cases": [{"market_id": "m1", "information_score": 2.5}]},
        "summary": {"profile_actions": 1, "high_information_cases": 1},
    }

    md = render_learning_cycle_markdown(payload)

    assert "## Automatic learning cycle" in md
    assert "paper_only=true" in md
    assert "live_order_allowed=false" in md
    assert "request_resolution_backfill" in md
    assert "m1" in md
```

**Step 2: Run RED**

Expected: FAIL.

**Step 3: Implement**

Render compact section:
- run id
- safety booleans
- counts:
  - policy actions
  - backfill cases
  - promoted/reduced/needs-backfill
- top 5 backfill cases
- never include live order suggestion.

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add scripts/weather_operator_daily.py python/tests/test_weather_operator_daily.py
git commit -m "feat(weather): render automatic learning cycle summary"
```

---

# Phase 7 — Backfill execution automation, bounded

## Task 14: Planner chooses accounts from followlist and report

**Objective:** Préparer automatiquement les comptes à backfill sans hardcoder CPR.

**Files:**
- Modify: `python/src/weather_pm/learning_cycle.py`
- Test: `python/tests/test_weather_learning_cycle.py`

**Step 1: Write failing test**

```python
def test_select_learning_accounts_prioritizes_profiles_needing_resolution():
    from weather_pm.learning_cycle import select_learning_accounts

    followlist = [
        {"handle": "ColdMath", "wallet": "0xCold", "score": "0.9"},
        {"handle": "Railbird", "wallet": "0xRail", "score": "0.7"},
        {"handle": "Tiny", "wallet": "0xTiny", "score": "0.1"},
    ]
    report = {
        "profile_actions": [
            {"profile_id": "ColdMath", "action": "collect_more_resolutions"},
            {"profile_id": "Railbird", "action": "promote_candidate_paper_only"},
        ]
    }

    selected = select_learning_accounts(followlist, report, max_accounts=2)

    assert [row["handle"] for row in selected] == ["ColdMath", "Railbird"]
```

**Step 2: Run RED**

Expected: FAIL.

**Step 3: Implement**

- Score account rows by:
  - profile appears in `collect_more_resolutions`
  - profile appears in promote/reduce actions
  - numeric existing score if present
- Limit to `max_accounts`.

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/weather_pm/learning_cycle.py python/tests/test_weather_learning_cycle.py
git commit -m "feat(weather): select accounts for automatic learning backfill"
```

---

## Task 15: Add `--plan-only` backfill commands to learning-cycle output

**Objective:** Le cycle doit produire les commandes exactes à lancer pour backfill, sans réseau en test.

**Files:**
- Modify: `python/src/weather_pm/learning_cycle.py`
- Test: `python/tests/test_weather_learning_cycle.py`

**Step 1: Write failing test**

```python
def test_learning_cycle_plan_includes_bounded_backfill_commands(tmp_path):
    from weather_pm.learning_cycle import build_bounded_backfill_commands

    commands = build_bounded_backfill_commands(
        output_dir=tmp_path,
        followlist_csv="data/polymarket/weather_accounts_followlist_20260425.csv",
        max_accounts=10,
        trades_per_account=100,
    )

    joined = "\n".join(commands)
    assert "backfill-account-trades" in joined
    assert "--limit-accounts 10" in joined
    assert "--trades-per-account 100" in joined
    assert "paper" in joined.lower() or "shadow" in joined.lower()
```

**Step 2: Run RED**

Expected: FAIL.

**Step 3: Implement**

Commands should include existing CLI surfaces:
- `backfill-account-trades`
- `import-account-trades`
- `shadow-profile-report`
- `shadow-paper-runner`
- `shadow-profile-evaluator`
- `shadow-profile-learning-report`

They are plan strings, not executed by this helper.

**Step 4: Run tests**

Expected: PASS.

**Step 5: Commit**

```bash
git add python/src/weather_pm/learning_cycle.py python/tests/test_weather_learning_cycle.py
git commit -m "feat(weather): emit bounded learning backfill commands"
```

---

# Phase 8 — Cron productionization

## Task 16: Update cron prompt to run learning-cycle before daily operator

**Objective:** Le cron 30 min doit produire un cycle léger avant le daily.

**Files:**
- No repo code required if using Hermes cron update.
- Optional doc: `docs/ops/weather_learning_cycle_cron.md`

**Step 1: Verify current cron**

```bash
# via Hermes cronjob(action="list")
```

Expected:
- `312c3b855271` active
- `deliver=local`
- workdir clean

**Step 2: Update prompt**

Cron prompt should run:

```bash
cd /home/jul/P-core/.parallel/weather-learning/integration
RUN_ID="learn-$(date -u +%Y%m%dT%H%M%SZ)"
OUT="data/polymarket/learning-cycles/$RUN_ID"
LATEST_REPORT=$(find data/polymarket -path '*shadow_profile_learning_report*.json' -type f -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)
PYTHONPATH=python/src python3 -m weather_pm.cli learning-cycle \
  --run-id "$RUN_ID" \
  --learning-report-json "$LATEST_REPORT" \
  --output-dir "$OUT" \
  --no-network
PYTHONPATH=python/src python3 scripts/weather_operator_daily.py
```

**Step 3: Safety verification in prompt**

Require:
- final learning-cycle JSON parses
- daily JSON parses
- both have `paper_only=true`
- both have `live_order_allowed=false`
- daily has `no_real_order_placed=true`
- recursive scan no `live_order_allowed=true`

**Step 4: Keep heavy backfill separate**

Do not run network-heavy backfill every 30 min. Create separate local cron later:
- schedule: `0 */12 * * *` or `every 12h`
- deliver: `local`
- bounded max accounts/trades

---

# Phase 9 — Heavy learning backfill, once/twice daily

## Task 17: Create heavy backfill cron prompt after code is merged

**Objective:** Nourrir l’apprentissage automatiquement avec plus de matière que CPR.

**Prompt shape:**

```text
Run P-core weather learning heavy backfill in /home/jul/P-core/.parallel/weather-learning/integration.
Strictly paper-only. Use max_accounts=80, trades_per_account=200, lookback_days=30.
Use weather_pm.cli learning-cycle to build plan, then execute bounded backfill commands only if safety contract is valid.
Write all outputs under data/polymarket/learning-cycles/<run_id>/heavy-backfill.
Never place live orders.
Deliver local only.
```

**Verification:**
- `paper_only=true`
- `live_order_allowed=false`
- `no_real_order_placed=true`
- no nested `live_order_allowed=true`
- output has nonzero `profile_actions` or nonzero `high_information_cases`, otherwise report `insufficient_signal` not failure.

---

# Final verification bundle

Run after all phases in integration worktree:

```bash
cd /home/jul/P-core/.parallel/weather-learning/integration
PYTHONPATH=python/src python3 -m pytest -q \
  python/tests/test_weather_learning_cycle.py \
  python/tests/test_weather_shadow_paper_runner.py \
  python/tests/test_weather_operator_daily.py

PYTHONPATH=python/src python3 -m py_compile \
  python/src/weather_pm/learning_cycle.py \
  python/src/weather_pm/cli.py \
  python/src/weather_pm/shadow_paper_runner.py \
  scripts/weather_operator_daily.py

RUN_ID="learn-smoke-$(date -u +%Y%m%dT%H%M%SZ)"
PYTHONPATH=python/src python3 -m weather_pm.cli learning-cycle \
  --run-id "$RUN_ID" \
  --learning-report-json data/polymarket/account-analysis/targeted-cpr-20260430T095132Z/shadow_profile_learning_report_coldmath_poligarch_railbird.json \
  --output-dir "data/polymarket/learning-cycles/$RUN_ID" \
  --no-network

PYTHONPATH=python/src python3 scripts/weather_operator_daily.py --skip-cron-monitor
```

Then verify with Python:

```python
import json
from pathlib import Path

latest = max(Path('data/polymarket/operator-daily').glob('weather_operator_daily_*.json'), key=lambda p: p.stat().st_mtime)
payload = json.loads(latest.read_text())
assert payload['paper_only'] is True
assert payload['live_order_allowed'] is False
assert payload['no_real_order_placed'] is True

violations = []
def walk(x, path=''):
    if isinstance(x, dict):
        for k, v in x.items():
            p = f'{path}.{k}' if path else k
            if k == 'live_order_allowed' and v is True:
                violations.append(p)
            walk(v, p)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            walk(v, f'{path}[{i}]')
walk(payload)
assert not violations, violations
```

---

# Commit/push strategy

Because `/home/jul/P-core` primary checkout has unrelated WIP, implement in the clean worktree:

```bash
cd /home/jul/P-core/.parallel/weather-learning/integration
git status --short
git fetch origin main
git rebase origin/main
```

For each phase:

```bash
git diff --check
git status --short
git add <intended files only>
git diff --cached --name-only
git commit -m "feat(weather): ..."
```

Before push:

```bash
PYTHONPATH=python/src python3 -m pytest -q python/tests/test_weather_learning_cycle.py python/tests/test_weather_operator_daily.py python/tests/test_weather_shadow_paper_runner.py
git fetch origin main
git rebase origin/main
git push origin HEAD:main
git rev-list --left-right --count origin/main...HEAD
```

Expected after push: `0 0`.

---

# Subagent split recommendation

Use 4 parallel subagents after this plan is accepted:

1. **orchestrator-core**
   - Tasks 1, 2, 3, 10, 11
   - Owns `python/src/weather_pm/learning_cycle.py`, CLI `learning-cycle`, core tests.

2. **experiment-ledger-policy**
   - Tasks 4, 5, 8, 9
   - Owns ledger, dedupe, policy actions, anti-false-edge thresholds.

3. **info-backfill-planner**
   - Tasks 6, 7, 14, 15
   - Owns information scoring, backfill planning, account selection, command generation.

4. **daily-cron-integration**
   - Tasks 12, 13, 16, 17
   - Owns daily operator rendering, latest safe cycle discovery, cron prompt updates.

Integration controller should cherry-pick sequentially into a fifth clean worktree, resolve overlaps in `learning_cycle.py` and `test_weather_learning_cycle.py`, then run the final verification bundle.
