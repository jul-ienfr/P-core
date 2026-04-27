"""Prediction Core operational state.

Revision ID: 0003_operational_state
Revises: 0002_storage_optimization
Create Date: 2026-04-27
"""
from __future__ import annotations

from alembic import op

revision = "0003_operational_state"
down_revision = "0002_storage_optimization"
branch_labels = None
depends_on = None

OPERATIONAL_SQL = """
CREATE TABLE IF NOT EXISTS storage_artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT,
    artifact_type TEXT NOT NULL,
    source TEXT NOT NULL,
    uri TEXT NOT NULL,
    content_type TEXT,
    sha256 TEXT,
    size_bytes BIGINT,
    row_count BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    paper_only BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS prediction_runs (
    run_id TEXT PRIMARY KEY,
    strategy_id TEXT,
    profile_id TEXT,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    artifact_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    paper_only BOOLEAN NOT NULL DEFAULT TRUE,
    live_order_allowed BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS execution_idempotency_keys (
    key TEXT PRIMARY KEY,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id TEXT,
    market_id TEXT,
    token_id TEXT,
    mode TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    paper_only BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS execution_audit_events (
    execution_event_id TEXT NOT NULL,
    run_id TEXT,
    market_id TEXT,
    token_id TEXT,
    event_type TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    paper_only BOOLEAN NOT NULL DEFAULT TRUE,
    live_order_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (execution_event_id, recorded_at)
);

SELECT create_hypertable('execution_audit_events', 'recorded_at', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS job_runs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    input JSONB NOT NULL DEFAULT '{}'::jsonb,
    output JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT
);
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_prediction_runs_started_at ON prediction_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_prediction_runs_status_mode ON prediction_runs (status, mode);
CREATE INDEX IF NOT EXISTS idx_execution_audit_events_recorded_event_type ON execution_audit_events (recorded_at DESC, event_type);
CREATE INDEX IF NOT EXISTS idx_execution_audit_events_run_recorded ON execution_audit_events (run_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_storage_artifacts_run_created ON storage_artifacts (run_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_storage_artifacts_type_created ON storage_artifacts (artifact_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_runs_status_type_created ON job_runs (status, job_type, created_at);
"""


def upgrade() -> None:
    op.execute(OPERATIONAL_SQL)
    op.execute(INDEX_SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS job_runs")
    op.execute("DROP TABLE IF EXISTS execution_audit_events")
    op.execute("DROP TABLE IF EXISTS execution_idempotency_keys")
    op.execute("DROP TABLE IF EXISTS prediction_runs")
    op.execute("DROP TABLE IF EXISTS storage_artifacts")
