"""Migration 0001: bridge the prototype schema to product identity/state fields."""

from __future__ import annotations

import sqlite3
from uuid import UUID, uuid5

from digital_spotter.persistence.schema import Migration, add_column_if_missing


LEGACY_NAMESPACE = UUID("6dfcc594-753c-5a5a-ae6d-0e0b43f97b59")


def _apply(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            hardware_model TEXT NOT NULL,
            provisioned_utc_ms INTEGER,
            state TEXT NOT NULL CHECK (state IN ('provisioning', 'active', 'revoked')),
            metadata_json TEXT NOT NULL DEFAULT '{}'
                CHECK (json_valid(metadata_json))
        ) STRICT
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exercise_id INTEGER NOT NULL,
            exercise_name TEXT NOT NULL,
            started_at TEXT DEFAULT CURRENT_TIMESTAMP,
            ended_at TEXT,
            total_reps INTEGER DEFAULT 0,
            good_reps INTEGER DEFAULT 0,
            bad_reps INTEGER DEFAULT 0,
            notes TEXT,
            height_cm REAL,
            weight_kg REAL,
            ftr REAL,
            record_uuid TEXT,
            device_id TEXT,
            schema_version INTEGER NOT NULL DEFAULT 1,
            state TEXT NOT NULL DEFAULT 'legacy_import',
            started_monotonic_ns INTEGER,
            ended_monotonic_ns INTEGER,
            model_package_id TEXT,
            created_utc_ms INTEGER,
            exercise_contract_version TEXT,
            privacy_mode TEXT NOT NULL DEFAULT 'summary_only'
        )
        """
    )
    session_columns = (
        ("height_cm", "REAL"),
        ("weight_kg", "REAL"),
        ("ftr", "REAL"),
        ("record_uuid", "TEXT"),
        ("device_id", "TEXT"),
        ("schema_version", "INTEGER NOT NULL DEFAULT 1"),
        ("state", "TEXT NOT NULL DEFAULT 'legacy_import'"),
        ("started_monotonic_ns", "INTEGER"),
        ("ended_monotonic_ns", "INTEGER"),
        ("model_package_id", "TEXT"),
        ("created_utc_ms", "INTEGER"),
        ("exercise_contract_version", "TEXT"),
        ("privacy_mode", "TEXT NOT NULL DEFAULT 'summary_only'"),
    )
    for name, definition in session_columns:
        add_column_if_missing(connection, "sessions", name, definition)

    for row in connection.execute(
        "SELECT id FROM sessions WHERE record_uuid IS NULL OR record_uuid = ''"
    ).fetchall():
        record_uuid = str(uuid5(LEGACY_NAMESPACE, f"session:{row[0]}"))
        connection.execute(
            "UPDATE sessions SET record_uuid = ? WHERE id = ?",
            (record_uuid, row[0]),
        )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_sessions_record_uuid ON sessions(record_uuid)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_device_created "
        "ON sessions(device_id, created_utc_ms)"
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS reps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES sessions(id),
            rep_number INTEGER NOT NULL,
            phase INTEGER NOT NULL,
            timestamp_ms INTEGER NOT NULL,
            left_hip_angle REAL,
            right_hip_angle REAL,
            left_knee_angle REAL,
            right_knee_angle REAL,
            left_ankle_angle REAL,
            right_ankle_angle REAL,
            trunk_angle REAL,
            inference_label TEXT,
            inference_confidence REAL,
            landmark_data TEXT,
            record_uuid TEXT,
            rep_event_id TEXT,
            completed_monotonic_ns INTEGER,
            quality TEXT NOT NULL DEFAULT 'unavailable',
            analysis_id TEXT,
            payload_hash TEXT
        )
        """
    )
    rep_columns = (
        ("record_uuid", "TEXT"),
        ("rep_event_id", "TEXT"),
        ("completed_monotonic_ns", "INTEGER"),
        ("quality", "TEXT NOT NULL DEFAULT 'unavailable'"),
        ("analysis_id", "TEXT"),
        ("payload_hash", "TEXT"),
    )
    for name, definition in rep_columns:
        add_column_if_missing(connection, "reps", name, definition)

    for row in connection.execute(
        "SELECT id FROM reps WHERE record_uuid IS NULL OR record_uuid = ''"
    ).fetchall():
        record_uuid = str(uuid5(LEGACY_NAMESPACE, f"rep-row:{row[0]}"))
        connection.execute(
            "UPDATE reps SET record_uuid = ? WHERE id = ?",
            (record_uuid, row[0]),
        )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_reps_record_uuid ON reps(record_uuid)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_reps_session_id ON reps(session_id)"
    )


MIGRATION = Migration(
    version=1,
    name="core_legacy_bridge",
    definition="devices; sessions product identity/state; reps product identity/quality",
    apply=_apply,
)
