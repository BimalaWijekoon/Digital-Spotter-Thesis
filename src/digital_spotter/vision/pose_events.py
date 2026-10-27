"""Construction policy for canonical pose events from one processed frame."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from uuid import UUID

from digital_spotter.contracts import (
    EventEnvelope,
    EventType,
    PoseLandmark,
    PoseSample,
    Quality,
    ReasonCode,
    SCHEMA_VERSION_V1,
    Source,
)
from digital_spotter.contracts.time import MonotonicNanoseconds
from digital_spotter.vision.frames import CameraFrame


class PoseEventError(ValueError):
    """A processed frame cannot produce a canonical pose event."""


@dataclass(frozen=True)
class PoseEvaluation:
    """Adapter-neutral pose output before it becomes a wire event."""

    found: bool
    landmarks: tuple[PoseLandmark, ...]
    angles: Mapping[str, float]
    confidence: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("pose confidence must be between zero and one")
        if not self.found and (self.landmarks or self.angles or self.confidence != 0.0):
            raise ValueError("missing pose cannot contain landmarks, angles, or confidence")
        if self.found and not self.landmarks:
            raise ValueError("found pose must contain landmarks")


@dataclass(frozen=True)
class PoseBuildResult:
    sample: PoseSample
    reason_code: ReasonCode


def build_pose_sample(
    *,
    camera_id: str,
    frame: CameraFrame,
    evaluation: PoseEvaluation,
    processed_monotonic_ns: int,
    frames_dropped_since_previous: int,
    minimum_confidence: float,
    landmark_schema_version: int = 1,
    simulated: bool = False,
) -> PoseBuildResult:
    """Create one fail-closed `PoseSample` and its explicit quality reason."""

    captured_ns = frame.timestamp.captured_monotonic_ns
    if captured_ns is None:
        raise PoseEventError("camera frame has no measurement-time capture timestamp")
    if processed_monotonic_ns < frame.received_monotonic_ns:
        raise PoseEventError("pose processing cannot finish before frame receipt")
    if frames_dropped_since_previous < 0:
        raise PoseEventError("dropped-frame count must not be negative")
    if not 0.0 <= minimum_confidence <= 1.0:
        raise PoseEventError("minimum confidence must be between zero and one")

    if not evaluation.found:
        quality = Quality.SIMULATED if simulated else Quality.VISION_DEGRADED
        reason = ReasonCode.POSE_NOT_FOUND
    elif evaluation.confidence < minimum_confidence:
        quality = Quality.SIMULATED if simulated else Quality.VISION_DEGRADED
        reason = ReasonCode.POSE_LOW_VISIBILITY
    elif simulated:
        quality = Quality.SIMULATED
        reason = ReasonCode.SIMULATED
    else:
        quality = Quality.GOOD
        reason = ReasonCode.OK

    sample = PoseSample(
        camera_id=camera_id,
        frame_sequence=frame.sequence,
        captured_monotonic_ns=MonotonicNanoseconds(captured_ns),
        processed_monotonic_ns=MonotonicNanoseconds(processed_monotonic_ns),
        image_width=frame.width,
        image_height=frame.height,
        landmark_schema_version=landmark_schema_version,
        landmarks=evaluation.landmarks,
        angles=dict(evaluation.angles),
        pose_confidence=evaluation.confidence,
        quality=quality,
        processing_latency_ns=processed_monotonic_ns - captured_ns,
        frames_dropped_since_previous=frames_dropped_since_previous,
    )
    return PoseBuildResult(sample=sample, reason_code=reason)


def build_pose_envelope(
    *,
    result: PoseBuildResult,
    event_id: UUID,
    created_monotonic_ns: int,
    device_id: str | None = None,
) -> EventEnvelope[PoseSample]:
    """Wrap a pose sample in the shared, bounded internal event envelope."""

    return EventEnvelope[PoseSample](
        schema_version=SCHEMA_VERSION_V1,
        event_type=EventType.POSE_SAMPLE,
        event_id=event_id,
        source=Source.VISION,
        device_id=device_id,
        captured_monotonic_ns=result.sample.captured_monotonic_ns,
        created_monotonic_ns=MonotonicNanoseconds(created_monotonic_ns),
        quality=result.sample.quality,
        payload=result.sample,
    )
