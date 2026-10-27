"""
integration/session_manager.py
Purpose: Orchestrates session lifecycle — ties together database,
         vision pipeline, and inference engine into coherent sessions.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import logging
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config
from database.queries import (
    create_session, end_session, get_session, insert_rep,
    get_session_stats,
)
from inference.feature_engineer import FeatureEngineer
from inference.sequence_buffer import SequenceBuffer
from inference.lstm_runner import LSTMRunner
from vision.frame_processor import FrameProcessor
from imu.esp32_bridge import ESP32Bridge
from config.constants import FEATURE_ORDER

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages a complete training session lifecycle.

    Coordinates:
    - FrameProcessor (pose + angles + rep segmentation)
    - FeatureEngineer (38-dim feature vector)
    - SequenceBuffer (3-phase accumulation)
    - LSTMRunner (inference)
    - Database (session + rep storage)
    """

    def __init__(self, on_rep_complete=None, on_inference=None):
        """Initialize all ML models and hardware bridges.

        Args:
            on_rep_complete: Optional callback function(rep_event_dict)
            on_inference: Optional callback function(inference_result_dict)
        """
        self._on_rep_complete = on_rep_complete
        self._on_inference = on_inference
        self._frame_processor = FrameProcessor()
        self._feature_engineer = FeatureEngineer()
        self._sequence_buffer = SequenceBuffer()
        self._lstm_runner = LSTMRunner()
        self._imu_bridge = ESP32Bridge()
        self._imu_bridge.connect()

        self._session_id = None
        self._exercise_id = 0
        self._exercise_name = ""
        self._is_active = False
        self._rep_count = 0

        # Per-session manual subject input (replaces old hardcoded constants)
        self._subject = {"height_cm": 175.0, "weight_kg": 75.0, "ftr": 1.20}
        self._current_load_kg = 0.0

        # Per-rep phase1/phase3 bar velocity, for Velocity_Decel_Ratio computation
        self._phase1_velocity = None
        self._phase3_velocity = None
        self._decel_ratio_idx = FEATURE_ORDER.index("Velocity_Decel_Ratio")

        # Load model
        self._lstm_runner.load()

        logger.info("SessionManager initialized")

    def start_session(self, exercise_id=0, notes=None, height_cm=None,
                       weight_kg=None, ftr=None, load_kg=None):
        """Start a new training session.

        Args:
            exercise_id: Exercise type (0=Squat, 1=Deadlift).
            notes: Optional notes.
            height_cm: Subject height in cm, manual per-session input.
                Defaults to 175.0 if not provided.
            weight_kg: Subject weight in kg, manual per-session input.
                Defaults to 75.0 if not provided.
            ftr: Femur-to-tibia ratio, manual per-session input.
                Defaults to 1.20 (population-average from training data)
                if not provided.
            load_kg: Barbell load for this session, manual per-session input.
                Defaults to 0.0 if not provided.

        Returns:
            int: New session ID.

        Side Effects:
            Creates DB record (including new subject columns), resets
            pipeline, starts processing.
        """
        self._exercise_id = exercise_id
        self._exercise_name = Config.EXERCISES.get_name(exercise_id)

        self._subject = {
            "height_cm": height_cm if height_cm is not None else 175.0,
            "weight_kg": weight_kg if weight_kg is not None else 75.0,
            "ftr": ftr if ftr is not None else 1.20,
        }
        self._current_load_kg = load_kg if load_kg is not None else 0.0

        self._session_id = create_session(
            exercise_id, self._exercise_name, notes,
            height_cm=self._subject["height_cm"],
            weight_kg=self._subject["weight_kg"],
            ftr=self._subject["ftr"],
        )
        self._is_active = True
        self._rep_count = 0
        self._phase1_velocity = None
        self._phase3_velocity = None

        # Reset pipeline state
        self._frame_processor.reset_session()
        self._sequence_buffer.reset()

        logger.info(
            "Session %d started (exercise=%s, height=%.1fcm, weight=%.1fkg, ftr=%.2f, load=%.1fkg)",
            self._session_id, self._exercise_name,
            self._subject["height_cm"], self._subject["weight_kg"],
            self._subject["ftr"], self._current_load_kg
        )

        # Command the ESP32 to start streaming IMU data
        self._imu_bridge.start_session(f"s_{self._session_id}")

        return self._session_id

    def stop_session(self):
        """Stop the active session.

        Returns:
            dict: Final session statistics.

        Side Effects:
            Closes DB record, stops processing.
        """
        if not self._is_active:
            return {}

        self._is_active = False
        end_session(self._session_id)

        stats = get_session_stats(self._session_id)

        logger.info(
            "Session %d ended (reps=%d, good=%d, bad=%d)",
            self._session_id, stats["total_reps"],
            stats["good_reps"], stats["bad_reps"]
        )
        
        # Command ESP32 to stop streaming IMU data
        self._imu_bridge.stop_session()

        session_id = self._session_id
        self._session_id = None

        return stats

    def process_frame_result(self, frame_result):
        """Process a completed frame through the inference pipeline.

        Called by the frame processing loop for each frame. If a rep
        phase event occurs, engineers features and accumulates in the
        buffer. When all 3 phases are collected, runs LSTM inference.

        Args:
            frame_result: FrameResult from FrameProcessor.

        Returns:
            dict or None: Inference result dict if a full rep
            was classified, None otherwise.

        Side Effects:
            May insert rep into database and emit WebSocket events.
        """
        if not self._is_active or not frame_result.is_valid:
            return None

        # Check for rep event
        rep_event = frame_result.rep_event
        if rep_event is None:
            return None

        # Engineer features for this phase
        imu_sample = self._imu_bridge.read_sample()

        context = {
            "rep_phase": rep_event.phase,
            "exercise_id": self._exercise_id,
            "load_kg": self._current_load_kg,
        }
        features = self._feature_engineer.engineer(
            frame_result.landmarks, frame_result.angles,
            imu_data=imu_sample, context=context, subject=self._subject,
        )

        # Track bar velocity at phase boundaries for Velocity_Decel_Ratio
        if rep_event.phase == 1:
            self._phase1_velocity = imu_sample.get("v_bar_velocity", 0.0)
        elif rep_event.phase == 3:
            self._phase3_velocity = imu_sample.get("v_bar_velocity", 0.0)

        # Push into buffer
        self._sequence_buffer.push(rep_event.phase, features)

        # Emit rep phase event
        if self._on_rep_complete:
            self._on_rep_complete(rep_event.to_dict())

        # Check if all 3 phases collected
        if not self._sequence_buffer.is_ready():
            return None

        # Compute the real Velocity_Decel_Ratio now that phase1 and phase3
        # velocities are both known (was a 1.0 placeholder during per-frame
        # feature engineering — see feature_engineer._compute_engineered_features)
        decel_ratio = 1.0
        if self._phase1_velocity is not None and self._phase3_velocity is not None:
            decel_ratio = self._phase3_velocity / (abs(self._phase1_velocity) + 1e-6)

        sequence = self._sequence_buffer.get_model_sequence(
            decel_ratio_idx=self._decel_ratio_idx,
            decel_ratio_value=decel_ratio,
        )
        result = self._lstm_runner.predict(sequence)
        self._sequence_buffer.reset()
        self._phase1_velocity = None
        self._phase3_velocity = None

        self._rep_count += 1

        # Save to DB
        rep_data = {
            "rep_number": self._rep_count,
            "phase": 3,
            "timestamp_ms": frame_result.timestamp_ms,
            "angles": frame_result.angles,
            "inference_label": result.label,
            "inference_confidence": result.confidence,
        }
        insert_rep(self._session_id, rep_data)

        # Emit inference result
        result_dict = result.to_dict()
        result_dict["rep_number"] = self._rep_count

        if self._on_inference:
            self._on_inference({
                "label": result.label,
                "confidence": result.confidence,
                "is_bad_form": result.is_bad_form,
                "rep_number": self._rep_count,
            })

        return result_dict

    @property
    def frame_processor(self):
        """Get the FrameProcessor instance.
        Returns:
            FrameProcessor: The internal frame processor.
        """
        return self._frame_processor

    @property
    def session_id(self):
        """Get current session ID.
        Returns:
            int or None: Active session ID.
        """
        return self._session_id

    @property
    def is_active(self):
        """Check if a session is in progress.
        Returns:
            bool: True if session is active.
        """
        return self._is_active

    @property
    def rep_count(self):
        """Get completed rep count.
        Returns:
            int: Reps counted this session.
        """
        return self._rep_count
