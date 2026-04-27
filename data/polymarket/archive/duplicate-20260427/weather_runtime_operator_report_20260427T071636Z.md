# Météo Polymarket — refresh paper-only 20260427T071636Z

## Verdict opérateur
- Statut: **HOLD**
- Paper-only: **oui** — aucun ordre réel.
- Raison: aucun candidat ne franchit min_edge=0.02; pas d’ajout
- Données: 3 snapshots live Gamma/CLOB rejoués localement, 3 abonnements.
- Décisions: 3 HOLD, 0 signal paper, 0 snapshot manquant.

## Watchlist
| Market | Outcome | Bid | Ask | Proba modèle | Edge | Action |
|---|---:|---:|---:|---:|---:|---|
| 2091681 — Will the highest temperature in Hong Kong be 19°C or below on April 29? | Yes | None | 0.92 | 0.052 | -0.868 | HOLD |
| 2091691 — Will the highest temperature in Hong Kong be 29°C or higher on April 29? | Yes | 0.007 | 0.94 | 0.07 | -0.87 | HOLD |
| 2082488 — Will the highest temperature in Hong Kong be 21°C or below on April 28? | Yes | None | 0.919 | 0.051 | -0.868 | HOLD |

## Artefacts
- markets_json: `/home/jul/prediction_core/data/polymarket/weather_runtime_live_markets_20260427T071636Z.json`
- events_jsonl: `/home/jul/prediction_core/data/polymarket/weather_runtime_live_events_20260427T071636Z.jsonl`
- probabilities_json: `/home/jul/prediction_core/data/polymarket/weather_runtime_live_probabilities_20260427T071636Z.json`
- runtime_json: `/home/jul/prediction_core/data/polymarket/weather_runtime_dryrun_20260427T071636Z.json`
- audit_jsonl: `/home/jul/prediction_core/data/polymarket/runtime_audit/weather_runtime_audit_20260427T071636Z.jsonl`
- operator_report_json: `/home/jul/prediction_core/data/polymarket/weather_runtime_operator_report_20260427T071636Z.json`
- operator_report_md: `/home/jul/prediction_core/data/polymarket/weather_runtime_operator_report_20260427T071636Z.md`
