from __future__ import annotations

import pytest

from digital_spotter.contracts import ClockState, MonotonicNanoseconds, Quality
from digital_spotter.imu.protocol import IMUFlags, IMUProtocolError, encode_imu_packet
from digital_spotter.imu.r9_agent import R9AgentCore, R9ConnectionState
from digital_spotter.imu.r9_protocol import EXPECTED_DEVICE_INFO


def _status(*, uptime_ms: int = 1000, samples_sent: int = 0, errors: int = 0) -> bytes:
    return (
        f"state=streaming;i2c_errors={errors};samples_sent={samples_sent};"
        f"uptime_ms={uptime_ms}"
    ).encode("ascii")


def _packet(*, sequence: int, sensor_time_us: int) -> bytes:
    return encode_imu_packet(
        flags=IMUFlags(0),
        sequence=sequence,
        sensor_time_us=sensor_time_us,
        acceleration_raw=(0, 16_384, 0),
        angular_velocity_raw=(0, 0, 0),
    )


def _ready_core() -> R9AgentCore:
    core = R9AgentCore(device_id="dsimu-r9-test", initial_boot_id=42)
    core.mark_connected()
    core.accept_device_info(EXPECTED_DEVICE_INFO)
    core.accept_status(_status())
    core.mark_streaming(True)
    return core


def test_r9_core_emits_real_uncalibrated_latest_sample_and_rate():
    core = _ready_core()
    first = core.accept_packet(
        _packet(sequence=10, sensor_time_us=20_000),
        arrival_monotonic_ns=MonotonicNanoseconds(1_000_000_000),
    )
    second = core.accept_packet(
        _packet(sequence=11, sensor_time_us=40_000),
        arrival_monotonic_ns=MonotonicNanoseconds(1_020_000_000),
    )
    third = core.accept_packet(
        _packet(sequence=12, sensor_time_us=60_000),
        arrival_monotonic_ns=MonotonicNanoseconds(1_040_000_000),
    )

    assert first is not None and second is not None and third is not None
    assert third.payload.boot_id == 42
    assert third.payload.quality is Quality.IMU_DEGRADED
    assert third.payload.clock_state is ClockState.ACQUIRING
    assert third.payload.acceleration_m_s2[1] == pytest.approx(9.80665)
    assert core.latest.get() == third
    assert core.latest.version == 3
    health = core.health(now_monotonic_ns=1_045_000_000)
    assert health.state is R9ConnectionState.STREAMING
    assert health.sample_rate_hz == pytest.approx(50.0)
    assert health.latest_sample_age_ms == pytest.approx(5.0)
    assert health.latest_sequence == 12
    assert health.is_simulated is False


def test_r9_core_counts_wrap_gap_duplicate_rejection_and_staleness():
    core = _ready_core()
    core.accept_packet(
        _packet(sequence=65534, sensor_time_us=1),
        arrival_monotonic_ns=MonotonicNanoseconds(1_000_000_000),
    )
    gap = core.accept_packet(
        _packet(sequence=1, sensor_time_us=2),
        arrival_monotonic_ns=MonotonicNanoseconds(1_020_000_000),
    )
    assert gap is not None and gap.payload.gap_count_since_previous == 2
    assert core.accept_packet(
        _packet(sequence=1, sensor_time_us=2),
        arrival_monotonic_ns=MonotonicNanoseconds(1_021_000_000),
    ) is None
    with pytest.raises(IMUProtocolError, match="backward"):
        core.accept_packet(
            _packet(sequence=65535, sensor_time_us=3),
            arrival_monotonic_ns=MonotonicNanoseconds(1_022_000_000),
        )

    counters = core.counters()
    assert counters.sequence_gaps == 2
    assert counters.packets_duplicate == 1
    assert counters.packets_rejected == 1
    assert core.health(now_monotonic_ns=1_500_000_000).state is R9ConnectionState.DEGRADED


def test_r9_core_detects_esp_reboot_from_status_regression():
    core = _ready_core()
    before = core.accept_packet(
        _packet(sequence=100, sensor_time_us=2_000_000),
        arrival_monotonic_ns=MonotonicNanoseconds(1_000_000_000),
    )
    assert before is not None and before.payload.boot_id == 42

    core.accept_status(_status(uptime_ms=50, samples_sent=0))
    after = core.accept_packet(
        _packet(sequence=0, sensor_time_us=20_000),
        arrival_monotonic_ns=MonotonicNanoseconds(1_100_000_000),
    )

    assert after is not None
    assert after.payload.boot_id == 43
    assert after.payload.clock_state is ClockState.RESET
    assert core.counters().clock_resets == 1


def test_r9_core_accepts_firmware_sequence_restart_for_new_stream():
    core = _ready_core()
    before = core.accept_packet(
        _packet(sequence=100, sensor_time_us=2_000_000),
        arrival_monotonic_ns=MonotonicNanoseconds(1_000_000_000),
    )
    core.begin_stream()
    after = core.accept_packet(
        _packet(sequence=0, sensor_time_us=2_020_000),
        arrival_monotonic_ns=MonotonicNanoseconds(1_020_000_000),
    )

    assert before is not None and after is not None
    assert after.payload.boot_id == before.payload.boot_id
    assert after.payload.sequence == 0
    assert after.payload.clock_state is ClockState.ACQUIRING
    assert core.counters().packets_rejected == 0
    assert core.counters().clock_resets == 0


def test_r9_i2c_error_is_explicitly_degraded():
    core = _ready_core()
    core.accept_status(_status(errors=2))

    health = core.health(now_monotonic_ns=1)

    assert health.state is R9ConnectionState.DEGRADED
    assert health.i2c_errors == 2


def test_r9_status_reads_synchronize_packet_capture_into_pi_clock_domain():
    core = _ready_core()
    intercept_ns = 10_000_000_000
    for index in range(6):
        uptime_ms = 2_000 + index * 1_000
        sensor_us = uptime_ms * 1000
        pi_mid_ns = intercept_ns + sensor_us * 1000
        core.accept_status_exchange(
            _status(uptime_ms=uptime_ms, samples_sent=index),
            t1_pi_ns=MonotonicNanoseconds(pi_mid_ns - 2_000_000),
            t4_pi_ns=MonotonicNanoseconds(pi_mid_ns + 2_000_000),
        )

    sensor_us = 7_020_000
    expected_capture_ns = intercept_ns + sensor_us * 1000
    arrival_ns = MonotonicNanoseconds(expected_capture_ns + 3_000_000)
    event = core.accept_packet(
        _packet(sequence=1, sensor_time_us=sensor_us),
        arrival_monotonic_ns=arrival_ns,
    )

    assert event is not None
    assert event.payload.clock_state is ClockState.SYNCHRONIZED
    assert event.payload.captured_monotonic_ns == pytest.approx(
        expected_capture_ns,
        abs=2,
    )
    assert event.payload.captured_monotonic_ns < event.payload.arrival_monotonic_ns
    assert event.payload.estimated_clock_error_ns == pytest.approx(3_000_000, abs=2)
    # The unchanged R9 sample remains uncalibrated even after its clock is usable.
    assert event.quality is Quality.IMU_DEGRADED
    health = core.health(now_monotonic_ns=int(arrival_ns))
    assert health.clock_state is ClockState.SYNCHRONIZED
    assert health.clock_fit_points == 6
    assert health.counters.clock_exchanges_accepted == 6
    assert health.counters.clock_exchanges_rejected == 0


def test_r9_high_rtt_status_exchange_is_rejected_and_quality_fails_closed():
    core = _ready_core()
    core.accept_status_exchange(
        _status(uptime_ms=2_000),
        t1_pi_ns=MonotonicNanoseconds(10_000_000_000),
        t4_pi_ns=MonotonicNanoseconds(10_100_000_000),
    )
    event = core.accept_packet(
        _packet(sequence=1, sensor_time_us=2_020_000),
        arrival_monotonic_ns=MonotonicNanoseconds(10_120_000_000),
    )

    assert event is not None
    assert event.payload.clock_state is ClockState.ACQUIRING
    assert event.payload.estimated_clock_error_ns == 50_000_000
    assert event.quality is not Quality.GOOD
    assert core.counters().clock_exchanges_accepted == 0
    assert core.counters().clock_exchanges_rejected == 1
