"""
inference/feature_engineer.py
Purpose: Transforms raw angles + IMU data into the exact 40 features
         used in v4 training. Feature order MUST match FEATURE_ORDER
         in config/constants.py exactly.
Author: bimalawijekoon
Version: 2.0.0
Last Modified: 2026-06-20
"""

import logging
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.constants import (
    TOTAL_FEATURES, FEATURE_ORDER,
    NUM_LANDMARK_XY_FEATURES, NUM_IMU_RAW_FEATURES, NUM_BAR_FEATURES,
)

logger = logging.getLogger(__name__)


class FeatureEngineer:
    """Transform raw pose/IMU data into the 40-feature v4 training vector.

    Feature groups (in order, see FEATURE_ORDER for exact field names):
        1. Context (5): Height, Weight, ExerciseID, RepPhase, Load
        2. Vision XY landmarks (16): L/R Hip/Knee/Shoulder/Ankle X and Y
        3. Trunk angle (1): trunk inclination only — raw L/R angles dropped
        4. IMU raw (6): Acc XYZ + Gyro XYZ (mock until real ESP32-S3 lands)
        5. Bar performance (3): Velocity, Power, Jerk (mock until real IMU)
        6. Asymmetry (3): Hip/Knee/Ankle |L-R|, replaces raw L/R angle pairs
        7. Engineered (4): IMU_Acc_Magnitude, Knee_Hip_Coupling_L/R,
           Velocity_Decel_Ratio
        8. Subject (2): Femur_Tibia_Ratio, BMI (manual per-session input)
    """

    # Landmarks used for XY extraction (order matters!)
    _XY_LANDMARKS = [
        "LEFT_HIP", "RIGHT_HIP",
        "LEFT_KNEE", "RIGHT_KNEE",
        "LEFT_SHOULDER", "RIGHT_SHOULDER",
        "LEFT_ANKLE", "RIGHT_ANKLE",
    ]

    def engineer(self, landmarks, angles, imu_data=None, context=None, subject=None):
        """Build the complete 40-feature vector matching FEATURE_ORDER.

        Args:
            landmarks: Dict {name: (x, y, z, visibility)}.
            angles: Dict {joint_name: angle_degrees} — needs LEFT/RIGHT_HIP,
                LEFT/RIGHT_KNEE, LEFT/RIGHT_ANKLE, TRUNK.
            imu_data: Optional dict from ESP32Bridge.read_sample() (acc_x..gyro_z,
                v_bar_velocity, p_bar_power, smoothness_jerk). None = zeros.
            context: Optional dict — rep_phase, exercise_id, load_kg.
            subject: Optional dict — height_cm, weight_kg, ftr (manual per-session
                input collected at /api/session/start). None = config defaults.

        Returns:
            numpy.ndarray: Shape (40,) float32, ordered per FEATURE_ORDER.
        """
        features = np.zeros(TOTAL_FEATURES, dtype=np.float32)
        idx = 0
        features[idx:idx+5] = self._extract_context(context, subject); idx += 5
        features[idx:idx+16] = self._extract_landmark_xy(landmarks);    idx += 16
        features[idx:idx+1]  = self._extract_trunk_angle(angles);       idx += 1
        features[idx:idx+6]  = self._extract_imu_features(imu_data);    idx += 6
        features[idx:idx+3]  = self._extract_bar_features(imu_data);    idx += 3
        features[idx:idx+3]  = self._compute_asymmetry_features(angles); idx += 3
        features[idx:idx+4]  = self._compute_engineered_features(angles, imu_data); idx += 4
        features[idx:idx+2]  = self._extract_subject_features(subject); idx += 2
        assert idx == TOTAL_FEATURES, f"Feature count mismatch: expected {TOTAL_FEATURES}, got {idx}"
        return features

    def _extract_landmark_xy(self, landmarks):
        """Extract 16 XY coordinates from 8 landmarks.

        Args:
            landmarks: Dict of {name: (x, y, z, visibility)}.

        Returns:
            numpy.ndarray: Shape (16,) — [x1, y1, x2, y2, ...].
        """
        xy = np.zeros(NUM_LANDMARK_XY_FEATURES, dtype=np.float32)
        for i, name in enumerate(self._XY_LANDMARKS):
            if name in landmarks:
                x, y = landmarks[name][0], landmarks[name][1]
                xy[i * 2] = x
                xy[i * 2 + 1] = y
        return xy

    def _extract_trunk_angle(self, angles):
        """Extract the single trunk inclination feature.

        Args:
            angles: Dict of {joint_name: angle_degrees}.

        Returns:
            numpy.ndarray: Shape (1,).
        """
        return np.array([angles.get("TRUNK", 0.0)], dtype=np.float32)

    def _compute_asymmetry_features(self, angles):
        """Compute left-right asymmetry features.

        Args:
            angles: Dict of {joint_name: angle_degrees}.

        Returns:
            numpy.ndarray: Shape (3,) — hip, knee, ankle asymmetry.
        """
        hip_asym = abs(
            angles.get("LEFT_HIP", 0) - angles.get("RIGHT_HIP", 0)
        )
        knee_asym = abs(
            angles.get("LEFT_KNEE", 0) - angles.get("RIGHT_KNEE", 0)
        )
        ankle_asym = abs(
            angles.get("LEFT_ANKLE", 0) - angles.get("RIGHT_ANKLE", 0)
        )
        return np.array(
            [hip_asym, knee_asym, ankle_asym], dtype=np.float32
        )

    def _compute_engineered_features(self, angles, imu_data):
        """Compute the 4 v4-only engineered features.

        IMU_Acc_Magnitude: sqrt(ax^2+ay^2+az^2), rotation-invariant movement
            intensity. Gravity baseline ~9.81 when still.
        Knee_Hip_Coupling_L/R: knee_flexion_angle / (hip_flexion_angle + eps).
            Needs the RAW per-side angles, not the asymmetry — read directly
            from `angles` here even though raw angles aren't in the output vector.
        Velocity_Decel_Ratio: placeholder 1.0 (neutral) here — the true value
            needs phase1 AND phase3 bar velocity and is computed once per
            completed rep in SessionManager, then backfilled into the delta
            row before inference. See sequence_buffer.py changes.

        Args:
            angles: Dict of joint angles (raw, includes L/R pairs).
            imu_data: Optional IMU dict, None = zeros/neutral defaults.

        Returns:
            numpy.ndarray: Shape (4,) — [IMU_Acc_Magnitude, Knee_Hip_Coupling_L,
                Knee_Hip_Coupling_R, Velocity_Decel_Ratio].
        """
        eps = 1e-6
        if imu_data is None:
            imu_mag = 0.0
        else:
            ax = imu_data.get("acc_x", 0.0)
            ay = imu_data.get("acc_y", 0.0)
            az = imu_data.get("acc_z", 0.0)
            imu_mag = float(np.sqrt(ax**2 + ay**2 + az**2))

        knee_hip_l = angles.get("LEFT_KNEE", 0.0) / (angles.get("LEFT_HIP", 0.0) + eps)
        knee_hip_r = angles.get("RIGHT_KNEE", 0.0) / (angles.get("RIGHT_HIP", 0.0) + eps)

        decel_ratio = 1.0  # neutral placeholder; SessionManager overwrites this
                           # on the delta row once phase1/phase3 velocity are both known

        return np.array([imu_mag, knee_hip_l, knee_hip_r, decel_ratio], dtype=np.float32)

    def _extract_imu_features(self, imu_data):
        """Extract 6 raw IMU features.

        Args:
            imu_data: Optional dict with acc/gyro values.
                None returns zeros (placeholder).

        Returns:
            numpy.ndarray: Shape (6,) — [acc_x, acc_y, acc_z,
                gyro_x, gyro_y, gyro_z].
        """
        # TODO: PHASE_8 - Replace with actual IMU data from ESP32-S3
        if imu_data is None:
            return np.zeros(NUM_IMU_RAW_FEATURES, dtype=np.float32)

        return np.array([
            imu_data.get("acc_x", 0.0),
            imu_data.get("acc_y", 0.0),
            imu_data.get("acc_z", 0.0),
            imu_data.get("gyro_x", 0.0),
            imu_data.get("gyro_y", 0.0),
            imu_data.get("gyro_z", 0.0),
        ], dtype=np.float32)

    def _extract_bar_features(self, imu_data):
        """Extract 3 bar performance features.

        Args:
            imu_data: Optional dict with bar velocity/power/jerk.
                None returns zeros (placeholder).

        Returns:
            numpy.ndarray: Shape (3,) — [velocity, power, jerk].
        """
        # TODO: PHASE_8 - Compute from IMU when available
        if imu_data is None:
            return np.zeros(NUM_BAR_FEATURES, dtype=np.float32)

        return np.array([
            imu_data.get("v_bar_velocity", 0.0),
            imu_data.get("p_bar_power", 0.0),
            imu_data.get("smoothness_jerk", 0.0),
        ], dtype=np.float32)

    def _extract_context(self, context, subject):
        """Extract the 5 context features: height, weight, exercise_id, phase, load.

        Args:
            context: Optional dict with rep_phase, exercise_id, load_kg.
            subject: Optional dict with height_cm, weight_kg (manual per-session input).

        Returns:
            numpy.ndarray: Shape (5,) — [height_cm, weight_kg, exercise_id, rep_phase, load_kg].
        """
        context = context or {}
        subject = subject or {}
        return np.array([
            subject.get("height_cm", 175.0),
            subject.get("weight_kg", 75.0),
            context.get("exercise_id", 0),
            context.get("rep_phase", 0),
            context.get("load_kg", 0.0),
        ], dtype=np.float32)

    def _extract_subject_features(self, subject):
        """Extract the 2 trailing subject-context features: FTR, BMI.

        Args:
            subject: Optional dict with height_cm, weight_kg, ftr — same dict
                passed to start_session(), manual per-session input.

        Returns:
            numpy.ndarray: Shape (2,) — [Femur_Tibia_Ratio, BMI].
                BMI is computed from height_cm/weight_kg if not given directly.
        """
        subject = subject or {}
        height_cm = subject.get("height_cm", 175.0)
        weight_kg = subject.get("weight_kg", 75.0)
        ftr = subject.get("ftr", 1.20)  # ~population average from subject_meta.csv

        bmi = subject.get("bmi")
        if bmi is None:
            height_m = height_cm / 100.0
            bmi = weight_kg / (height_m ** 2) if height_m > 0 else 0.0

        return np.array([ftr, bmi], dtype=np.float32)
