# Panoptique data contracts

Phase 1 contracts live in `python/src/panoptique/contracts.py` and serialize to JSON-safe dictionaries with `schema_version`.

## Contracts and table mapping

- `Market` -> `markets`
- `OrderbookSnapshot` -> `orderbook_snapshots`
- `TradeEvent` -> `trade_events`
- `ShadowPrediction` -> `shadow_predictions`
- `CrowdFlowObservation` -> `crowd_flow_observations`
- `IngestionHealth` -> `ingestion_health`
- `ArtifactMetadata` -> audit/replay metadata for JSONL/Parquet artifacts

Repository writes should flow through `panoptique.repositories` rather than ad-hoc table writes. Raw JSONL artifacts are written through `panoptique.artifacts` for replayable audit history.
