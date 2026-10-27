"""
database/models.py
Purpose: Data classes for Session, Rep, and SystemLog.
         Provides clean Python objects for database records.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Session:
    """Represents a training session record.

    Attributes:
        id: Auto-incremented primary key.
        exercise_id: Numeric exercise identifier (0=Squat, 1=Deadlift).
        exercise_name: Human-readable exercise name.
        started_at: ISO timestamp when session started.
        ended_at: ISO timestamp when session ended (None if active).
        total_reps: Total repetitions counted.
        good_reps: Reps classified as good form.
        bad_reps: Reps classified as bad form.
        notes: Optional user notes.
        height_cm: Subject height in cm (v4 pipeline).
        weight_kg: Subject weight in kg (v4 pipeline).
        ftr: Femur-to-tibia ratio (v4 pipeline).
    """
    id: int = 0
    exercise_id: int = 0
    exercise_name: str = ""
    started_at: str = ""
    ended_at: Optional[str] = None
    total_reps: int = 0
    good_reps: int = 0
    bad_reps: int = 0
    notes: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    ftr: Optional[float] = None

    def to_dict(self):
        """Convert to dictionary for JSON serialization.

        Returns:
            dict: All fields as a dictionary.
        """
        return {
            "id": self.id,
            "exercise_id": self.exercise_id,
            "exercise_name": self.exercise_name,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "total_reps": self.total_reps,
            "good_reps": self.good_reps,
            "bad_reps": self.bad_reps,
            "notes": self.notes,
            "height_cm": self.height_cm,
            "weight_kg": self.weight_kg,
            "ftr": self.ftr,
        }

    @classmethod
    def from_row(cls, row):
        """Create Session from sqlite3.Row.

        Args:
            row: sqlite3.Row object from query result.

        Returns:
            Session: Populated Session instance.
        """
        return cls(
            id=row["id"],
            exercise_id=row["exercise_id"],
            exercise_name=row["exercise_name"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            total_reps=row["total_reps"],
            good_reps=row["good_reps"],
            bad_reps=row["bad_reps"],
            notes=row["notes"],
            height_cm=row["height_cm"] if "height_cm" in row.keys() else None,
            weight_kg=row["weight_kg"] if "weight_kg" in row.keys() else None,
            ftr=row["ftr"] if "ftr" in row.keys() else None,
        )


@dataclass
class Rep:
    """Represents a single repetition record.

    Attributes:
        id: Auto-incremented primary key.
        session_id: Foreign key to sessions table.
        rep_number: Sequential rep number within session.
        phase: Temporal phase (1=Eccentric, 2=Isometric, 3=Concentric).
        timestamp_ms: Millisecond timestamp of rep detection.
        left_hip_angle: Left hip flexion angle in degrees.
        right_hip_angle: Right hip flexion angle in degrees.
        left_knee_angle: Left knee flexion angle in degrees.
        right_knee_angle: Right knee flexion angle in degrees.
        left_ankle_angle: Left ankle dorsiflexion angle in degrees.
        right_ankle_angle: Right ankle dorsiflexion angle in degrees.
        trunk_angle: Trunk inclination angle in degrees.
        inference_label: Model prediction label.
        inference_confidence: Model confidence score 0.0-1.0.
        landmark_data: JSON string of raw landmark positions.
    """
    id: int = 0
    session_id: int = 0
    rep_number: int = 0
    phase: int = 0
    timestamp_ms: int = 0
    left_hip_angle: float = 0.0
    right_hip_angle: float = 0.0
    left_knee_angle: float = 0.0
    right_knee_angle: float = 0.0
    left_ankle_angle: float = 0.0
    right_ankle_angle: float = 0.0
    trunk_angle: float = 0.0
    inference_label: Optional[str] = None
    inference_confidence: Optional[float] = None
    landmark_data: Optional[str] = None

    def to_dict(self):
        """Convert to dictionary for JSON serialization.

        Returns:
            dict: All fields as a dictionary.
        """
        return {
            "id": self.id,
            "session_id": self.session_id,
            "rep_number": self.rep_number,
            "phase": self.phase,
            "timestamp_ms": self.timestamp_ms,
            "left_hip_angle": self.left_hip_angle,
            "right_hip_angle": self.right_hip_angle,
            "left_knee_angle": self.left_knee_angle,
            "right_knee_angle": self.right_knee_angle,
            "left_ankle_angle": self.left_ankle_angle,
            "right_ankle_angle": self.right_ankle_angle,
            "trunk_angle": self.trunk_angle,
            "inference_label": self.inference_label,
            "inference_confidence": self.inference_confidence,
            "landmark_data": self.landmark_data,
        }

    @classmethod
    def from_row(cls, row):
        """Create Rep from sqlite3.Row.

        Args:
            row: sqlite3.Row object from query result.

        Returns:
            Rep: Populated Rep instance.
        """
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            rep_number=row["rep_number"],
            phase=row["phase"],
            timestamp_ms=row["timestamp_ms"],
            left_hip_angle=row["left_hip_angle"],
            right_hip_angle=row["right_hip_angle"],
            left_knee_angle=row["left_knee_angle"],
            right_knee_angle=row["right_knee_angle"],
            left_ankle_angle=row["left_ankle_angle"],
            right_ankle_angle=row["right_ankle_angle"],
            trunk_angle=row["trunk_angle"],
            inference_label=row["inference_label"],
            inference_confidence=row["inference_confidence"],
            landmark_data=row["landmark_data"],
        )


@dataclass
class SystemLog:
    """Represents a system log entry.

    Attributes:
        id: Auto-incremented primary key.
        timestamp: ISO timestamp of log entry.
        level: Log level (INFO, WARNING, ERROR, etc).
        message: Log message text.
        module: Source module name.
    """
    id: int = 0
    timestamp: str = ""
    level: str = "INFO"
    message: str = ""
    module: str = ""

    def to_dict(self):
        """Convert to dictionary for JSON serialization.

        Returns:
            dict: All fields as a dictionary.
        """
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
            "module": self.module,
        }

    @classmethod
    def from_row(cls, row):
        """Create SystemLog from sqlite3.Row.

        Args:
            row: sqlite3.Row object from query result.

        Returns:
            SystemLog: Populated SystemLog instance.
        """
        return cls(
            id=row["id"],
            timestamp=row["timestamp"],
            level=row["level"],
            message=row["message"],
            module=row["module"],
        )
