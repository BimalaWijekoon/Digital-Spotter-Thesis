"""
vision/rep_segmenter.py
Purpose: Detect repetitions and segment into 3 temporal phases
         using Savitzky-Golay smoothing and peak detection.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config
from config.constants import REP_PHASES

logger = logging.getLogger(__name__)

# Attempt scipy import; degrade gracefully
try:
    from scipy.signal import savgol_filter, find_peaks
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logger.warning("scipy not available — rep segmentation limited")


@dataclass
class RepEvent:
    """Event fired when a complete rep is detected.

    Attributes:
        rep_number: Sequential rep number in the session.
        phase: Current phase (1=Eccentric, 2=Isometric, 3=Concentric).
        phase_name: Human-readable phase name.
        frame_start: Frame index where rep started.
        frame_end: Frame index where rep ended.
        angles_at_bottom: Joint angles at deepest point of rep.
    """
    rep_number: int = 0
    phase: int = 0
    phase_name: str = ""
    frame_start: int = 0
    frame_end: int = 0
    angles_at_bottom: dict = None

    def __post_init__(self):
        if self.angles_at_bottom is None:
            self.angles_at_bottom = {}
        if not self.phase_name and self.phase in REP_PHASES:
            self.phase_name = REP_PHASES[self.phase]

    def to_dict(self):
        """Convert to dictionary for JSON serialization.

        Returns:
            dict: All fields as a dictionary.
        """
        return {
            "rep_number": self.rep_number,
            "phase": self.phase,
            "phase_name": self.phase_name,
            "frame_start": self.frame_start,
            "frame_end": self.frame_end,
            "angles_at_bottom": self.angles_at_bottom,
        }


class RepSegmenter:
    """Detect repetitions and segment into temporal phases.

    Uses Savitzky-Golay smoothing on the knee flexion signal
    to detect rep boundaries via peak detection, then segments
    each rep into 3 phases: Eccentric, Isometric, Concentric.
    """

    def __init__(self, fps=30):
        """Initialize RepSegmenter.

        Args:
            fps: Camera framerate for window size calculations.

        Side Effects:
            Allocates angle history buffer.
        """
        self._fps = fps
        self._config = Config.REP_SEGMENTATION
        self._angle_buffer = deque(maxlen=fps * 30)  # 30 sec buffer
        self._frame_count = 0
        self._rep_count = 0
        self._last_peak_idx = 0
        self._min_frames_between_reps = int(fps * 1.0)  # Min 1 sec per rep
        self._current_phase = 0
        self._phase_angles = {}

        # State tracking
        self._tracking_descent = False
        self._descent_start_angle = None
        self._bottom_angle = None
        self._bottom_frame = 0

        logger.info(
            "RepSegmenter initialized (fps=%d, min_gap=%d frames)",
            fps, self._min_frames_between_reps
        )

    def update(self, angles):
        """Add a frame's angles and detect rep/phase transitions.

        This is called every frame. Internally tracks the knee flexion
        signal to detect reps using a simplified state machine.

        Args:
            angles: dict[str, float] — Joint angles for current frame.
                Must include 'LEFT_KNEE' and 'RIGHT_KNEE'.

        Returns:
            RepEvent or None: RepEvent if a phase transition was
            detected, None otherwise.
        """
        # Use average knee angle as primary signal
        left_knee = angles.get("LEFT_KNEE", 180)
        right_knee = angles.get("RIGHT_KNEE", 180)
        avg_knee = (left_knee + right_knee) / 2.0

        self._angle_buffer.append(avg_knee)
        self._frame_count += 1

        # Need minimum frames to start detection
        if self._frame_count < self._min_frames_between_reps:
            return None

        return self._state_machine_update(avg_knee, angles)

    def _state_machine_update(self, avg_knee, angles):
        """Process angle through the rep detection state machine.

        States:
        - IDLE: Looking for descent (angle decreasing significantly)
        - DESCENT: Tracking descent, looking for bottom
        - ASCENT: Tracking ascent back to standing

        Args:
            avg_knee: Average bilateral knee angle.
            angles: Full angle dict for the current frame.

        Returns:
            RepEvent or None: Event if phase transition detected.
        """
        # Thresholds
        descent_threshold = 10   # degrees drop to start tracking
        bottom_threshold = 5     # degrees of stability at bottom
        ascent_threshold = 15    # degrees rise to confirm ascent

        if not self._tracking_descent:
            # Looking for start of descent
            if self._descent_start_angle is None:
                self._descent_start_angle = avg_knee
            elif (self._descent_start_angle - avg_knee) > descent_threshold:
                # Descent started
                self._tracking_descent = True
                self._bottom_angle = avg_knee
                self._bottom_frame = self._frame_count
                self._current_phase = 1  # Eccentric

                return RepEvent(
                    rep_number=self._rep_count + 1,
                    phase=1,
                    frame_start=self._frame_count,
                    angles_at_bottom=angles.copy(),
                )
            else:
                # Update baseline if angle is higher
                if avg_knee > self._descent_start_angle:
                    self._descent_start_angle = avg_knee
        else:
            # Currently tracking a rep
            if avg_knee < self._bottom_angle:
                # Still descending — update bottom
                self._bottom_angle = avg_knee
                self._bottom_frame = self._frame_count

            elif self._current_phase == 1:
                # Check for transition to isometric (bottom)
                if (self._frame_count - self._bottom_frame) > (
                    self._fps * 0.1
                ):
                    self._current_phase = 2  # Isometric
                    self._phase_angles = angles.copy()

                    return RepEvent(
                        rep_number=self._rep_count + 1,
                        phase=2,
                        frame_start=self._bottom_frame,
                        angles_at_bottom=self._phase_angles,
                    )

            elif self._current_phase == 2:
                # Check for ascent (concentric)
                if (avg_knee - self._bottom_angle) > ascent_threshold:
                    self._current_phase = 3  # Concentric
                    return RepEvent(
                        rep_number=self._rep_count + 1,
                        phase=3,
                        frame_start=self._bottom_frame,
                        frame_end=self._frame_count,
                        angles_at_bottom=self._phase_angles,
                    )

            elif self._current_phase == 3:
                # Check if returned to standing
                if self._descent_start_angle is not None and (
                    avg_knee > (self._descent_start_angle - 10)
                ):
                    # Rep complete — reset for next
                    self._rep_count += 1
                    self._tracking_descent = False
                    self._descent_start_angle = avg_knee
                    self._bottom_angle = None
                    self._current_phase = 0

        return None

    def _smooth_signal(self, signal):
        """Apply Savitzky-Golay filter to angle signal.

        Args:
            signal: numpy array of angle values.

        Returns:
            numpy.ndarray: Smoothed signal. Returns original if
            scipy unavailable or signal too short.
        """
        if not SCIPY_AVAILABLE or len(signal) < 7:
            return np.array(signal)

        window = int(
            len(signal) * self._config.SAVITZKY_GOLAY_WINDOW_RATIO
        )
        # Window must be odd and >= polyorder + 2
        window = max(window, self._config.POLYNOMIAL_ORDER + 2)
        if window % 2 == 0:
            window += 1
        window = min(window, len(signal))
        if window % 2 == 0:
            window -= 1

        return savgol_filter(
            signal,
            window_length=window,
            polyorder=self._config.POLYNOMIAL_ORDER,
        )

    def _detect_peaks(self, signal):
        """Find rep deep-points (minima) in the smoothed signal.

        Inverts signal and uses scipy find_peaks for valley detection.

        Args:
            signal: numpy array of smoothed angle values.

        Returns:
            list[int]: Frame indices of detected rep bottoms.
        """
        if not SCIPY_AVAILABLE or len(signal) < 10:
            return []

        # Invert to find valleys as peaks
        inverted = -np.array(signal)
        min_distance = int(
            self._fps * self._config.MIN_INTER_PEAK_RATIO
        )

        peaks, properties = find_peaks(
            inverted,
            prominence=self._config.PROMINENCE_THRESHOLD,
            distance=min_distance,
        )

        return peaks.tolist()

    def _assign_phase(self, frame_idx, rep_start, rep_end):
        """Assign temporal phase (1/2/3) to a frame within a rep.

        Args:
            frame_idx: Frame index to classify.
            rep_start: Frame index where rep started.
            rep_end: Frame index where rep ended.

        Returns:
            int: Phase number (1=Eccentric, 2=Isometric, 3=Concentric).
        """
        if rep_end <= rep_start:
            return 1

        progress = (frame_idx - rep_start) / (rep_end - rep_start)
        boundaries = self._config.PHASE_BOUNDARIES

        if progress < boundaries[0]:
            return 1  # Eccentric / Descent
        elif progress < boundaries[1]:
            return 2  # Isometric / Bottom
        else:
            return 3  # Concentric / Lockout

    def reset(self):
        """Clear buffer and reset state for new session.

        Side Effects:
            Resets all internal counters and buffers.
        """
        self._angle_buffer.clear()
        self._frame_count = 0
        self._rep_count = 0
        self._last_peak_idx = 0
        self._current_phase = 0
        self._tracking_descent = False
        self._descent_start_angle = None
        self._bottom_angle = None
        self._bottom_frame = 0
        self._phase_angles = {}
        logger.info("RepSegmenter reset")

    @property
    def rep_count(self):
        """Current completed rep count.

        Returns:
            int: Number of fully completed reps.
        """
        return self._rep_count

    @property
    def current_phase(self):
        """Current phase of the active rep.

        Returns:
            int: Phase number (0=idle, 1/2/3 during active rep).
        """
        return self._current_phase
