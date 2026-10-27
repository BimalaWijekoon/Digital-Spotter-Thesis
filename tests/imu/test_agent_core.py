from __future__ import annotations

from uuid import UUID

import pytest

from digital_spotter.contracts import (
    ClockState,
    EventEnvelope,
    IMUSample,
    MonotonicNanoseconds,
    Quality,
)
from digital_spotter.imu import (
    FakeWearable,
    IMUAgentCore,
    IMUFlags,
    IMUProtocolError,
    UDSFrameError,
    decode_event_frame,
    encode_event_frame,
)


def _ready_agent(*, max_buffer_samples: int = 3):
    fake = FakeWearable()
    agent = IMUAgentCore(
        expected_device_id=fake.device_id,
        max_buffer_samples=max_buffer_samples,
    )
    agent.set_session(UUID("11111111-1111-4111-8111-111111111111"))
    agent.accept_device_info(fake.device_info())
    agent.accept_status(fake.status())
    return fake, agent


def test_fake_and_agent_identity_cannot_be_confused():
    fake, agent = _ready_agent()

    assert fake.is_real is False
    assert fake.is_simulated is True
    assert fake.persistence_allowed is False
    assert agent.is_real is True
    assert agent.is_simulated is False


def test_agent_emits_bounded_v1_event_and_uds_round_trip():
    fake, agent = _ready_agent()
    event = agent.accept_packet(
        fake.packet(sequence=1, sensor_time_us=20_000),
        arrival_monotonic_ns=MonotonicNanoseconds(1_000_000),
    )

    assert event is not None
    assert event.payload.acceleration_m_s2[1] == pytest.approx(9.80665)
    assert event.payload.clock_state is ClockState.ACQUIRING
    assert event.quality is Quality.UNSYNCHRONIZED
    frame = encode_event_frame(event)
    assert decode_event_frame(frame, EventEnvelope[IMUSample]) == event


def test_agent_counts_gap_duplicate_reset_rejection_and_eviction():
    fake, agent = _ready_agent(max_buffer_samples=2)
    assert agent.accept_packet(
        fake.packet(sequence=10, sensor_time_us=10),
        arrival_monotonic_ns=MonotonicNanoseconds(1),
    ) is not None
    gap = agent.accept_packet(
        fake.packet(sequence=13, sensor_time_us=20),
        arrival_monotonic_ns=MonotonicNanoseconds(2),
    )
    assert gap is not None
    assert gap.payload.gap_count_since_previous == 2
    assert gap.quality is Quality.IMU_DEGRADED
    assert agent.accept_packet(
        fake.packet(sequence=13, sensor_time_us=20),
        arrival_monotonic_ns=MonotonicNanoseconds(3),
    ) is None

    fake.boot_id = 2
    agent.accept_status(fake.status())
    reset = agent.accept_packet(
        fake.packet(sequence=0, sensor_time_us=1),
        arrival_monotonic_ns=MonotonicNanoseconds(4),
    )
    assert reset is not None
    assert reset.payload.clock_state is ClockState.RESET
    assert agent.counters().sequence_gaps == 2
    assert agent.counters().clock_resets == 1
    assert agent.counters().packets_duplicate == 1
    assert agent.counters().packets_evicted == 1

    with pytest.raises(IMUProtocolError):
        agent.accept_packet(
            b"bad",
            arrival_monotonic_ns=MonotonicNanoseconds(5),
        )
    assert agent.counters().packets_rejected == 1


def test_sensor_flags_never_silently_become_good_quality():
    fake, agent = _ready_agent()
    saturated = agent.accept_packet(
        fake.packet(
            sequence=1,
            sensor_time_us=1,
            flags=IMUFlags.CALIBRATED | IMUFlags.SATURATED,
        ),
        arrival_monotonic_ns=MonotonicNanoseconds(1),
    )
    assert saturated is not None and saturated.quality is Quality.IMU_DEGRADED

    sensor_error = agent.accept_packet(
        fake.packet(sequence=2, sensor_time_us=2, flags=IMUFlags.SENSOR_ERROR),
        arrival_monotonic_ns=MonotonicNanoseconds(2),
    )
    assert sensor_error is not None and sensor_error.quality is Quality.UNAVAILABLE


def test_unprovisioned_or_contradictory_identity_is_rejected():
    fake = FakeWearable(device_id="imu-other-001")
    agent = IMUAgentCore(expected_device_id="imu-expected-001")
    with pytest.raises(IMUProtocolError, match="identity"):
        agent.accept_device_info(fake.device_info())
    with pytest.raises(IMUProtocolError, match="required before samples"):
        agent.accept_packet(
            fake.packet(sequence=1, sensor_time_us=1),
            arrival_monotonic_ns=MonotonicNanoseconds(1),
        )


def test_uds_frame_rejects_truncation_and_length_tampering():
    fake, agent = _ready_agent()
    event = agent.accept_packet(
        fake.packet(sequence=1, sensor_time_us=1),
        arrival_monotonic_ns=MonotonicNanoseconds(1),
    )
    frame = encode_event_frame(event)

    with pytest.raises(UDSFrameError, match="truncated"):
        decode_event_frame(b"", EventEnvelope[IMUSample])
    with pytest.raises(UDSFrameError, match="does not match"):
        decode_event_frame(frame[:-1], EventEnvelope[IMUSample])
