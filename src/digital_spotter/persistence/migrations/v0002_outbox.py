"""Migration 0002: analysis, model, audit, and durable outbox records."""

from __future__ import annotations

import sqlite3

from digital_spotter.persistence.schema import Migration


def _apply(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS model_registry (
            model_package_id TEXT PRIMARY KEY,
            model_version TEXT NOT NULL,
            manifest_sha256 TEXT NOT NULL CHECK (length(manifest_sha256) = 64),
            release_status TEXT NOT NULL,
            installed_utc_ms INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1))
        ) STRICT
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_model_registry_one_active
        ON model_registry(active) WHERE active = 1
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_events (
            analysis_id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL UNIQUE,
            session_uuid TEXT NOT NULL,
            rep_uuid TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            model_package_id TEXT NOT NULL,
            model_version TEXT NOT NULL,
            feature_contract_version TEXT NOT NULL,
            input_hash TEXT NOT NULL CHECK (length(input_hash) = 64),
            label TEXT NOT NULL,
            bad_form_probability REAL NOT NULL
                CHECK (bad_form_probability >= 0.0 AND bad_form_probability <= 1.0),
            threshold REAL NOT NULL CHECK (threshold >= 0.0 AND threshold <= 1.0),
            latency_ns INTEGER NOT NULL CHECK (latency_ns >= 0),
            quality TEXT NOT NULL,
            created_monotonic_ns INTEGER NOT NULL CHECK (created_monotonic_ns >= 0),
            created_utc_ms INTEGER,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_hash TEXT NOT NULL CHECK (length(payload_hash) = 64),
            FOREIGN KEY (session_uuid) REFERENCES sessions(record_uuid),
            FOREIGN KEY (rep_uuid) REFERENCES reps(record_uuid)
        ) STRICT
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_analysis_session_rep "
        "ON analysis_events(session_uuid, rep_uuid)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS outbox (
            event_id TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            device_id TEXT NOT NULL,
            session_uuid TEXT NOT NULL,
            created_monotonic_ns INTEGER NOT NULL CHECK (created_monotonic_ns >= 0),
            created_utc_ms INTEGER,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            payload_hash TEXT NOT NULL CHECK (length(payload_hash) = 64),
            state TEXT NOT NULL DEFAULT 'pending'
                CHECK (state IN ('pending', 'leased', 'acknowledged', 'rejected')),
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
            next_attempt_utc_ms INTEGER NOT NULL DEFAULT 0 CHECK (next_attempt_utc_ms >= 0),
            lease_until_utc_ms INTEGER,
            acknowledged_utc_ms INTEGER,
            gateway_version TEXT,
            last_error_code TEXT,
            FOREIGN KEY (session_uuid) REFERENCES sessions(record_uuid)
        ) STRICT
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_outbox_ready "
        "ON outbox(state, next_attempt_utc_ms, created_monotonic_ns)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            audit_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            actor_type TEXT NOT NULL,
            actor_id TEXT,
            created_monotonic_ns INTEGER NOT NULL CHECK (created_monotonic_ns >= 0),
            created_utc_ms INTEGER,
            outcome TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}'
                CHECK (json_valid(details_json))
        ) STRICT
        """
    )


MIGRATION = Migration(
    version=2,
    name="analysis_outbox_audit",
    definition="model registry; analysis events; durable outbox; audit events",
    apply=_apply,
)
