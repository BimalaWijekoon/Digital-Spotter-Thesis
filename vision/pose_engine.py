"""
vision/pose_engine.py
Purpose: MediaPipe BlazePose initialization and landmark extraction.
         Wraps the MediaPipe Pose solution for frame-by-frame processing.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import logging
import time
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config
from config.constants import MEDIAPIPE_LANDMARKS

logger = logging.getLogger(__name__)

# Attempt to import mediapipe; gracefully degrade if unavailable
try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    logger.warning("MediaPipe not available — using mock pose engine")


class PoseResult:
    """Container for pose estimation results from a single frame.

    Attributes:
        landmarks: Dict mapping landmark name to (x, y, z, visibility) tuple.
        raw_landmarks: Raw MediaPipe landmark list (None if mock).
        is_valid: Whether the frame had sufficient landmark visibility.
        processing_time_ms: Time taken to process the frame.
    """

    def __init__(self, landmarks=None, raw_landmarks=None,
                 is_valid=False, processing_time_ms=0.0):
        """Initialize PoseResult.

        Args:
            landmarks: Dict of {name: (x, y, z, visibility)}.
            raw_landmarks: Raw MediaPipe NormalizedLandmarkList.
            is_valid: Whether landmarks pass visibility threshold.
            processing_time_ms: Processing latency in milliseconds.
        """
        self.landmarks = landmarks or {}
        self.raw_landmarks = raw_landmarks
        self.is_valid = is_valid
        self.processing_time_ms = processing_time_ms


class PoseEngine:
    """MediaPipe BlazePose pose estimation engine.

    Wraps MediaPipe Pose for single-frame inference with configurable
    model complexity and confidence thresholds.
    """

    def __init__(self, config=None):
        """Initialize PoseEngine with BlazePose Heavy model.

        Args:
            config: Optional Config object. Uses global Config if None.

        Side Effects:
            Loads MediaPipe Pose model into memory.
        """
        self._config = config or Config
        self._pose = None
        self._mp_pose = None
        self._mp_drawing = None

        if MEDIAPIPE_AVAILABLE:
            self._mp_pose = mp.solutions.pose
            self._mp_drawing = mp.solutions.drawing_utils
            self._pose = self._mp_pose.Pose(
                model_complexity=self._config.MEDIAPIPE.MODEL_COMPLEXITY,
                min_detection_confidence=(
                    self._config.MEDIAPIPE.MIN_DETECTION_CONFIDENCE
                ),
                min_tracking_confidence=(
                    self._config.MEDIAPIPE.MIN_TRACKING_CONFIDENCE
                ),
                static_image_mode=False,
            )
            logger.info(
                "PoseEngine initialized with BlazePose "
                "(complexity=%d)",
                self._config.MEDIAPIPE.MODEL_COMPLEXITY
            )
        else:
            logger.warning("PoseEngine running in MOCK mode")

    def process_frame(self, frame):
        """Run pose estimation on a single frame.

        Args:
            frame: numpy.ndarray BGR image from camera/video.

        Returns:
            PoseResult: Contains extracted landmarks and validity flag.

        Side Effects:
            None (pure inference, no state change).
        """
        start_time = time.perf_counter()

        if not MEDIAPIPE_AVAILABLE or self._pose is None:
            return self._mock_process(start_time)

        # MediaPipe expects RGB
        import cv2
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._pose.process(rgb_frame)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        if results.pose_landmarks is None:
            return PoseResult(
                is_valid=False,
                processing_time_ms=elapsed_ms
            )

        landmarks = self.get_landmarks(results.pose_landmarks)
        is_valid = self.is_valid_frame(landmarks)

        return PoseResult(
            landmarks=landmarks,
            raw_landmarks=results.pose_landmarks,
            is_valid=is_valid,
            processing_time_ms=elapsed_ms,
        )

    def get_landmarks(self, pose_landmarks):
        """Extract named landmarks from MediaPipe result.

        Args:
            pose_landmarks: MediaPipe NormalizedLandmarkList with
                33 pose landmarks.

        Returns:
            dict: Maps landmark name (str) to tuple of
                (x, y, z, visibility) where x/y/z are normalized
                coordinates and visibility is 0.0-1.0 confidence.
        """
        landmarks = {}
        for name, idx in MEDIAPIPE_LANDMARKS.items():
            lm = pose_landmarks.landmark[idx]
            landmarks[name] = (lm.x, lm.y, lm.z, lm.visibility)
        return landmarks

    def is_valid_frame(self, landmarks):
        """Check if extracted landmarks meet visibility thresholds.

        A frame is valid if all key lower-body landmarks
        (hips, knees, ankles) have visibility above the threshold.

        Args:
            landmarks: Dict of {name: (x, y, z, visibility)}.

        Returns:
            bool: True if all key landmarks are sufficiently visible.
        """
        threshold = self._config.MEDIAPIPE.VISIBILITY_THRESHOLD
        required_landmarks = [
            "LEFT_HIP", "RIGHT_HIP",
            "LEFT_KNEE", "RIGHT_KNEE",
            "LEFT_ANKLE", "RIGHT_ANKLE",
            "LEFT_SHOULDER", "RIGHT_SHOULDER",
        ]

        for name in required_landmarks:
            if name not in landmarks:
                return False
            _, _, _, visibility = landmarks[name]
            if visibility < threshold:
                return False
        return True

    def draw_skeleton(self, frame, landmarks):
        """Draw skeleton overlay on a frame.

        Args:
            frame: numpy.ndarray BGR image to draw on (will be modified).
            landmarks: Raw MediaPipe NormalizedLandmarkList.

        Returns:
            numpy.ndarray: Frame with skeleton overlay drawn.
        """
        if (not MEDIAPIPE_AVAILABLE or self._mp_drawing is None
                or landmarks is None):
            return frame

        self._mp_drawing.draw_landmarks(
            frame,
            landmarks,
            self._mp_pose.POSE_CONNECTIONS,
        )
        return frame

    def release(self):
        """Release MediaPipe resources.

        Side Effects:
            Closes the MediaPipe Pose solution.
        """
        if self._pose is not None:
            self._pose.close()
            self._pose = None
            logger.info("PoseEngine released")

    def _mock_process(self, start_time):
        """Generate mock pose data when MediaPipe is unavailable.

        Args:
            start_time: perf_counter start timestamp.

        Returns:
            PoseResult: Mock result with synthetic landmark positions.
        """
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Generate plausible landmark positions for a standing person
        mock_landmarks = {}
        base_positions = {
            "LEFT_SHOULDER": (0.4, 0.3, 0.0),
            "RIGHT_SHOULDER": (0.6, 0.3, 0.0),
            "LEFT_HIP": (0.42, 0.55, 0.0),
            "RIGHT_HIP": (0.58, 0.55, 0.0),
            "LEFT_KNEE": (0.41, 0.72, 0.0),
            "RIGHT_KNEE": (0.59, 0.72, 0.0),
            "LEFT_ANKLE": (0.40, 0.90, 0.0),
            "RIGHT_ANKLE": (0.60, 0.90, 0.0),
            "LEFT_HEEL": (0.39, 0.93, 0.0),
            "RIGHT_HEEL": (0.61, 0.93, 0.0),
            "LEFT_FOOT_INDEX": (0.41, 0.94, 0.0),
            "RIGHT_FOOT_INDEX": (0.59, 0.94, 0.0),
            "NOSE": (0.5, 0.15, 0.0),
        }
        for name, (x, y, z) in base_positions.items():
            # Add small noise
            noise = np.random.normal(0, 0.005, 3)
            mock_landmarks[name] = (
                x + noise[0], y + noise[1],
                z + noise[2], 0.95
            )

        return PoseResult(
            landmarks=mock_landmarks,
            raw_landmarks=None,
            is_valid=True,
            processing_time_ms=elapsed_ms,
        )
