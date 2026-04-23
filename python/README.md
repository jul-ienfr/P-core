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
cd /home/jul/swarm/prediction_core/python
PYTHONPATH=src pytest -q
python3 -m weather_pm.cli --help
```

## Suite prévue

- stabiliser la coexistence `prediction_core.*` + `weather_pm.*`
- converger ensuite vers un namespace Python plus unifié si utile
- ne pas déplacer `prediction_core/rust` pendant cette phase
