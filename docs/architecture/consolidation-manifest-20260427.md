# P-core consolidation manifest — 2026-04-27

Canonical root: `/home/jul/P-core`

This manifest records the non-destructive consolidation of P-core / prediction_core-related content from external roots into the canonical repository.

## Imported source files

| Source | Destination | Action | Reason |
|---|---|---|---|
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/python/src/weather_pm/archetype_backtest.py` | `python/src/weather_pm/archetype_backtest.py` | imported | Unique weather strategy module |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/python/src/weather_pm/threshold_watcher.py` | `python/src/weather_pm/threshold_watcher.py` | imported | Unique weather strategy module |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/python/src/weather_pm/strategy_profiles.py` | `python/src/weather_pm/strategy_profiles.py` | imported | Unique weather strategy module |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/python/src/weather_pm/portfolio_risk.py` | `python/src/weather_pm/portfolio_risk.py` | imported | Unique risk module |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/python/src/weather_pm/production_operator.py` | `python/src/weather_pm/production_operator.py` | imported | Unique production operator module |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/python/src/weather_pm/consensus_tracker.py` | `python/src/weather_pm/consensus_tracker.py` | imported | Unique consensus module |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/python/src/weather_pm/surface_inconsistency.py` | `python/src/weather_pm/surface_inconsistency.py` | imported | Unique surface analysis module |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/python/src/prediction_core/paper/ledger.py` | `python/src/prediction_core/paper/ledger.py` | imported | Unique paper ledger module |
| `_archive_prediction_core_duplicate_20260427/python/src/prediction_core/strategies/weather_bookmaker.py` | `python/src/prediction_core/strategies/weather_bookmaker.py` | imported | Unique strategy module |
| `_archive_prediction_core_duplicate_20260427/python/src/weather_pm/paper_report.py` | `python/src/weather_pm/paper_report.py` | imported | Unique paper reporting module |
| `_archive_prediction_core_duplicate_20260427/python/src/weather_pm/polymarket_settlement.py` | `python/src/weather_pm/polymarket_settlement.py` | imported | Unique settlement resolver module |

## Imported tests

| Source | Destination | Action | Reason |
|---|---|---|---|
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/python/tests/test_paper_ledger.py` | `python/tests/test_paper_ledger.py` | imported | Coverage for imported paper ledger |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/python/tests/test_weather_production_contracts.py` | `python/tests/test_weather_production_contracts.py` | imported | Coverage for weather production contracts |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/python/tests/test_weather_strategy_profiles.py` | `python/tests/test_weather_strategy_profiles.py` | imported | Coverage for strategy profiles |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/python/tests/test_weather_archetype_backtest.py` | `python/tests/test_weather_archetype_backtest.py` | imported | Coverage for archetype backtest |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/python/tests/test_weather_production_operator_report.py` | `python/tests/test_weather_production_operator_report.py` | imported | Coverage for production operator |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/python/tests/test_weather_portfolio_risk.py` | `python/tests/test_weather_portfolio_risk.py` | imported | Coverage for portfolio risk |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/python/tests/fixtures/polymarket_weather_city_date_surface.json` | `python/tests/fixtures/polymarket_weather_city_date_surface.json` | imported | Fixture for imported tests |
| `_archive_prediction_core_duplicate_20260427/python/tests/test_polymarket_settlement_resolver.py` | `python/tests/test_polymarket_settlement_resolver.py` | imported | Coverage for settlement resolver |
| `_archive_prediction_core_duplicate_20260427/python/tests/test_strategy_weather_bookmaker.py` | `python/tests/test_strategy_weather_bookmaker.py` | imported | Coverage for weather bookmaker strategy |
| `_archive_prediction_core_duplicate_20260427/python/tests/test_weather_paper_report.py` | `python/tests/test_weather_paper_report.py` | imported | Coverage for paper report |
| `/home/jul/swarm/tests/test_prediction_core_*.py` | `python/tests/contracts/` | imported and path-adjusted | Historical prediction_core contract tests |

## Imported docs

| Source | Destination | Action | Reason |
|---|---|---|---|
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/docs/p-core-strategy-boundaries.md` | `docs/strategy/p-core-strategy-boundaries.md` | imported | Active strategy documentation |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/docs/plans/2026-04-27-polymarket-weather-strategy-profiles.md` | `docs/plans/2026-04-27-polymarket-weather-strategy-profiles.md` | imported | Active planning documentation |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/docs/polymarket/*.md` | `docs/polymarket/` | imported | Active Polymarket/weather documentation |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/docs/polymarket/generated/*.md` | `docs/polymarket/generated/` | imported | Generated weather strategy reference |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/docs/architecture/*` | `docs/legacy-imports/architecture-audit-20260427/` | imported | Historical audit evidence, not active architecture |

## Imported data

| Source | Destination | Action | Reason |
|---|---|---|---|
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/data/polymarket/account-analysis/*` | `data/polymarket/account-analysis/` | imported | Unique account-analysis artifacts |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/data/polymarket/latest/*` | `data/polymarket/latest/` | imported | Latest report pointers and outputs |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/data/polymarket/reports/*/.gitkeep` | `data/polymarket/reports/` | imported | Preserve intended report layout |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/data/polymarket/scans/.gitkeep` | `data/polymarket/scans/.gitkeep` | imported | Preserve intended data layout |
| `_archive_P-core_dirty_state_before_correction_20260427T120939Z/untracked-files/data/polymarket/ledgers/.gitkeep` | `data/polymarket/ledgers/.gitkeep` | imported | Preserve intended data layout |
| `_archive_prediction_core_duplicate_20260427/data/polymarket/*` | `data/polymarket/archive/duplicate-20260427/` | imported | Unique duplicate-archive runtime artifacts kept out of active data root |

## Conflict-retained files

Canonical files were not overwritten. Divergent external versions were retained under `docs/legacy-imports/conflicts/` for review.

| Source root | Destination | Action | Reason |
|---|---|---|---|
| `P-core-clickhouse-grafana` | `docs/legacy-imports/conflicts/P-core-clickhouse-grafana/` | conflict-retained | Same relative paths differed from canonical P-core |
| `_archive_prediction_core_duplicate_20260427` | `docs/legacy-imports/conflicts/_archive_prediction_core_duplicate_20260427/` | conflict-retained | Same relative paths differed from canonical P-core |

## Excluded content

The consolidation intentionally excluded `.git/`, `.claude/`, `.pytest_cache/`, `__pycache__/`, `*.pyc`, Rust `target/`, and generated caches.

## Cleanup status

No external P-core-related root was deleted or moved during consolidation. These paths are now candidates for later archival or removal after validation:

- `/home/jul/P-core-clickhouse-grafana`
- `/home/jul/_archive_prediction_core_duplicate_20260427`
- `/home/jul/_archive_P-core_dirty_state_before_correction_20260427T120939Z`
- `/home/jul/swarm/prediction_core`
- `/home/jul/swarm/tests/test_prediction_core_*.py`
