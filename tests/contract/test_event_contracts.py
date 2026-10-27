from __future__ import annotations

from typing import get_type_hints
from uuid import UUID, uuid4

import msgpack
import pytest
from pydantic import ValidationError

from digital_spotter.contracts import (
    MAX_EVENT_BYTES,
    SCHEMA_VERSION_V1,
    AnalysisEvent,
    ClockState,
    ComponentState,
    ContractDecodeError,
    EventEnvelope,
    EventType,
    FusedSample,
    HealthState,
    IMUSample,
    InterpolatedIMU,
    MonotonicClock,
    MonotonicNanoseconds,
    PoseLandmark,
    PoseSample,
    Quality,
    ReasonCode,
    RepEvent,
    RepPhase,
    RepTransition,
    Source,
    UtcClock,
    UtcMilliseconds,
    new_event_id,
)


EVENT_ID = new_event_id(unix_time_ms=1_750_000_000_000, random_bits=42)
SESSION_ID = UUID("11111111-1111-4111-8111-111111111111")
PAYLOAD_ID = UUID("22222222-2222-4222-8222-222222222222")


def _imu() -> IMUSample:
    return IMUSample(
        device_id="imu-test-001",
        boot_id=7,
        sequence=12,
        sensor_time_us=123_000,
        captured_monotonic_ns=MonotonicNanoseconds(2_000_000),
        arrival_monotonic_ns=MonotonicNanoseconds(2_100_000),
        acceleration_m_s2=(0.1, 9.8, -0.2),
        angular_velocity_rad_s=(0.01, 0.02, 0.03),
        calibration_version=3,
        quality=Quality.GOOD,
        gap_count_since_previous=0,
        estimated_clock_error_ns=50_000,
        clock_state=ClockState.SYNCHRONIZED,
    )


def _pose() -> PoseSample:
    return PoseSample(
        camera_id="picam0",
        frame_sequence=9,
        captured_monotonic_ns=MonotonicNanoseconds(2_000_000),
        processed_monotonic_ns=MonotonicNanoseconds(2_500_000),
        image_width=640,
        image_height=360,
        landmark_schema_version=1,
        landmarks=(PoseLandmark(x=0.5, y=0.5, z=-0.1, visibility=0.9),),
        angles={"left_knee": 91.0},
        pose_confidence=0.9,
        quality=Quality.GOOD,
        processing_latency_ns=500_000,
        frames_dropped_since_previous=2,
    )


def _payloads():
    return [
        (EventType.IMU_SAMPLE, Source.IMU, _imu()),
        (EventType.POSE_SAMPLE, Source.VISION, _pose()),
        (
            EventType.FUSED_SAMPLE,
            Source.CORE,
            FusedSample(
                pose_event_id=PAYLOAD_ID,
                captured_monotonic_ns=MonotonicNanoseconds(2_000_000),
                interpolated_imu=InterpolatedIMU(
                    acceleration_m_s2=(0.1, 9.8, -0.2),
                    angular_velocity_rad_s=(0.01, 0.02, 0.03),
                ),
                imu_before_sequence=11,
                imu_after_sequence=12,
                alignment_error_ns=100_000,
                calibration_version=3,
                quality=Quality.GOOD,
            ),
        ),
        (
            EventType.REP_EVENT,
            Source.CORE,
            RepEvent(
                rep_id=PAYLOAD_ID,
                rep_number=1,
                exercise_contract_version="squat-1.0.0",
                event=RepTransition.PHASE,
                phase=RepPhase.BOTTOM,
                captured_monotonic_ns=MonotonicNanoseconds(2_000_000),
                quality=Quality.GOOD,
            ),
        ),
        (
            EventType.ANALYSIS_EVENT,
            Source.CORE,
            AnalysisEvent(
                analysis_id=PAYLOAD_ID,
                rep_id=SESSION_ID,
                model_package_id="compat-v4",
                model_version="4.0.0",
                feature_contract_version="1.0.0",
                input_hash="a" * 64,
                label="good_form",
                bad_form_probability=0.1,
                threshold=0.359,
                latency_ns=2_000_000,
                quality=Quality.GOOD,
            ),
        ),
        (
            EventType.HEALTH_STATE,
            Source.CORE,
            HealthState(
                component="core",
                state=ComponentState.DEGRADED,
                reason_codes=(ReasonCode.IMU_UNAVAILABLE,),
                since_monotonic_ns=MonotonicNanoseconds(1_900_000),
                versions={"software": "0.1.0"},
                counters={"imu_reconnects": 1},
                is_simulated=False,
            ),
        ),
    ]


@pytest.mark.parametrize(("event_type", "source", "payload"), _payloads())
def test_all_v1_events_round_trip_with_bounded_messagepack(event_type, source, payload):
    envelope_type = EventEnvelope[type(payload)]
    envelope = envelope_type(
        schema_version=SCHEMA_VERSION_V1,
        event_type=event_type,
        event_id=EVENT_ID,
        source=source,
        device_id="device-test-001",
        session_id=SESSION_ID,
        captured_monotonic_ns=getattr(payload, "captured_monotonic_ns", None),
        created_monotonic_ns=MonotonicNanoseconds(2_600_000),
        created_utc_ms=UtcMilliseconds(1_750_000_000_000),
        quality=payload.quality if hasattr(payload, "quality") else Quality.GOOD,
        payload=payload,
    )

    encoded = envelope.to_messagepack()
    decoded = envelope_type.from_messagepack(encoded)

    assert len(encoded) <= MAX_EVENT_BYTES
    assert decoded == envelope


def test_event_type_must_match_payload():
    with pytest.raises(ValidationError, match="event_type does not match"):
        EventEnvelope[IMUSample](
            event_type=EventType.POSE_SAMPLE,
            event_id=EVENT_ID,
            source=Source.IMU,
            created_monotonic_ns=MonotonicNanoseconds(1),
            quality=Quality.GOOD,
            payload=_imu(),
        )


def test_envelope_quality_and_time_must_match_payload():
    base = {
        "event_type": EventType.IMU_SAMPLE,
        "event_id": EVENT_ID,
        "source": Source.IMU,
        "captured_monotonic_ns": MonotonicNanoseconds(2_000_000),
        "created_monotonic_ns": MonotonicNanoseconds(2_600_000),
        "quality": Quality.GOOD,
        "payload": _imu(),
    }
    with pytest.raises(ValidationError, match="quality differ"):
        EventEnvelope[IMUSample](**{**base, "quality": Quality.IMU_DEGRADED})
    with pytest.raises(ValidationError, match="cannot precede capture"):
        EventEnvelope[IMUSample](
            **{**base, "created_monotonic_ns": MonotonicNanoseconds(1_999_999)}
        )


def test_wrong_schema_and_non_uuid7_are_rejected():
    base = {
        "event_type": EventType.IMU_SAMPLE,
        "event_id": EVENT_ID,
        "source": Source.IMU,
        "created_monotonic_ns": MonotonicNanoseconds(1),
        "quality": Quality.GOOD,
        "payload": _imu(),
    }
    with pytest.raises(ValidationError, match="unsupported event schema"):
        EventEnvelope[IMUSample](schema_version=0x0200, **base)
    with pytest.raises(ValidationError, match="UUIDv7"):
        EventEnvelope[IMUSample](**{**base, "event_id": uuid4()})


def test_malformed_and_oversized_messagepack_are_rejected():
    envelope_type = EventEnvelope[IMUSample]
    with pytest.raises(ContractDecodeError, match="invalid event"):
        envelope_type.from_messagepack(msgpack.packb({"schema_version": SCHEMA_VERSION_V1}))
    with pytest.raises(ContractDecodeError, match="exceeds"):
        envelope_type.from_messagepack(b"x" * (MAX_EVENT_BYTES + 1))
    with pytest.raises(ContractDecodeError, match="root must be a map"):
        envelope_type.from_messagepack(msgpack.packb([1, 2, 3]))


def test_nonfinite_vectors_and_clock_inversion_are_rejected():
    values = _imu().model_dump()
    values["acceleration_m_s2"] = (float("nan"), 0.0, 0.0)
    with pytest.raises(ValidationError):
        IMUSample.model_validate(values)

    values = _imu().model_dump()
    values["arrival_monotonic_ns"] = values["captured_monotonic_ns"] - 1
    with pytest.raises(ValidationError, match="cannot precede"):
        IMUSample.model_validate(values)


def test_monotonic_and_utc_clock_apis_are_distinct_types():
    monotonic_return = get_type_hints(MonotonicClock.now_ns)["return"]
    utc_return = get_type_hints(UtcClock.now_ms)["return"]

    assert monotonic_return is MonotonicNanoseconds
    assert utc_return is UtcMilliseconds
    assert monotonic_return is not utc_return


def test_uuid7_generation_is_deterministic_with_injected_sources():
    first = new_event_id(unix_time_ms=1_750_000_000_000, random_bits=42)
    second = new_event_id(unix_time_ms=1_750_000_000_000, random_bits=42)

    assert first == second
    assert first.version == 7
    assert first.variant == "specified in RFC 4122"
