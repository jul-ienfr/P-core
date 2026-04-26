# Panoptique local storage

This directory defines the Phase 1 local storage foundation for Panoptique.

## Boot local services

```bash
cd /home/jul/prediction_core/infra/panoptique
cp .env.example .env
docker compose --env-file .env up -d
```

Services bind to `127.0.0.1` by default:

- PostgreSQL 16 + TimescaleDB on `localhost:5432`
- Redis on `localhost:6379`

Validate configuration without starting containers:

```bash
docker compose --env-file .env.example config
```

## Migrations

Alembic files live under `/home/jul/prediction_core/migrations/panoptique/alembic`.
The first migration enables the TimescaleDB extension, creates core relational tables, and converts timestamped fact tables into hypertables.

## Redis role

Redis is an ephemeral live cache only. It is never the source of truth and should be safe to flush during local development.

## JSONL/Parquet audit/replay role

PostgreSQL/TimescaleDB is the primary queryable store. Raw JSONL and later Parquet archives under `data/panoptique/` remain mandatory audit/replay artifacts for external payloads, deterministic replay, and offline analysis with tools such as DuckDB.

## Secrets and safety

`.env.example` contains non-secret local defaults only. Do not add wallet credentials, private keys, real-money trading credentials, or production secrets. Phase 1 introduces storage and paper/read-only data contracts only; it does not place orders.
