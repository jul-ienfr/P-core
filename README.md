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
