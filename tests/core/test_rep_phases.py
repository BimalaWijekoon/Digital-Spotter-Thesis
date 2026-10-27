"""Small deterministic replay of the FYP video's three-phase rule."""

from __future__ import annotations

import math
import pytest

from digital_spotter.contracts import (
    ClockState,
    EventEnvelope,
    EventType,
    IMUSample,
    MonotonicNanoseconds,
    PoseLandmark,
    PoseSample,
    Quality,
    Source,
    new_event_id,
)
from digital_spotter.core.rep_phases import RepPhaseBuilder


def _pose(
    frame: int,
    knee_flexion_deg: float,
    *,
    quality: Quality = Quality.GOOD,
    left_visibility: float = 1.0,
    right_visibility: float = 1.0,
) -> EventEnvelope[PoseSample]:
    theta = math.radians(knee_flexion_deg)
    landmarks = [PoseLandmark(x=0.5, y=0.5, z=0.0, visibility=1.0) for _ in range(33)]
    for (shoulder, hip, knee, ankle, foot), visibility in zip(
        ((11, 23, 25, 27, 31), (12, 24, 26, 28, 32)),
        (left_visibility, right_visibility),
    ):
        landmarks[shoulder] = PoseLandmark(x=0.5, y=0.2, z=0, visibility=visibility)
        landmarks[hip] = PoseLandmark(x=0.5, y=0.4, z=0, visibility=visibility)
        landmarks[knee] = PoseLandmark(x=0.5, y=0.6, z=0, visibility=visibility)
        landmarks[ankle] = PoseLandmark(
            x=0.5 + 0.2 * math.sin(theta),
            y=0.6 + 0.2 * math.cos(theta),
            z=0,
            visibility=visibility,
        )
        landmarks[foot] = PoseLandmark(x=0.5, y=0.9, z=0, visibility=visibility)
    captured = MonotonicNanoseconds(1_000_000_000 + frame * 40_000_000)
    processed = MonotonicNanoseconds(int(captured) + 5_000_000)
    sample = PoseSample(
        camera_id="research-camera",
        frame_sequence=frame,
        captured_monotonic_ns=captured,
        processed_monotonic_ns=processed,
        image_width=640,
        image_height=360,
        landmark_schema_version=1,
        landmarks=tuple(landmarks),
        angles={},
        pose_confidence=1,
        quality=quality,
        processing_latency_ns=5_000_000,
    )
    return EventEnvelope[PoseSample](
        event_type=EventType.POSE_SAMPLE,
        event_id=new_event_id(unix_time_ms=1_750_000_000_000 + frame, random_bits=frame),
        source=Source.VISION,
        device_id="pi-research",
        captured_monotonic_ns=captured,
        created_monotonic_ns=processed,
        quality=quality,
        payload=sample,
    )


def _imu(sequence: int) -> EventEnvelope[IMUSample]:
    captured = MonotonicNanoseconds(1_000_000_000 + sequence * 20_000_000)
    sample = IMUSample(
        device_id="dsimu-research",
        boot_id=1,
        sequence=sequence,
        sensor_time_us=sequence * 20_000,
        captured_monotonic_ns=captured,
        arrival_monotonic_ns=captured,
        acceleration_m_s2=(1.0, 2.0, 9.0),
        angular_velocity_rad_s=(0.1, 0.2, 0.3),
        calibration_version=1,
        quality=Quality.GOOD,
        gap_count_since_previous=0,
        estimated_clock_error_ns=1_000_000,
        clock_state=ClockState.SYNCHRONIZED,
    )
    return EventEnvelope[IMUSample](
        event_type=EventType.IMU_SAMPLE,
        event_id=new_event_id(unix_time_ms=1_750_000_001_000 + sequence, random_bits=sequence),
        source=Source.IMU,
        device_id=sample.device_id,
        captured_monotonic_ns=captured,
        created_monotonic_ns=captured,
        quality=Quality.GOOD,
        payload=sample,
    )


@pytest.mark.parametrize(
    ("exercise_id", "expected_names"),
    [
        (0, ("Descent", "Bottom", "Lockout")),
        (1, ("Setup", "Mid-pull", "Lockout")),
    ],
)
def test_one_completed_rep_has_three_ordered_median_phases_once(
    exercise_id: int, expected_names: tuple[str, str, str]
) -> None:
    builder = RepPhaseBuilder(exercise_id=exercise_id, fps=25)
    angles = [0] * 9 + [10, 20, 35, 50, 70, 90, 110, 125, 140, 125, 110, 90, 70, 50, 35, 20, 10] + [0] * 9
    for frame, angle in enumerate(angles):
        builder.add(_pose(frame, angle))

    completed = builder.poll(tuple(_imu(i) for i in range(80)))

    assert len(completed) == 1
    rep = completed[0]
    assert rep.event.rep_number == 1
    assert rep.event.quality is Quality.GOOD
    assert [(phase.phase, phase.name) for phase in rep.phases] == list(enumerate(expected_names, 1))
    assert all(phase.frame_count > 0 for phase in rep.phases)
    assert all(phase.imu is not None for phase in rep.phases)
    assert rep.phases[1].vision["Angle_Knee_Flexion_L"] > rep.phases[0].vision["Angle_Knee_Flexion_L"]
    assert builder.poll(tuple(_imu(i) for i in range(80))) == ()


def test_no_peak_does_not_fabricate_a_deadlift_rep() -> None:
    builder = RepPhaseBuilder(exercise_id=1, fps=25)
    for frame in range(35):
        builder.add(_pose(frame, 0))

    assert builder.poll(tuple(_imu(i) for i in range(80))) == ()


def test_missing_imu_does_not_become_a_good_or_zero_filled_rep() -> None:
    builder = RepPhaseBuilder(exercise_id=0, fps=25)
    angles = [0] * 9 + [10, 20, 35, 50, 70, 90, 110, 125, 140, 125, 110, 90, 70, 50, 35, 20, 10] + [0] * 9
    for frame, angle in enumerate(angles):
        builder.add(_pose(frame, angle))

    completed = builder.poll(())

    assert len(completed) == 1
    assert completed[0].event.quality is Quality.UNAVAILABLE
    assert all(phase.imu is None for phase in completed[0].phases)


def test_tracking_good_one_side_counts_rep_without_authorizing_model_features() -> None:
    builder = RepPhaseBuilder(exercise_id=0, fps=25)
    angles = [0] * 9 + [10, 20, 35, 50, 70, 90, 110, 125, 140, 125, 110, 90, 70, 50, 35, 20, 10] + [0] * 9
    for frame, angle in enumerate(angles):
        builder.add(_pose(
            frame,
            angle,
            quality=Quality.GOOD,
            left_visibility=0.8,
            right_visibility=0.2,
        ))

    completed = builder.poll(tuple(_imu(i) for i in range(80)))

    assert len(completed) == 1
    assert completed[0].event.rep_number == 1
    assert completed[0].event.quality is Quality.UNAVAILABLE
    assert all(phase.quality is Quality.UNAVAILABLE for phase in completed[0].phases)
    assert all(phase.frame_count == 0 for phase in completed[0].phases)
    assert all(phase.vision == {} for phase in completed[0].phases)
