"""Bounded research rep phases adapted from the recorded-video FYP extractor.

This module does not score form. It waits for a complete knee-flexion peak and
keeps missing pose or synchronized IMU data explicit instead of inventing a rep.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from statistics import median
from typing import Mapping, Sequence
from uuid import UUID, uuid4

import numpy as np
from scipy.signal import find_peaks, savgol_filter

from digital_spotter.contracts import (
    EventEnvelope,
    EventType,
    IMUSample,
    PoseLandmark,
    PoseSample,
    Quality,
    RepEvent,
    RepTransition,
    Source,
)
from digital_spotter.core.fusion import FusionEngine


PHASE_NAMES = {
    0: ("Descent", "Bottom", "Lockout"),
    1: ("Setup", "Mid-pull", "Lockout"),
}

# Rep segmentation needs only one unobstructed hip-knee-ankle chain. This is
# deliberately separate from the stricter bilateral feature-quality gate used
# by _vision_values() and the V5 candidate path.
REP_TRACKING_VISIBILITY_MIN = 0.5
MODEL_FEATURE_VISIBILITY_MIN = 0.7
MODEL_FEATURE_LANDMARKS = (11, 12, 23, 24, 25, 26, 27, 28, 31, 32)


@dataclass(frozen=True)
class PhaseRecord:
    phase: int
    name: str
    started_monotonic_ns: int
    ended_monotonic_ns: int
    captured_monotonic_ns: int
    frame_count: int
    vision: Mapping[str, float]
    imu: Mapping[str, float] | None
    quality: Quality


@dataclass(frozen=True)
class CompletedRep:
    session_uuid: UUID | None
    event: RepEvent
    phases: tuple[PhaseRecord, PhaseRecord, PhaseRecord]


@dataclass(frozen=True)
class _Observation:
    event: EventEnvelope[PoseSample]
    knee_mean: float


def _point(landmarks: tuple[PoseLandmark, ...], index: int) -> tuple[float, float]:
    landmark = landmarks[index]
    return landmark.x, landmark.y


def _angle(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
) -> float:
    ab = (a[0] - b[0], a[1] - b[1])
    cb = (c[0] - b[0], c[1] - b[1])
    cosine = (ab[0] * cb[0] + ab[1] * cb[1]) / (
        math.hypot(*ab) * math.hypot(*cb) + 1e-9
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _vision_values(pose: PoseSample) -> dict[str, float] | None:
    """Match FYP/Vision/vision.py's normalized coordinates and 2D angles."""
    if (
        pose.quality is not Quality.GOOD
        or len(pose.landmarks) < 33
        or min(
            pose.landmarks[index].visibility
            for index in MODEL_FEATURE_LANDMARKS
        ) < MODEL_FEATURE_VISIBILITY_MIN
    ):
        return None
    landmarks = pose.landmarks
    fields: dict[str, float] = {}
    for name, index in (
        ("L_Shoulder", 11), ("R_Shoulder", 12),
        ("L_Hip", 23), ("R_Hip", 24),
        ("L_Knee", 25), ("R_Knee", 26),
        ("L_Ankle", 27), ("R_Ankle", 28),
    ):
        landmark = landmarks[index]
        for axis in ("X", "Y", "Z"):
            fields[f"Vis_{name}_{axis}"] = round(getattr(landmark, axis.lower()), 3)

    knees: list[float] = []
    for side, shoulder, hip, knee, ankle, foot in (
        ("L", 11, 23, 25, 27, 31),
        ("R", 12, 24, 26, 28, 32),
    ):
        sh, hp, kn, ank, ft = (
            _point(landmarks, index) for index in (shoulder, hip, knee, ankle, foot)
        )
        fields[f"Angle_Hip_Flexion_{side}"] = round(
            max(0.0, min(175.0, 180.0 - _angle(sh, hp, kn))), 1
        )
        knee_angle = round(max(0.0, min(175.0, 180.0 - _angle(hp, kn, ank))), 1)
        fields[f"Angle_Knee_Flexion_{side}"] = knee_angle
        knees.append(knee_angle)
        fields[f"Angle_Ankle_Dorsiflexion_{side}"] = round(
            max(0.0, min(45.0, abs(_angle(kn, ank, ft) - 90.0))), 1
        )

    shoulder_mid = tuple(
        (left + right) / 2.0
        for left, right in zip(_point(landmarks, 11), _point(landmarks, 12))
    )
    hip_mid = tuple(
        (left + right) / 2.0
        for left, right in zip(_point(landmarks, 23), _point(landmarks, 24))
    )
    spine = (shoulder_mid[0] - hip_mid[0], shoulder_mid[1] - hip_mid[1])
    cosine = spine[1] / (math.hypot(*spine) + 1e-9)
    fields["Angle_Trunk_Inclination"] = round(
        math.degrees(math.acos(max(-1.0, min(1.0, cosine)))), 1
    )
    fields["_knee_mean"] = sum(knees) / 2.0
    return fields


def _tracking_knee_flexion(pose: PoseSample) -> float | None:
    """Return knee motion from any sufficiently visible side for rep tracking.

    A side-camera view commonly occludes the far leg. That must not erase the
    rep-motion signal, but it also must not authorize bilateral model features.
    """
    if len(pose.landmarks) < 29:
        return None
    knees: list[float] = []
    for hip, knee, ankle in ((23, 25, 27), (24, 26, 28)):
        side = (pose.landmarks[hip], pose.landmarks[knee], pose.landmarks[ankle])
        if min(landmark.visibility for landmark in side) < REP_TRACKING_VISIBILITY_MIN:
            continue
        angle = 180.0 - _angle(
            _point(pose.landmarks, hip),
            _point(pose.landmarks, knee),
            _point(pose.landmarks, ankle),
        )
        knees.append(max(0.0, min(175.0, angle)))
    return sum(knees) / len(knees) if knees else None


class RepPhaseBuilder:
    """Own one session's bounded pose history and completed-rep cursor."""

    def __init__(
        self,
        *,
        exercise_id: int,
        fps: int,
        session_uuid: UUID | None = None,
        exercise_contract_version: str = "v5-research-video-rule-1",
        max_frames: int = 300,
    ) -> None:
        if exercise_id not in PHASE_NAMES:
            raise ValueError("only V5 squat and deadlift phase names are supported")
        if fps not in (15, 25, 30):
            raise ValueError("research rep phase builder requires 15, 25, or 30 FPS")
        if not 30 <= max_frames <= 900:
            raise ValueError("rep history must hold 30-900 frames")
        self.exercise_id = exercise_id
        self.fps = fps
        self.session_uuid = session_uuid
        self.exercise_contract_version = exercise_contract_version
        self._observations: deque[_Observation] = deque(maxlen=max_frames)
        self._last_frame_sequence: int | None = None
        self._last_capture_ns: int | None = None
        self._last_completed_end_ns: int | None = None
        self._rep_number = 0
        self._fusion = FusionEngine()

    def discard_partial_rep(self) -> None:
        """Pause/resume must not join pre-pause movement to a later repetition."""
        self._observations.clear()
        self._last_frame_sequence = None
        self._last_capture_ns = None

    def add(self, event: EventEnvelope[PoseSample]) -> None:
        if event.event_type is not EventType.POSE_SAMPLE or event.source is not Source.VISION:
            raise ValueError("rep phases require a vision pose event")
        if event.quality is Quality.SIMULATED:
            raise ValueError("simulated poses cannot enter a real rep builder")
        captured_ns = int(event.payload.captured_monotonic_ns)
        if (
            self._last_capture_ns is not None
            and captured_ns <= self._last_capture_ns
        ):
            # The session receiver rejects backward capture time. An equal-time
            # duplicate must not become another phase frame.
            return
        if (
            self._last_frame_sequence is not None
            and event.payload.frame_sequence <= self._last_frame_sequence
        ):
            # Camera restart: abandon the partial rep, not the whole session.
            self._observations.clear()
        tracking_knee = _tracking_knee_flexion(event.payload)
        knee = tracking_knee if tracking_knee is not None else float("nan")
        self._observations.append(_Observation(event, knee))
        self._last_capture_ns = captured_ns
        self._last_frame_sequence = event.payload.frame_sequence

    def poll(
        self, imu_events: Sequence[EventEnvelope[IMUSample]]
    ) -> tuple[CompletedRep, ...]:
        """Emit only newly completed peaks; never the FYP no-peak fake rep."""
        observations = list(self._observations)
        if len(observations) < 10:
            return ()
        angles = np.asarray([item.knee_mean for item in observations], dtype=float)
        finite = np.flatnonzero(np.isfinite(angles))
        if not len(finite):
            return ()
        first = int(finite[0])
        angles = angles[first:]
        if len(angles) < 10:
            return ()
        for index in range(1, len(angles)):
            if not math.isfinite(angles[index]):
                angles[index] = angles[index - 1]
        intervals = np.diff([
            int(item.event.payload.captured_monotonic_ns) for item in observations
        ])
        positive_intervals = intervals[intervals > 0]
        observed_fps = (
            1_000_000_000 / float(np.median(positive_intervals))
            if len(positive_intervals) else self.fps
        )
        # The camera captures at 30 Hz, but latest-frame pose processing is slower.
        # Preserve the source's 0.4 s / 1.2 s rules in measurement time.
        window = max(3, min(int(observed_fps * 0.4) | 1, len(angles) - 2))
        if window % 2 == 0:
            window += 1
        smoothed = savgol_filter(angles, window, 2)
        peaks, _ = find_peaks(
            smoothed, distance=max(1, int(observed_fps * 1.2)), prominence=15
        )
        completed: list[CompletedRep] = []
        for peak in peaks:
            threshold = smoothed[peak] * 0.45
            left = next((index for index in range(peak - 1, -1, -1) if smoothed[index] < threshold), None)
            right = next((index for index in range(peak + 1, len(smoothed)) if smoothed[index] < threshold), None)
            if left is None or right is None or right + 2 >= len(smoothed):
                continue
            start, end = first + left, first + right
            start_ns = int(observations[start].event.payload.captured_monotonic_ns)
            end_ns = int(observations[end].event.payload.captured_monotonic_ns)
            if self._last_completed_end_ns is not None and start_ns <= self._last_completed_end_ns:
                continue
            duration = end - start
            phase1_end = start + max(1, int(duration * 0.35))
            phase2_end = start + max(2, int(duration * 0.45))
            if not start < phase1_end < phase2_end <= end:
                continue
            spans = ((start, phase1_end), (phase1_end, phase2_end), (phase2_end, end + 1))
            phases = tuple(
                self._summarize(
                    observations[begin:finish], phase_id, imu_events
                )
                for phase_id, (begin, finish) in enumerate(spans, 1)
            )
            if any(phase is None for phase in phases):
                continue
            self._rep_number += 1
            quality = (
                Quality.GOOD
                if all(phase.quality is Quality.GOOD for phase in phases)
                else Quality.UNAVAILABLE
            )
            event = RepEvent(
                rep_id=uuid4(),
                rep_number=self._rep_number,
                exercise_contract_version=self.exercise_contract_version,
                event=RepTransition.COMPLETED,
                captured_monotonic_ns=end_ns,
                quality=quality,
            )
            completed.append(CompletedRep(self.session_uuid, event, phases))
            self._last_completed_end_ns = end_ns
        return tuple(completed)

    def _summarize(
        self,
        observations: Sequence[_Observation],
        phase_id: int,
        imu_events: Sequence[EventEnvelope[IMUSample]],
    ) -> PhaseRecord | None:
        vision_rows: list[dict[str, float]] = []
        imu_rows: list[dict[str, float]] = []
        fully_synchronized = True
        for observation in observations:
            values = _vision_values(observation.event.payload)
            if values is None:
                fully_synchronized = False
                continue
            values.pop("_knee_mean")
            vision_rows.append(values)
            outcome = self._fusion.fuse(
                observation.event,
                imu_events,
                now_monotonic_ns=int(observation.event.payload.processed_monotonic_ns),
            )
            if outcome.sample is None or outcome.quality is not Quality.GOOD:
                fully_synchronized = False
                continue
            imu = outcome.sample.interpolated_imu
            imu_rows.append(dict(zip(
                (
                    "acceleration_m_s2_x", "acceleration_m_s2_y", "acceleration_m_s2_z",
                    "angular_velocity_rad_s_x", "angular_velocity_rad_s_y", "angular_velocity_rad_s_z",
                ),
                (*imu.acceleration_m_s2, *imu.angular_velocity_rad_s),
            )))
        vision = (
            {
                name: float(median(row[name] for row in vision_rows))
                for name in vision_rows[0]
            }
            if vision_rows else {}
        )
        imu = (
            {
                name: float(median(row[name] for row in imu_rows))
                for name in imu_rows[0]
            }
            if fully_synchronized and len(imu_rows) == len(observations)
            else None
        )
        timestamps = [int(item.event.payload.captured_monotonic_ns) for item in observations]
        return PhaseRecord(
            phase=phase_id,
            name=PHASE_NAMES[self.exercise_id][phase_id - 1],
            started_monotonic_ns=timestamps[0],
            ended_monotonic_ns=timestamps[-1],
            captured_monotonic_ns=int(median(timestamps)),
            frame_count=len(vision_rows),
            vision=vision,
            imu=imu,
            quality=Quality.GOOD if fully_synchronized and imu is not None else Quality.UNAVAILABLE,
        )
