"""Focused measurement-time fusion checks; no hardware or model execution."""

from __future__ import annotations

from digital_spotter.contracts import (
    ClockState,
    EventEnvelope,
    EventType,
    IMUSample,
    MonotonicNanoseconds,
    PoseLandmark,
    PoseSample,
    Quality,
    ReasonCode,
    Source,
    new_event_id,
)
from digital_spotter.core.fusion import FusionEngine


def _imu(
    sequence: int,
    captured_ns: int,
    acceleration_x: float,
    *,
    arrival_ns: int | None = None,
    boot_id: int = 1,
    gap_count: int = 0,
    clock_state: ClockState = ClockState.SYNCHRONIZED,
    calibration_version: int = 1,
    quality: Quality = Quality.GOOD,
) -> EventEnvelope[IMUSample]:
    captured = MonotonicNanoseconds(captured_ns)
    arrival = MonotonicNanoseconds(arrival_ns or captured_ns)
    sample = IMUSample(
        device_id="dsimu-fusion-test",
        boot_id=boot_id,
        sequence=sequence,
        sensor_time_us=sequence * 20_000,
        captured_monotonic_ns=captured,
        arrival_monotonic_ns=arrival,
        acceleration_m_s2=(acceleration_x, 0.0, 0.0),
        angular_velocity_rad_s=(acceleration_x / 10.0, 0.0, 0.0),
        calibration_version=calibration_version,
        quality=quality,
        gap_count_since_previous=gap_count,
        estimated_clock_error_ns=1_000_000,
        clock_state=clock_state,
    )
    return EventEnvelope[IMUSample](
        event_type=EventType.IMU_SAMPLE,
        event_id=new_event_id(unix_time_ms=1_750_000_000_000 + sequence, random_bits=sequence),
        source=Source.IMU,
        device_id=sample.device_id,
        captured_monotonic_ns=captured,
        created_monotonic_ns=arrival,
        quality=quality,
        payload=sample,
    )


def _pose(captured_ns: int = 110_000_000, *, quality: Quality = Quality.GOOD) -> EventEnvelope[PoseSample]:
    captured = MonotonicNanoseconds(captured_ns)
    processed = MonotonicNanoseconds(captured_ns + 2_000_000)
    sample = PoseSample(
        camera_id="fusion-camera",
        frame_sequence=1,
        captured_monotonic_ns=captured,
        processed_monotonic_ns=processed,
        image_width=640,
        image_height=480,
        landmark_schema_version=1,
        landmarks=(PoseLandmark(x=0.5, y=0.5, z=0.0, visibility=1.0),),
        angles={},
        pose_confidence=1.0,
        quality=quality,
        processing_latency_ns=2_000_000,
    )
    return EventEnvelope[PoseSample](
        event_type=EventType.POSE_SAMPLE,
        event_id=new_event_id(unix_time_ms=1_750_000_001_000, random_bits=1000),
        source=Source.VISION,
        device_id="pi-fusion-test",
        captured_monotonic_ns=captured,
        created_monotonic_ns=processed,
        quality=quality,
        payload=sample,
    )


def test_interpolates_by_capture_time_even_when_arrival_is_misleading() -> None:
    before = _imu(10, 100_000_000, 0.0, arrival_ns=300_000_000)
    after = _imu(11, 120_000_000, 10.0, arrival_ns=301_000_000)

    outcome = FusionEngine().fuse(_pose(), (before, after), now_monotonic_ns=310_000_000)

    assert outcome.quality is Quality.GOOD
    assert outcome.reasons == ()
    assert outcome.sample is not None
    assert outcome.sample.interpolated_imu.acceleration_m_s2 == (5.0, 0.0, 0.0)
    assert outcome.sample.interpolated_imu.angular_velocity_rad_s == (0.5, 0.0, 0.0)
    assert outcome.sample.imu_before_sequence == 10
    assert outcome.sample.imu_after_sequence == 11
    assert outcome.sample.captured_monotonic_ns == 110_000_000


def test_missing_or_far_imu_never_becomes_zero_filled_fused_sample() -> None:
    engine = FusionEngine()
    missing = engine.fuse(_pose(), (), now_monotonic_ns=120_000_000)
    far = engine.fuse(
        _pose(),
        (_imu(1, 20_000_000, 1.0), _imu(2, 40_000_000, 2.0)),
        now_monotonic_ns=120_000_000,
    )

    assert missing.sample is None and missing.reasons == (ReasonCode.IMU_UNAVAILABLE,)
    assert far.sample is None and ReasonCode.IMU_STALE in far.reasons


def test_gap_clock_reset_and_pose_staleness_are_explicit() -> None:
    engine = FusionEngine()
    before = _imu(10, 100_000_000, 0.0)
    gap = engine.fuse(
        _pose(),
        (before, _imu(12, 120_000_000, 10.0, gap_count=1)),
        now_monotonic_ns=130_000_000,
    )
    reset = engine.fuse(
        _pose(),
        (before, _imu(11, 120_000_000, 10.0, boot_id=2, clock_state=ClockState.RESET)),
        now_monotonic_ns=130_000_000,
    )
    old_pose = engine.fuse(_pose(), (before,), now_monotonic_ns=500_000_000)

    assert gap.sample is None and ReasonCode.IMU_GAP_RATE_HIGH in gap.reasons
    assert reset.sample is None and ReasonCode.CLOCK_UNSYNCHRONIZED in reset.reasons
    assert old_pose.sample is None and ReasonCode.POSE_STALE in old_pose.reasons


def test_uncalibrated_imu_and_degraded_pose_cannot_be_good() -> None:
    outcome = FusionEngine().fuse(
        _pose(quality=Quality.VISION_DEGRADED),
        (
            _imu(10, 100_000_000, 0.0, calibration_version=0, quality=Quality.IMU_DEGRADED),
            _imu(11, 120_000_000, 10.0, calibration_version=0, quality=Quality.IMU_DEGRADED),
        ),
        now_monotonic_ns=130_000_000,
    )

    assert outcome.sample is not None
    assert outcome.quality is not Quality.GOOD
    assert ReasonCode.CALIBRATION_REQUIRED in outcome.reasons
    assert ReasonCode.POSE_LOW_VISIBILITY in outcome.reasons
    assert outcome.sample.quality is outcome.quality
