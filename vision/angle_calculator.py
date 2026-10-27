"""
vision/angle_calculator.py
Purpose: Compute 7 clinical joint angles from 3D landmark coordinates.
         Uses arctangent dot-product formula for accurate joint angle
         calculation from 3-point vectors.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import logging
import math
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.constants import JOINT_NAMES

logger = logging.getLogger(__name__)


class AngleCalculator:
    """Compute clinical joint angles from 3D landmark positions.

    Calculates 7 joint angles: bilateral hip flexion, knee flexion,
    ankle dorsiflexion, and trunk inclination.
    """

    @staticmethod
    def calculate_angle(a, b, c):
        """Calculate the angle at point B formed by points A-B-C.

        Uses the arctangent dot-product formula:
        angle = atan2(|BA × BC|, BA · BC)

        Args:
            a: tuple/list (x, y, z) — first point.
            b: tuple/list (x, y, z) — vertex point (angle measured here).
            c: tuple/list (x, y, z) — third point.

        Returns:
            float: Angle in degrees (0-180).
        """
        a = np.array(a[:3], dtype=np.float64)
        b = np.array(b[:3], dtype=np.float64)
        c = np.array(c[:3], dtype=np.float64)

        ba = a - b
        bc = c - b

        # Handle zero-length vectors
        ba_norm = np.linalg.norm(ba)
        bc_norm = np.linalg.norm(bc)
        if ba_norm < 1e-10 or bc_norm < 1e-10:
            return 0.0

        cosine = np.dot(ba, bc) / (ba_norm * bc_norm)
        # Clamp to [-1, 1] to avoid NaN from floating point errors
        cosine = np.clip(cosine, -1.0, 1.0)

        angle_rad = np.arccos(cosine)
        return math.degrees(angle_rad)

    @classmethod
    def compute_all_angles(cls, landmarks):
        """Compute all 7 joint angles from landmark positions.

        Args:
            landmarks: Dict mapping landmark name to
                (x, y, z, visibility) tuple. Must contain:
                LEFT/RIGHT_SHOULDER, LEFT/RIGHT_HIP,
                LEFT/RIGHT_KNEE, LEFT/RIGHT_ANKLE.

        Returns:
            dict[str, float]: Maps joint name to angle in degrees.
                Keys match JOINT_NAMES from constants.py.
        """
        angles = {
            "LEFT_HIP": cls.compute_left_hip_flexion(landmarks),
            "RIGHT_HIP": cls.compute_right_hip_flexion(landmarks),
            "LEFT_KNEE": cls.compute_left_knee_flexion(landmarks),
            "RIGHT_KNEE": cls.compute_right_knee_flexion(landmarks),
            "LEFT_ANKLE": cls.compute_left_ankle_dorsiflexion(landmarks),
            "RIGHT_ANKLE": cls.compute_right_ankle_dorsiflexion(landmarks),
            "TRUNK": cls.compute_trunk_inclination(landmarks),
        }
        return angles

    @classmethod
    def compute_left_hip_flexion(cls, landmarks):
        """Compute left hip flexion angle.

        Angle at LEFT_HIP between LEFT_SHOULDER and LEFT_KNEE.

        Args:
            landmarks: Landmark dict with LEFT_SHOULDER, LEFT_HIP, LEFT_KNEE.

        Returns:
            float: Left hip flexion angle in degrees.
        """
        return cls.calculate_angle(
            landmarks.get("LEFT_SHOULDER", (0, 0, 0, 0)),
            landmarks.get("LEFT_HIP", (0, 0, 0, 0)),
            landmarks.get("LEFT_KNEE", (0, 0, 0, 0)),
        )

    @classmethod
    def compute_right_hip_flexion(cls, landmarks):
        """Compute right hip flexion angle.

        Angle at RIGHT_HIP between RIGHT_SHOULDER and RIGHT_KNEE.

        Args:
            landmarks: Landmark dict with RIGHT_SHOULDER, RIGHT_HIP,
                RIGHT_KNEE.

        Returns:
            float: Right hip flexion angle in degrees.
        """
        return cls.calculate_angle(
            landmarks.get("RIGHT_SHOULDER", (0, 0, 0, 0)),
            landmarks.get("RIGHT_HIP", (0, 0, 0, 0)),
            landmarks.get("RIGHT_KNEE", (0, 0, 0, 0)),
        )

    @classmethod
    def compute_left_knee_flexion(cls, landmarks):
        """Compute left knee flexion angle.

        Angle at LEFT_KNEE between LEFT_HIP and LEFT_ANKLE.

        Args:
            landmarks: Landmark dict with LEFT_HIP, LEFT_KNEE, LEFT_ANKLE.

        Returns:
            float: Left knee flexion angle in degrees.
        """
        return cls.calculate_angle(
            landmarks.get("LEFT_HIP", (0, 0, 0, 0)),
            landmarks.get("LEFT_KNEE", (0, 0, 0, 0)),
            landmarks.get("LEFT_ANKLE", (0, 0, 0, 0)),
        )

    @classmethod
    def compute_right_knee_flexion(cls, landmarks):
        """Compute right knee flexion angle.

        Angle at RIGHT_KNEE between RIGHT_HIP and RIGHT_ANKLE.

        Args:
            landmarks: Landmark dict with RIGHT_HIP, RIGHT_KNEE,
                RIGHT_ANKLE.

        Returns:
            float: Right knee flexion angle in degrees.
        """
        return cls.calculate_angle(
            landmarks.get("RIGHT_HIP", (0, 0, 0, 0)),
            landmarks.get("RIGHT_KNEE", (0, 0, 0, 0)),
            landmarks.get("RIGHT_ANKLE", (0, 0, 0, 0)),
        )

    @classmethod
    def compute_left_ankle_dorsiflexion(cls, landmarks):
        """Compute left ankle dorsiflexion angle.

        Angle at LEFT_ANKLE between LEFT_KNEE and LEFT_HEEL.
        Falls back to LEFT_FOOT_INDEX if LEFT_HEEL unavailable.

        Args:
            landmarks: Landmark dict with LEFT_KNEE, LEFT_ANKLE,
                LEFT_HEEL (or LEFT_FOOT_INDEX).

        Returns:
            float: Left ankle dorsiflexion angle in degrees.
        """
        foot = landmarks.get(
            "LEFT_HEEL",
            landmarks.get("LEFT_FOOT_INDEX", (0, 0, 0, 0))
        )
        return cls.calculate_angle(
            landmarks.get("LEFT_KNEE", (0, 0, 0, 0)),
            landmarks.get("LEFT_ANKLE", (0, 0, 0, 0)),
            foot,
        )

    @classmethod
    def compute_right_ankle_dorsiflexion(cls, landmarks):
        """Compute right ankle dorsiflexion angle.

        Angle at RIGHT_ANKLE between RIGHT_KNEE and RIGHT_HEEL.
        Falls back to RIGHT_FOOT_INDEX if RIGHT_HEEL unavailable.

        Args:
            landmarks: Landmark dict with RIGHT_KNEE, RIGHT_ANKLE,
                RIGHT_HEEL (or RIGHT_FOOT_INDEX).

        Returns:
            float: Right ankle dorsiflexion angle in degrees.
        """
        foot = landmarks.get(
            "RIGHT_HEEL",
            landmarks.get("RIGHT_FOOT_INDEX", (0, 0, 0, 0))
        )
        return cls.calculate_angle(
            landmarks.get("RIGHT_KNEE", (0, 0, 0, 0)),
            landmarks.get("RIGHT_ANKLE", (0, 0, 0, 0)),
            foot,
        )

    @classmethod
    def compute_trunk_inclination(cls, landmarks):
        """Compute trunk inclination angle from vertical.

        Measures the angle between the midline of shoulders-to-hips
        and the vertical axis. 0° = perfectly upright,
        90° = horizontal.

        Args:
            landmarks: Landmark dict with LEFT/RIGHT_SHOULDER,
                LEFT/RIGHT_HIP.

        Returns:
            float: Trunk inclination angle in degrees from vertical.
        """
        ls = np.array(landmarks.get(
            "LEFT_SHOULDER", (0, 0, 0, 0))[:3])
        rs = np.array(landmarks.get(
            "RIGHT_SHOULDER", (0, 0, 0, 0))[:3])
        lh = np.array(landmarks.get(
            "LEFT_HIP", (0, 0, 0, 0))[:3])
        rh = np.array(landmarks.get(
            "RIGHT_HIP", (0, 0, 0, 0))[:3])

        mid_shoulder = (ls + rs) / 2.0
        mid_hip = (lh + rh) / 2.0

        trunk_vec = mid_shoulder - mid_hip
        # Vertical vector (pointing up in image coords — negative Y)
        vertical = np.array([0, -1, 0], dtype=np.float64)

        trunk_norm = np.linalg.norm(trunk_vec)
        if trunk_norm < 1e-10:
            return 0.0

        cosine = np.dot(trunk_vec, vertical) / trunk_norm
        cosine = np.clip(cosine, -1.0, 1.0)

        return math.degrees(np.arccos(cosine))
