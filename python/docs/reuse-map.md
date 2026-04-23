# prediction_core Python — reuse map

## Objectif

Préparer la Phase 2 sans casser l’existant : on pose les domaines cibles et on documente quoi extraire depuis le Python actuel.

## Domaines cibles

- `replay/`
- `paper/`
- `calibration/`
- `analytics/`
- `evaluation/`

## Principes d'exports Phase 2

Les packages `replay` et `paper` portent ici une première extraction canonique minimale ; `calibration`, `analytics` et `evaluation` restent pour l'instant des frontières de modules sans API stable.

Pendant cette extraction :
- on garde des `__init__.py` minimalistes ;
- on prépare des imports internes futurs sous `src/prediction_core/<domaine>/` ;
- on limite `replay` et `paper` à des briques minimales découplées du legacy ;
- on documente les frontières minimales avant de déplacer du code métier.

## Réutilisation prioritaire depuis l’existant

### replay
Source principale : `prediction_markets/replay.py`

À réutiliser en priorité :
- logique de comparaison replay/original
- signatures d’execution projection
- génération de rapports de replay

### paper
Source principale : `prediction_markets/paper_trading.py`

À réutiliser en priorité :
- modèles `PaperTradeFill` / `PaperTradeSimulation`
- logique de fill simulé
- projection de paper records

### calibration
Source principale : `prediction_markets/calibration_lab.py`

À réutiliser en priorité :
- scoring calibration
- agrégations de qualité
- production de snapshots calibration

Frontière minimale à préserver :
- `src/prediction_core/calibration/` doit rester le point d'entrée unique pour les futurs utilitaires de scoring et snapshots ;
- les artefacts de calibration doivent rester découplés de l'exécution replay/paper.

Hors frontière pour cette extraction :
- aucun port du moteur replay ;
- aucune logique de fill ou d'exécution simulée.

### analytics
Source candidate : `prediction_markets/research.py`

À réutiliser en priorité :
- normalisation de findings
- scoring/pondération des sources
- structuration des evidence packets

Frontière minimale à préserver :
- `src/prediction_core/analytics/` doit héberger les transformations d'analyse sans imposer de dépendance au pipeline d'exécution ;
- les structures produites doivent rester réutilisables par d'autres domaines Python.

Hors frontière pour cette extraction :
- aucune orchestration live ;
- aucune mutation des flows replay/paper.

### evaluation
Source principale : `prediction_markets/forecast_evaluation.py`

À réutiliser en priorité :
- Brier/log loss
- ECE buckets
- benchmarks de comparaison
- rapports category/horizon

Frontière minimale à préserver :
- `src/prediction_core/evaluation/` doit rester la frontière unique pour les métriques de qualité prédictive ;
- les calculs doivent rester indépendants des modules legacy d'exécution.

Hors frontière pour cette extraction :
- aucun couplage direct avec `paper_trading.py` ;
- aucun déplacement de logique legacy depuis `replay.py`.

## Règle de migration

On commence par déplacer les frontières logiques et la documentation de réutilisation ; le port de code viendra ensuite domaine par domaine avec TDD ciblé.