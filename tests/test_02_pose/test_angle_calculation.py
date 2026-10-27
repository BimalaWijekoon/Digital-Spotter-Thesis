"""
tests/test_02_pose/test_angle_calculation.py
Purpose: Test AngleCalculator with known geometric configurations.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import sys
import math
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vision.angle_calculator import AngleCalculator


class TestAngleCalculation:
    """Test angle computation with known geometric values."""

    def test_right_angle_90_degrees(self):
        """Verify 90° angle from perpendicular vectors."""
        a = (1, 0, 0, 1.0)
        b = (0, 0, 0, 1.0)
        c = (0, 1, 0, 1.0)
        angle = AngleCalculator.calculate_angle(a, b, c)
        assert abs(angle - 90.0) < 0.01

    def test_straight_angle_180_degrees(self):
        """Verify 180° angle from collinear points."""
        a = (-1, 0, 0, 1.0)
        b = (0, 0, 0, 1.0)
        c = (1, 0, 0, 1.0)
        angle = AngleCalculator.calculate_angle(a, b, c)
        assert abs(angle - 180.0) < 0.01

    def test_acute_angle_60_degrees(self):
        """Verify 60° angle from equilateral triangle vertices."""
        a = (1, 0, 0, 1.0)
        b = (0, 0, 0, 1.0)
        c = (0.5, math.sqrt(3) / 2, 0, 1.0)
        angle = AngleCalculator.calculate_angle(a, b, c)
        assert abs(angle - 60.0) < 0.01

    def test_zero_length_vector_returns_zero(self):
        """Verify zero-length vectors return 0 angle."""
        a = (0, 0, 0, 1.0)
        b = (0, 0, 0, 1.0)
        c = (1, 0, 0, 1.0)
        angle = AngleCalculator.calculate_angle(a, b, c)
        assert angle == 0.0

    def test_compute_all_angles_returns_7(self):
        """Verify compute_all_angles returns all 7 joint angles."""
        landmarks = {
            "LEFT_SHOULDER": (0.4, 0.3, 0.0, 0.9),
            "RIGHT_SHOULDER": (0.6, 0.3, 0.0, 0.9),
            "LEFT_HIP": (0.42, 0.55, 0.0, 0.9),
            "RIGHT_HIP": (0.58, 0.55, 0.0, 0.9),
            "LEFT_KNEE": (0.41, 0.72, 0.0, 0.9),
            "RIGHT_KNEE": (0.59, 0.72, 0.0, 0.9),
            "LEFT_ANKLE": (0.40, 0.90, 0.0, 0.9),
            "RIGHT_ANKLE": (0.60, 0.90, 0.0, 0.9),
            "LEFT_HEEL": (0.39, 0.93, 0.0, 0.9),
            "RIGHT_HEEL": (0.61, 0.93, 0.0, 0.9),
        }
        angles = AngleCalculator.compute_all_angles(landmarks)
        assert len(angles) == 7
        expected_keys = [
            "LEFT_HIP", "RIGHT_HIP",
            "LEFT_KNEE", "RIGHT_KNEE",
            "LEFT_ANKLE", "RIGHT_ANKLE",
            "TRUNK",
        ]
        for key in expected_keys:
            assert key in angles
            assert 0.0 <= angles[key] <= 180.0

    def test_symmetric_landmarks_give_symmetric_angles(self):
        """Verify symmetric body position gives roughly equal L/R angles."""
        landmarks = {
            "LEFT_SHOULDER": (0.4, 0.3, 0.0, 0.9),
            "RIGHT_SHOULDER": (0.6, 0.3, 0.0, 0.9),
            "LEFT_HIP": (0.42, 0.55, 0.0, 0.9),
            "RIGHT_HIP": (0.58, 0.55, 0.0, 0.9),
            "LEFT_KNEE": (0.41, 0.72, 0.0, 0.9),
            "RIGHT_KNEE": (0.59, 0.72, 0.0, 0.9),
            "LEFT_ANKLE": (0.40, 0.90, 0.0, 0.9),
            "RIGHT_ANKLE": (0.60, 0.90, 0.0, 0.9),
            "LEFT_HEEL": (0.39, 0.93, 0.0, 0.9),
            "RIGHT_HEEL": (0.61, 0.93, 0.0, 0.9),
        }
        angles = AngleCalculator.compute_all_angles(landmarks)
        # Hip angles should be roughly equal
        assert abs(angles["LEFT_HIP"] - angles["RIGHT_HIP"]) < 5.0
        # Knee angles should be roughly equal
        assert abs(angles["LEFT_KNEE"] - angles["RIGHT_KNEE"]) < 5.0
