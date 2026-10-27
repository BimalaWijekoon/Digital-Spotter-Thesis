from __future__ import annotations

import pytest

from digital_spotter.contracts import ClockState, MonotonicNanoseconds
from digital_spotter.imu import FakeWearable, IMUAgentCore, SensorClockMapper


def _train(
    mapper: SensorClockMapper,
    *,
    boot_id: int = 1,
    start_sensor_us: int = 100_000,
    drift_ppm: float = 100.0,
    rtt_ns: int = 4_000_000,
):
    slope = 1000.0 * (1.0 + drift_ppm / 1_000_000.0)
    intercept = 5_000_000_000
    processing_ns = 200_000
    exchange_ns = rtt_ns + processing_ns
    for index in range(8):
        sensor_mid = start_sensor_us + index * 1_000_000
        pi_mid = round(intercept + slope * sensor_mid)
        mapper.observe_exchange(
            boot_id=boot_id,
            t1_pi_ns=MonotonicNanoseconds(pi_mid - exchange_ns // 2),
            sensor_receive_us=(sensor_mid - 100) & 0xFFFFFFFF,
            sensor_send_us=(sensor_mid + 100) & 0xFFFFFFFF,
            t4_pi_ns=MonotonicNanoseconds(pi_mid + exchange_ns // 2),
        )
    return slope, intercept


def test_clock_mapper_converges_and_maps_within_budget():
    mapper = SensorClockMapper()
    slope, intercept = _train(mapper)
    sensor_us = 8_500_000
    expected = round(intercept + slope * sensor_us)
    estimate = mapper.map_sample(
        boot_id=1,
        sensor_time_us=sensor_us,
        arrival_monotonic_ns=MonotonicNanoseconds(expected + 3_000_000),
    )

    assert mapper.state is ClockState.SYNCHRONIZED
    assert estimate.state is ClockState.SYNCHRONIZED
    assert estimate.captured_monotonic_ns == pytest.approx(expected, abs=2)
    assert estimate.estimated_error_ns < 20_000_000
    assert estimate.drift_ppm == pytest.approx(100.0, abs=0.1)


def test_u32_wrap_is_unwrapped_without_time_reversal():
    mapper = SensorClockMapper()
    start = 0xFFFFFFFF - 2_000_000
    slope, intercept = _train(mapper, start_sensor_us=start, drift_ppm=0.0)
    raw_after_wrap = (start + 8_500_000) & 0xFFFFFFFF
    unwrapped = start + 8_500_000
    expected = round(intercept + slope * unwrapped)
    estimate = mapper.map_sample(
        boot_id=1,
        sensor_time_us=raw_after_wrap,
        arrival_monotonic_ns=MonotonicNanoseconds(expected + 2_000_000),
    )

    assert estimate.state is ClockState.SYNCHRONIZED
    assert estimate.captured_monotonic_ns == pytest.approx(expected, abs=2)


def test_new_boot_resets_mapping_and_high_rtt_is_rejected():
    mapper = SensorClockMapper()
    _train(mapper)
    assert mapper.state is ClockState.SYNCHRONIZED

    reset = mapper.map_sample(
        boot_id=2,
        sensor_time_us=1,
        arrival_monotonic_ns=MonotonicNanoseconds(10_000_000_000),
    )
    assert reset.state is ClockState.RESET
    assert reset.captured_monotonic_ns == 10_000_000_000

    accepted = mapper.observe_exchange(
        boot_id=2,
        t1_pi_ns=MonotonicNanoseconds(10_000_000_000),
        sensor_receive_us=10,
        sensor_send_us=20,
        t4_pi_ns=MonotonicNanoseconds(10_100_000_000),
    )
    assert accepted is False


def test_excessive_drift_stays_degraded():
    mapper = SensorClockMapper(max_abs_drift_ppm=500.0)
    _train(mapper, drift_ppm=2000.0)
    assert mapper.state is ClockState.DEGRADED


def test_low_delay_filter_rejects_scheduling_delay_from_clock_fit():
    mapper = SensorClockMapper()
    slope = 1000.0 * (1.0 + 40.0 / 1_000_000.0)
    intercept = 7_000_000_000
    processing_ns = 200_000

    for index in range(20):
        sensor_mid = 100_000 + index * 1_000_000
        low_delay = index % 2 == 0
        rtt_ns = 24_000_000 if low_delay else 44_000_000
        # High-delay exchanges carry a deliberately asymmetric midpoint error.
        midpoint_error_ns = 500_000 if low_delay else 12_000_000
        pi_mid = round(intercept + slope * sensor_mid + midpoint_error_ns)
        exchange_ns = rtt_ns + processing_ns
        assert mapper.observe_exchange(
            boot_id=1,
            t1_pi_ns=MonotonicNanoseconds(pi_mid - exchange_ns // 2),
            sensor_receive_us=sensor_mid - 100,
            sensor_send_us=sensor_mid + 100,
            t4_pi_ns=MonotonicNanoseconds(pi_mid + exchange_ns // 2),
        )

    expected = round(intercept + slope * 20_500_000 + 500_000)
    estimate = mapper.map_sample(
        boot_id=1,
        sensor_time_us=20_500_000,
        arrival_monotonic_ns=MonotonicNanoseconds(expected + 5_000_000),
    )

    assert mapper.fit_point_count == 10
    assert mapper.fit_rtt_max_ns == 24_000_000
    assert mapper.drift_observed is True
    assert mapper.state is ClockState.SYNCHRONIZED
    assert estimate.captured_monotonic_ns == pytest.approx(expected, abs=4)
    assert estimate.estimated_error_ns < 20_000_000


def test_uniform_high_delay_remains_explicitly_degraded():
    mapper = SensorClockMapper()
    _train(mapper, drift_ppm=0.0, rtt_ns=42_000_000)

    assert mapper.fit_point_count == 8
    assert mapper.fit_rtt_max_ns == 42_000_000
    assert mapper.estimated_error_ns >= 21_000_000
    assert mapper.state is ClockState.DEGRADED


def test_short_exchange_burst_bootstraps_nominal_rate_without_fake_drift():
    mapper = SensorClockMapper(min_drift_span_us=5_000_000)
    intercept = 9_000_000_000

    for index, midpoint_jitter_ns in enumerate((0, 300_000, -200_000, 100_000, 0)):
        sensor_mid = 100_000 + index * 100_000
        pi_mid = intercept + 1000 * sensor_mid + midpoint_jitter_ns
        assert mapper.observe_exchange(
            boot_id=1,
            t1_pi_ns=MonotonicNanoseconds(pi_mid - 2_100_000),
            sensor_receive_us=sensor_mid - 100,
            sensor_send_us=sensor_mid + 100,
            t4_pi_ns=MonotonicNanoseconds(pi_mid + 2_100_000),
        )

    assert mapper.drift_observed is False
    assert mapper.drift_ppm == pytest.approx(0.0)
    assert mapper.state is ClockState.SYNCHRONIZED


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"low_delay_slack_ns": -1}, "low-delay slack"),
        ({"min_drift_span_us": 0}, "minimum drift span"),
        ({"max_exchange_age_ns": 0}, "maximum exchange age"),
    ],
)
def test_clock_filter_configuration_is_bounded(kwargs, message):
    with pytest.raises(ValueError, match=message):
        SensorClockMapper(**kwargs)


def test_future_projection_is_capped_at_arrival_and_error_is_preserved():
    mapper = SensorClockMapper()
    slope, intercept = _train(mapper)
    sensor_us = 8_500_000
    projected = round(intercept + slope * sensor_us)
    arrival = MonotonicNanoseconds(projected - 3_000_000)

    estimate = mapper.map_sample(
        boot_id=1,
        sensor_time_us=sensor_us,
        arrival_monotonic_ns=arrival,
    )

    assert estimate.captured_monotonic_ns == arrival
    assert estimate.estimated_error_ns >= 3_000_000
    assert mapper.causal_cap_samples == 1
    assert mapper.max_future_projection_ns == pytest.approx(3_000_000, abs=2)


def test_exchange_diagnostics_record_accepted_and_rejected_rtt_without_secrets():
    mapper = SensorClockMapper(max_rtt_ns=10_000_000)
    _train(mapper, rtt_ns=4_000_000)

    accepted = mapper.exchange_diagnostics
    assert len(accepted) == 8
    assert all(diagnostic.accepted for diagnostic in accepted)
    assert all(diagnostic.round_trip_ns == 4_000_000 for diagnostic in accepted)
    assert all(diagnostic.processing_ns == 200_000 for diagnostic in accepted)
    assert all(diagnostic.sensor_uncertainty_ns == 0 for diagnostic in accepted)
    assert accepted[-1].estimated_error_ns == mapper.estimated_error_ns
    assert accepted[-1].state is ClockState.SYNCHRONIZED

    assert mapper.observe_exchange(
        boot_id=1,
        t1_pi_ns=MonotonicNanoseconds(20_000_000_000),
        sensor_receive_us=9_000_000,
        sensor_send_us=9_000_200,
        t4_pi_ns=MonotonicNanoseconds(20_020_200_000),
    ) is False
    rejected = mapper.exchange_diagnostics[-1]
    assert rejected.accepted is False
    assert rejected.round_trip_ns == 20_000_000
    assert rejected.processing_ns == 200_000


def test_coarse_sensor_timestamp_uncertainty_is_in_clock_error_budget():
    mapper = SensorClockMapper()
    slope = 1000.0
    intercept = 5_000_000_000
    for index in range(6):
        sensor_us = 1_000_000 + index * 1_000_000
        pi_mid = round(intercept + slope * sensor_us)
        assert mapper.observe_exchange(
            boot_id=1,
            t1_pi_ns=MonotonicNanoseconds(pi_mid - 2_000_000),
            sensor_receive_us=sensor_us,
            sensor_send_us=sensor_us,
            t4_pi_ns=MonotonicNanoseconds(pi_mid + 2_000_000),
            sensor_uncertainty_ns=1_000_000,
        )

    assert mapper.state is ClockState.SYNCHRONIZED
    assert mapper.estimated_error_ns >= 3_000_000
    assert mapper.exchange_diagnostics[-1].sensor_uncertainty_ns == 1_000_000


def test_synchronized_mapping_degrades_when_clock_exchange_becomes_stale():
    mapper = SensorClockMapper(max_exchange_age_ns=5_000_000_000)
    slope, intercept = _train(mapper, drift_ppm=0.0)
    sensor_us = 15_000_000
    expected = round(intercept + slope * sensor_us)

    estimate = mapper.map_sample(
        boot_id=1,
        sensor_time_us=sensor_us,
        arrival_monotonic_ns=MonotonicNanoseconds(expected + 3_000_000),
    )

    assert estimate.state is ClockState.DEGRADED
    assert estimate.estimated_error_ns > mapper.synchronized_error_ns


def test_reset_state_is_reported_once_then_reacquires():
    mapper = SensorClockMapper()
    _train(mapper)

    reset = mapper.map_sample(
        boot_id=2,
        sensor_time_us=10,
        arrival_monotonic_ns=MonotonicNanoseconds(20_000_000_000),
    )
    acquiring = mapper.map_sample(
        boot_id=2,
        sensor_time_us=20,
        arrival_monotonic_ns=MonotonicNanoseconds(20_000_010_000),
    )

    assert reset.state is ClockState.RESET
    assert acquiring.state is ClockState.ACQUIRING


def test_clock_mapping_never_moves_published_capture_time_backward():
    mapper = SensorClockMapper()
    slope, intercept = _train(mapper)
    first_sensor_us = 8_500_000
    first_expected = round(intercept + slope * first_sensor_us)
    first = mapper.map_sample(
        boot_id=1,
        sensor_time_us=first_sensor_us,
        arrival_monotonic_ns=MonotonicNanoseconds(first_expected + 3_000_000),
    )
    second = mapper.map_sample(
        boot_id=1,
        sensor_time_us=first_sensor_us - 100,
        arrival_monotonic_ns=MonotonicNanoseconds(first_expected + 4_000_000),
    )

    assert second.captured_monotonic_ns == first.captured_monotonic_ns
    assert mapper.monotonic_correction_samples == 1
    assert mapper.max_monotonic_correction_ns > 0


def test_acquisition_fallback_is_included_in_monotonic_transition_guard():
    mapper = SensorClockMapper()
    acquisition = mapper.map_sample(
        boot_id=1,
        sensor_time_us=1_000_000,
        arrival_monotonic_ns=MonotonicNanoseconds(20_050_000_000),
    )
    intercept = 18_500_000_000
    for index in range(5):
        sensor_us = 1_020_000 + index * 100_000
        pi_mid_ns = intercept + sensor_us * 1000
        assert mapper.observe_exchange(
            boot_id=1,
            t1_pi_ns=MonotonicNanoseconds(pi_mid_ns - 2_000_000),
            sensor_receive_us=sensor_us,
            sensor_send_us=sensor_us,
            t4_pi_ns=MonotonicNanoseconds(pi_mid_ns + 2_000_000),
        )
    synchronized = mapper.map_sample(
        boot_id=1,
        sensor_time_us=1_520_000,
        arrival_monotonic_ns=MonotonicNanoseconds(20_530_000_000),
    )

    assert synchronized.captured_monotonic_ns >= acquisition.captured_monotonic_ns
    assert mapper.monotonic_correction_samples == 1


def test_agent_only_reports_good_after_synchronized_mapping():
    fake = FakeWearable()
    mapper = SensorClockMapper()
    slope, intercept = _train(mapper, boot_id=fake.boot_id, drift_ppm=0.0)
    agent = IMUAgentCore(expected_device_id=fake.device_id, clock_mapper=mapper)
    agent.accept_device_info(fake.device_info())
    agent.accept_status(fake.status())
    sensor_us = 8_500_000
    event = agent.accept_packet(
        fake.packet(sequence=1, sensor_time_us=sensor_us),
        arrival_monotonic_ns=MonotonicNanoseconds(
            round(intercept + slope * sensor_us) + 2_000_000
        ),
    )

    assert event is not None
    assert event.payload.clock_state is ClockState.SYNCHRONIZED
    assert event.quality.value == "good"
