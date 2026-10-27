"""
tests/test_05_database/test_schema.py
Purpose: Test database schema initialization, CRUD operations,
         and session flow.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import os
import sys
import tempfile
import pytest
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.config import Config
from database.db import get_connection, init_db, close_connection
from database.queries import (
    create_session,
    end_session,
    insert_rep,
    get_session,
    get_session_reps,
    get_recent_sessions,
    get_session_stats,
)


@pytest.fixture(autouse=True)
def temp_database(tmp_path):
    """Use a temporary database for each test.

    Creates a fresh SQLite database in a temp directory,
    patches Config.PATHS.DATABASE, initializes schema,
    and cleans up after test.
    """
    original_db = Config.PATHS.DATABASE
    Config.PATHS.DATABASE = tmp_path / "test_sessions.db"

    # Force a new connection with the temp path
    close_connection()
    init_db()

    yield

    close_connection()
    Config.PATHS.DATABASE = original_db


class TestDatabaseInitialization:
    """Test database schema creation and table existence."""

    def test_db_initializes_without_error(self):
        """Verify init_db() completes without raising exceptions."""
        result = init_db()
        assert result is True

    def test_sessions_table_exists(self):
        """Verify the sessions table was created."""
        conn = get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='sessions'"
        )
        assert cursor.fetchone() is not None

    def test_reps_table_exists(self):
        """Verify the reps table was created."""
        conn = get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='reps'"
        )
        assert cursor.fetchone() is not None

    def test_system_log_table_exists(self):
        """Verify the system_log table was created."""
        conn = get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='system_log'"
        )
        assert cursor.fetchone() is not None


class TestSessionCRUD:
    """Test session create, read, update operations."""

    def test_can_create_session(self):
        """Verify a session can be created and returns an ID."""
        session_id = create_session(0, "Barbell Back Squat")
        assert session_id is not None
        assert session_id > 0

    def test_can_get_session(self):
        """Verify a created session can be retrieved."""
        session_id = create_session(0, "Barbell Back Squat", "Test notes")
        session = get_session(session_id)
        assert session is not None
        assert session.exercise_id == 0
        assert session.exercise_name == "Barbell Back Squat"
        assert session.notes == "Test notes"
        assert session.ended_at is None

    def test_can_end_session(self):
        """Verify a session can be ended."""
        session_id = create_session(0, "Barbell Back Squat")
        result = end_session(session_id)
        assert result is True

        session = get_session(session_id)
        assert session.ended_at is not None

    def test_get_recent_sessions(self):
        """Verify recent sessions are returned correctly."""
        create_session(0, "Barbell Back Squat")
        create_session(1, "Conventional Deadlift")
        create_session(0, "Barbell Back Squat")

        sessions = get_recent_sessions(limit=10)
        assert len(sessions) == 3
        # All sessions have valid data
        exercise_names = {s.exercise_name for s in sessions}
        assert "Barbell Back Squat" in exercise_names
        assert "Conventional Deadlift" in exercise_names


class TestRepCRUD:
    """Test rep insert and query operations."""

    def test_can_insert_rep(self):
        """Verify a rep can be inserted into a session."""
        session_id = create_session(0, "Barbell Back Squat")
        rep_data = {
            "rep_number": 1,
            "phase": 3,
            "timestamp_ms": 1000,
            "angles": {
                "LEFT_HIP": 95.5,
                "RIGHT_HIP": 93.2,
                "LEFT_KNEE": 88.0,
                "RIGHT_KNEE": 87.5,
                "LEFT_ANKLE": 72.1,
                "RIGHT_ANKLE": 71.8,
                "TRUNK": 14.3,
            },
            "inference_label": "Good Form",
            "inference_confidence": 0.92,
        }
        rep_id = insert_rep(session_id, rep_data)
        assert rep_id is not None
        assert rep_id > 0

    def test_can_get_session_reps(self):
        """Verify reps can be queried for a session."""
        session_id = create_session(0, "Barbell Back Squat")

        for phase in [1, 2, 3]:
            insert_rep(session_id, {
                "rep_number": 1,
                "phase": phase,
                "timestamp_ms": phase * 1000,
                "angles": {"LEFT_KNEE": 90.0},
            })

        reps = get_session_reps(session_id)
        assert len(reps) == 3
        assert reps[0].phase == 1
        assert reps[2].phase == 3


class TestSessionStats:
    """Test session statistics computation."""

    def test_can_query_session_stats(self):
        """Verify session stats compute correctly."""
        session_id = create_session(0, "Barbell Back Squat")

        # Insert 3 complete reps (phase 3) — 2 good, 1 bad
        for i, label in enumerate(
            ["Good Form", "Good Form", "Bad Form"], start=1
        ):
            insert_rep(session_id, {
                "rep_number": i,
                "phase": 3,
                "timestamp_ms": i * 3000,
                "angles": {"LEFT_KNEE": 85.0 + i},
                "inference_label": label,
                "inference_confidence": 0.85 + (i * 0.03),
            })

        stats = get_session_stats(session_id)
        assert stats["total_reps"] == 3
        assert stats["good_reps"] == 2
        assert stats["bad_reps"] == 1
        assert stats["avg_confidence"] > 0

    def test_empty_session_stats(self):
        """Verify stats return zeros for session with no reps."""
        session_id = create_session(0, "Barbell Back Squat")
        stats = get_session_stats(session_id)
        assert stats["total_reps"] == 0
        assert stats["good_reps"] == 0
        assert stats["bad_reps"] == 0
