-- database/schema.sql
-- Purpose: SQLite schema — all tables defined here.
--          Digital Spotter session, rep, and system log storage.
-- Author: bimalawijekoon
-- Version: 1.0.0
-- Last Modified: 2026-06-15

-- ──────────────────────────────────────────────────────────────────
-- Training sessions
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_id   INTEGER NOT NULL,
    exercise_name TEXT    NOT NULL,
    started_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at      TIMESTAMP,
    total_reps    INTEGER DEFAULT 0,
    good_reps     INTEGER DEFAULT 0,
    bad_reps      INTEGER DEFAULT 0,
    notes         TEXT,
    height_cm     REAL,
    weight_kg     REAL,
    ftr           REAL
);

-- ──────────────────────────────────────────────────────────────────
-- Individual repetitions within a session
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reps (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id           INTEGER NOT NULL REFERENCES sessions(id),
    rep_number           INTEGER NOT NULL,
    phase                INTEGER NOT NULL,
    timestamp_ms         INTEGER NOT NULL,
    left_hip_angle       REAL,
    right_hip_angle      REAL,
    left_knee_angle      REAL,
    right_knee_angle     REAL,
    left_ankle_angle     REAL,
    right_ankle_angle    REAL,
    trunk_angle          REAL,
    inference_label      TEXT,
    inference_confidence REAL,
    landmark_data        TEXT
);

-- Index for fast session lookup on reps
CREATE INDEX IF NOT EXISTS idx_reps_session_id ON reps(session_id);

-- ──────────────────────────────────────────────────────────────────
-- System event log
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    level     TEXT,
    message   TEXT,
    module    TEXT
);
