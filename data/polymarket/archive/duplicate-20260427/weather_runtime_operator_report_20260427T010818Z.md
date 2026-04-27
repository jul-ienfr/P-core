# Météo Polymarket — runtime dry-run 20260427T010818Z

## Verdict opérateur

- Statut: **HOLD**
- Paper-only: **oui** — aucun ordre réel, aucun ordre dry-run soumis.
- Données: 3 snapshots live Gamma/CLOB rejoués localement, 3 abonnements.
- Décisions: 3 HOLD, 0 signal paper, 0 snapshot manquant.

## Watchlist

| Market | Outcome | Bid | Ask | Proba modèle | Edge | Action |
|---|---:|---:|---:|---:|---:|---|
| 2082488 — Will the highest temperature in Hong Kong be 21°C or below on April 28? | Yes | None | 0.92 | 0.051 | -0.869 | HOLD |
| 2082498 — Will the highest temperature in Hong Kong be 31°C or higher on April 28? | Yes | 0.01 | 0.92 | 0.061 | -0.859 | HOLD |
| 2074460 — Will the highest temperature in Hong Kong be 20°C or below on April 27? | Yes | None | 0.94 | 0.051 | -0.889 | HOLD |

## Artefacts

- markets_json: `/home/jul/prediction_core/data/polymarket/weather_runtime_live_markets_20260427T010818Z.json`
- events_jsonl: `/home/jul/prediction_core/data/polymarket/weather_runtime_live_events_20260427T010818Z.jsonl`
- probabilities_json: `/home/jul/prediction_core/data/polymarket/weather_runtime_live_probabilities_20260427T010818Z.json`
- runtime_json: `/home/jul/prediction_core/data/polymarket/weather_runtime_dryrun_20260427T010818Z.json`
- audit_jsonl: `/home/jul/prediction_core/data/polymarket/runtime_audit/weather_runtime_audit_20260427T010818Z.jsonl`
