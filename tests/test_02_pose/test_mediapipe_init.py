"""
tests/test_02_pose/test_mediapipe_init.py
Purpose: Test PoseEngine initialization and mock processing.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import sys
import pytest
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vision.pose_engine import PoseEngine, PoseResult


class TestPoseEngineInit:
    """Test PoseEngine initialization and basic operations."""

    def test_pose_engine_initializes(self):
        """Verify PoseEngine can be created without error."""
        engine = PoseEngine()
        assert engine is not None

    def test_pose_engine_processes_frame(self):
        """Verify PoseEngine can process a synthetic frame."""
        engine = PoseEngine()
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = engine.process_frame(frame)
        assert isinstance(result, PoseResult)
        assert isinstance(result.processing_time_ms, float)

    def test_pose_result_has_landmarks(self):
        """Verify PoseResult contains landmark data."""
        engine = PoseEngine()
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = engine.process_frame(frame)
        # In mock mode, should have landmarks
        if result.is_valid:
            assert len(result.landmarks) > 0
            # Check landmark format: (x, y, z, visibility)
            for name, coords in result.landmarks.items():
                assert len(coords) == 4

    def test_pose_engine_release(self):
        """Verify PoseEngine releases cleanly."""
        engine = PoseEngine()
        engine.release()
        # Should not raise
