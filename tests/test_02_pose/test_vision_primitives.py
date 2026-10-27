from __future__ import annotations

from uuid import UUID

import pytest

from digital_spotter.contracts import (
    EventEnvelope,
    PoseLandmark,
    PoseSample,
    Quality,
    ReasonCode,
    Source,
)
from digital_spotter.vision.frames import (
    CameraFrame,
    CaptureTimestamp,
    CaptureTimestampSource,
    LatestFrameSlot,
)
from digital_spotter.vision.pose_events import (
    PoseEvaluation,
    PoseEventError,
    build_pose_envelope,
    build_pose_sample,
)


EVENT_ID = UUID("01993ced-28c0-7000-8000-000000000001")


def _frame(*, captured_ns: int | None = 1_000_000) -> CameraFrame:
    return CameraFrame(
        sequence=7,
        received_monotonic_ns=1_100_000,
        width=640,
        height=360,
        timestamp=CaptureTimestamp(
            captured_monotonic_ns=captured_ns,
            source=(
                CaptureTimestampSource.PICAMERA2_SENSOR_EXPOSURE_START
                if captured_ns is not None
                else CaptureTimestampSource.ARRIVAL_ONLY
            ),
        ),
        pixels=object(),
    )


def _found_pose(*, confidence: float = 0.9) -> PoseEvaluation:
    return PoseEvaluation(
        found=True,
        landmarks=(PoseLandmark(x=0.5, y=0.4, z=-0.1, visibility=confidence),),
        angles={"left_knee": 92.0},
        confidence=confidence,
    )


def test_latest_frame_slot_delivers_only_newest_and_counts_overwrites():
    slot: LatestFrameSlot[str] = LatestFrameSlot()
    slot.publish("old")
    slot.publish("newer")
    generation = slot.publish("newest")

    assert generation == 3
    assert slot.wait_after(0, timeout_s=0.01) == (3, "newest", 2)


def test_latest_frame_slot_close_is_terminal_and_does_not_fabricate_data():
    slot: LatestFrameSlot[str] = LatestFrameSlot()
    slot.close()

    assert slot.wait_after(0, timeout_s=0.01) is None
    with pytest.raises(RuntimeError, match="closed"):
        slot.publish("late")


def test_good_pose_builds_canonical_measurement_time_sample():
    result = build_pose_sample(
        camera_id="picam0",
        frame=_frame(),
        evaluation=_found_pose(),
        processed_monotonic_ns=1_500_000,
        frames_dropped_since_previous=3,
        minimum_confidence=0.7,
    )

    assert result.reason_code is ReasonCode.OK
    assert result.sample.quality is Quality.GOOD
    assert result.sample.captured_monotonic_ns == 1_000_000
    assert result.sample.processed_monotonic_ns == 1_500_000
    assert result.sample.processing_latency_ns == 500_000
    assert result.sample.frames_dropped_since_previous == 3
    assert result.sample.image_width == 640
    assert result.sample.image_height == 360


def test_missing_pose_is_explicit_and_never_synthetic():
    result = build_pose_sample(
        camera_id="picam0",
        frame=_frame(),
        evaluation=PoseEvaluation(
            found=False,
            landmarks=(),
            angles={},
            confidence=0.0,
        ),
        processed_monotonic_ns=1_500_000,
        frames_dropped_since_previous=0,
        minimum_confidence=0.7,
    )

    assert result.reason_code is ReasonCode.POSE_NOT_FOUND
    assert result.sample.quality is Quality.VISION_DEGRADED
    assert result.sample.landmarks == ()
    assert result.sample.angles == {}
    assert result.sample.pose_confidence == 0.0


def test_low_visibility_pose_preserves_measurement_but_degrades_quality():
    result = build_pose_sample(
        camera_id="picam0",
        frame=_frame(),
        evaluation=_found_pose(confidence=0.3),
        processed_monotonic_ns=1_500_000,
        frames_dropped_since_previous=0,
        minimum_confidence=0.7,
    )

    assert result.reason_code is ReasonCode.POSE_LOW_VISIBILITY
    assert result.sample.quality is Quality.VISION_DEGRADED
    assert len(result.sample.landmarks) == 1


def test_pose_builder_rejects_arrival_time_as_capture_time():
    with pytest.raises(PoseEventError, match="measurement-time"):
        build_pose_sample(
            camera_id="picam0",
            frame=_frame(captured_ns=None),
            evaluation=_found_pose(),
            processed_monotonic_ns=1_500_000,
            frames_dropped_since_previous=0,
            minimum_confidence=0.7,
        )


def test_pose_evaluation_rejects_inconsistent_missing_and_found_states():
    landmark = PoseLandmark(x=0.5, y=0.4, z=0.0, visibility=0.9)
    with pytest.raises(ValueError, match="missing pose"):
        PoseEvaluation(
            found=False,
            landmarks=(landmark,),
            angles={},
            confidence=0.0,
        )
    with pytest.raises(ValueError, match="found pose"):
        PoseEvaluation(found=True, landmarks=(), angles={}, confidence=0.9)


def test_pose_envelope_uses_shared_contract_and_round_trips():
    result = build_pose_sample(
        camera_id="picam0",
        frame=_frame(),
        evaluation=_found_pose(),
        processed_monotonic_ns=1_500_000,
        frames_dropped_since_previous=0,
        minimum_confidence=0.7,
    )
    envelope = build_pose_envelope(
        result=result,
        event_id=EVENT_ID,
        created_monotonic_ns=1_600_000,
        device_id="pi-camera-001",
    )

    assert envelope.source is Source.VISION
    assert envelope.captured_monotonic_ns == result.sample.captured_monotonic_ns
    assert envelope.quality is Quality.GOOD
    assert EventEnvelope[PoseSample].from_messagepack(envelope.to_messagepack()) == envelope
