"""Migration 0003: bounded local-session IMU summaries and active-session guard."""

from __future__ import annotations

import sqlite3

from digital_spotter.persistence.schema import Migration


def _apply(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_sessions_one_active
        ON sessions(state) WHERE state = 'active'
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS session_imu_summaries (
            session_uuid TEXT PRIMARY KEY
                REFERENCES sessions(record_uuid) ON DELETE CASCADE,
            imu_device_id TEXT NOT NULL,
            sample_count INTEGER NOT NULL DEFAULT 0 CHECK (sample_count >= 0),
            gap_count INTEGER NOT NULL DEFAULT 0 CHECK (gap_count >= 0),
            degraded_sample_count INTEGER NOT NULL DEFAULT 0
                CHECK (degraded_sample_count >= 0),
            clock_reset_count INTEGER NOT NULL DEFAULT 0
                CHECK (clock_reset_count >= 0),
            distinct_boot_count INTEGER NOT NULL DEFAULT 0
                CHECK (distinct_boot_count >= 0),
            ring_eviction_count INTEGER NOT NULL DEFAULT 0
                CHECK (ring_eviction_count >= 0),
            duplicate_event_count INTEGER NOT NULL DEFAULT 0
                CHECK (duplicate_event_count >= 0),
            last_boot_id TEXT,
            first_sequence INTEGER CHECK (
                first_sequence IS NULL OR first_sequence BETWEEN 0 AND 65535
            ),
            last_sequence INTEGER CHECK (
                last_sequence IS NULL OR last_sequence BETWEEN 0 AND 65535
            ),
            first_captured_monotonic_ns INTEGER CHECK (
                first_captured_monotonic_ns IS NULL
                OR first_captured_monotonic_ns >= 0
            ),
            last_captured_monotonic_ns INTEGER CHECK (
                last_captured_monotonic_ns IS NULL
                OR last_captured_monotonic_ns >= 0
            ),
            updated_monotonic_ns INTEGER NOT NULL CHECK (updated_monotonic_ns >= 0)
        ) STRICT
        """
    )


MIGRATION = Migration(
    version=3,
    name="local_session_runtime",
    definition="one active session; bounded aggregate IMU session summaries",
    apply=_apply,
)
