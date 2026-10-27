"""
database/queries.py
Purpose: All SQL queries as named functions — no raw SQL anywhere else.
         Every database operation goes through this module.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import json
import logging
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import get_connection
from database.models import Session, Rep

logger = logging.getLogger(__name__)


def create_session(exercise_id, exercise_name, notes=None, height_cm=None, weight_kg=None, ftr=None):
    """Create a new training session.

    Args:
        exercise_id: Numeric exercise identifier (0=Squat, 1=Deadlift).
        exercise_name: Human-readable exercise name string.
        notes: Optional user notes for the session.
        height_cm: Subject height in cm (v4 pipeline).
        weight_kg: Subject weight in kg (v4 pipeline).
        ftr: Femur-to-tibia ratio (v4 pipeline).

    Returns:
        int: The newly created session ID.

    Side Effects:
        Inserts a row into the sessions table.
    """
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO sessions (exercise_id, exercise_name, notes, height_cm, weight_kg, ftr)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (exercise_id, exercise_name, notes, height_cm, weight_kg, ftr)
    )
    conn.commit()
    session_id = cursor.lastrowid
    logger.info("Created session %d for %s", session_id, exercise_name)
    return session_id


def end_session(session_id):
    """End an active training session.

    Args:
        session_id: The session ID to end.

    Returns:
        bool: True if session was found and ended, False otherwise.

    Side Effects:
        Updates ended_at timestamp and rep count statistics.
    """
    conn = get_connection()

    # Count reps and their labels for this session
    stats = conn.execute(
        """SELECT
               COUNT(*) as total,
               SUM(CASE WHEN inference_label = 'Good Form' THEN 1 ELSE 0 END)
                   as good,
               SUM(CASE WHEN inference_label = 'Bad Form' THEN 1 ELSE 0 END)
                   as bad
           FROM reps
           WHERE session_id = ? AND phase = 3""",
        (session_id,)
    ).fetchone()

    total_reps = stats["total"] if stats["total"] else 0
    good_reps = stats["good"] if stats["good"] else 0
    bad_reps = stats["bad"] if stats["bad"] else 0

    result = conn.execute(
        """UPDATE sessions
           SET ended_at = CURRENT_TIMESTAMP,
               total_reps = ?,
               good_reps = ?,
               bad_reps = ?
           WHERE id = ?""",
        (total_reps, good_reps, bad_reps, session_id)
    )
    conn.commit()

    if result.rowcount > 0:
        logger.info(
            "Ended session %d: %d total, %d good, %d bad",
            session_id, total_reps, good_reps, bad_reps
        )
        return True
    return False


def insert_rep(session_id, rep_data):
    """Insert a repetition record into the database.

    Args:
        session_id: The session this rep belongs to.
        rep_data: Dictionary containing rep fields:
            - rep_number (int): Sequential rep number.
            - phase (int): Temporal phase 1/2/3.
            - timestamp_ms (int): Millisecond timestamp.
            - angles (dict): Joint angle values.
            - inference_label (str, optional): Model prediction.
            - inference_confidence (float, optional): Model confidence.
            - landmark_data (dict, optional): Raw landmark positions.

    Returns:
        int: The newly created rep row ID.

    Side Effects:
        Inserts a row into the reps table.
    """
    conn = get_connection()
    angles = rep_data.get("angles", {})
    landmark_json = None
    if rep_data.get("landmark_data"):
        landmark_json = json.dumps(rep_data["landmark_data"])

    cursor = conn.execute(
        """INSERT INTO reps (
               session_id, rep_number, phase, timestamp_ms,
               left_hip_angle, right_hip_angle,
               left_knee_angle, right_knee_angle,
               left_ankle_angle, right_ankle_angle,
               trunk_angle,
               inference_label, inference_confidence,
               landmark_data
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            rep_data.get("rep_number", 0),
            rep_data.get("phase", 0),
            rep_data.get("timestamp_ms", 0),
            angles.get("LEFT_HIP", 0.0),
            angles.get("RIGHT_HIP", 0.0),
            angles.get("LEFT_KNEE", 0.0),
            angles.get("RIGHT_KNEE", 0.0),
            angles.get("LEFT_ANKLE", 0.0),
            angles.get("RIGHT_ANKLE", 0.0),
            angles.get("TRUNK", 0.0),
            rep_data.get("inference_label"),
            rep_data.get("inference_confidence"),
            landmark_json,
        )
    )
    conn.commit()
    return cursor.lastrowid


def get_session(session_id):
    """Get a single session by ID.

    Args:
        session_id: The session ID to retrieve.

    Returns:
        Session: Session dataclass instance, or None if not found.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()

    if row:
        return Session.from_row(row)
    return None


def get_session_reps(session_id):
    """Get all reps for a session, ordered by rep number and phase.

    Args:
        session_id: The session ID to query reps for.

    Returns:
        list[Rep]: List of Rep dataclass instances.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM reps
           WHERE session_id = ?
           ORDER BY rep_number, phase""",
        (session_id,)
    ).fetchall()

    return [Rep.from_row(row) for row in rows]


def get_recent_sessions(limit=10):
    """Get the most recent sessions.

    Args:
        limit: Maximum number of sessions to return (default 10).

    Returns:
        list[Session]: List of Session dataclass instances,
        ordered by most recent first.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM sessions
           ORDER BY started_at DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()

    return [Session.from_row(row) for row in rows]


def get_session_stats(session_id):
    """Get aggregate statistics for a session.

    Args:
        session_id: The session ID to compute stats for.

    Returns:
        dict: Statistics dictionary with keys:
            - total_reps (int)
            - good_reps (int)
            - bad_reps (int)
            - avg_confidence (float)
            - avg_knee_angle (float)
            - min_knee_angle (float)
            - max_knee_angle (float)
            - duration_s (float or None)
    """
    conn = get_connection()

    # Rep statistics (only count phase 3 = concentric as completed reps)
    rep_stats = conn.execute(
        """SELECT
               COUNT(*) as total,
               SUM(CASE WHEN inference_label = 'Good Form'
                   THEN 1 ELSE 0 END) as good,
               SUM(CASE WHEN inference_label = 'Bad Form'
                   THEN 1 ELSE 0 END) as bad,
               AVG(inference_confidence) as avg_conf,
               AVG(left_knee_angle) as avg_knee,
               MIN(left_knee_angle) as min_knee,
               MAX(left_knee_angle) as max_knee
           FROM reps
           WHERE session_id = ? AND phase = 3""",
        (session_id,)
    ).fetchone()

    # Session duration
    session = conn.execute(
        """SELECT
               started_at,
               ended_at,
               CASE WHEN ended_at IS NOT NULL
                   THEN (julianday(ended_at) - julianday(started_at)) * 86400
                   ELSE NULL
               END as duration_s
           FROM sessions WHERE id = ?""",
        (session_id,)
    ).fetchone()

    return {
        "total_reps": rep_stats["total"] if rep_stats["total"] else 0,
        "good_reps": rep_stats["good"] if rep_stats["good"] else 0,
        "bad_reps": rep_stats["bad"] if rep_stats["bad"] else 0,
        "avg_confidence": round(rep_stats["avg_conf"], 3)
            if rep_stats["avg_conf"] else 0.0,
        "avg_knee_angle": round(rep_stats["avg_knee"], 1)
            if rep_stats["avg_knee"] else 0.0,
        "min_knee_angle": round(rep_stats["min_knee"], 1)
            if rep_stats["min_knee"] else 0.0,
        "max_knee_angle": round(rep_stats["max_knee"], 1)
            if rep_stats["max_knee"] else 0.0,
        "duration_s": round(session["duration_s"], 1)
            if session and session["duration_s"] else None,
    }
