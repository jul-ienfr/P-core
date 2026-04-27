# prediction_core

Cœur cible de la stack prediction.

## Rôle

`prediction_core/` héberge la nouvelle architecture convergente sans casser `subprojects/prediction`.

- `python/` : research, replay, paper, calibration, analytics, evaluation, plus bootstrap service HTTP local minimal
- `rust/` : moteur live canonique
- `contracts/` : formats d’échange communs entre moteurs et cockpit

## Principe de migration

1. construire ici les composants canoniques
2. produire des artefacts stables (Postgres + JSON)
3. faire consommer ces artefacts par `subprojects/prediction`
4. déclasser progressivement les bridges live redondants

## Panoptique migration

The Panoptique migration is tracked in `docs/plans/2026-04-26-panoptique-migration-plan.md`, with strategy doctrine in `docs/strategy/PANOPTIQUE_STRATEGY.md`. It is paper-only/read-only unless a separate future approval explicitly changes that boundary.

## Root and runtime checks

`/home/jul/P-core` is the canonical active root. Older P-core related roots were archived at `/home/jul/_archive_consolidated_pcore_roots_20260427`.

When local `cargo` is unavailable, Rust runtime checks can be run via Docker with `rust/scripts/check_pm_storage_runtime.sh`.
