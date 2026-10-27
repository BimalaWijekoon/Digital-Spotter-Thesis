from __future__ import annotations

from argparse import Namespace

import pytest

from digital_spotter.contracts import ClockState
from digital_spotter.imu.bench import (
    _failed_checks,
    _nearest_rank_p50,
    _nearest_rank_p95,
    _sensor_rate_hz,
    _validate_args,
)


def test_sensor_rate_uses_wrapped_measurement_time():
    times = [0xFFFFFF00, 0x00004D20, 0x00009B40]

    assert _sensor_rate_hz(times) == pytest.approx(50.0, rel=0.001)


def test_p95_uses_nearest_rank():
    assert _nearest_rank_p95(list(range(1, 21))) == 19
    assert _nearest_rank_p95([]) is None


def test_p50_uses_nearest_rank():
    assert _nearest_rank_p50(list(range(1, 21))) == 10
    assert _nearest_rank_p50([]) is None


def test_transport_gate_accepts_clean_uncalibrated_development_stream():
    failed = _failed_checks(
        configured_rate_hz=50,
        requested_duration_s=10.0,
        samples_received=500,
        observed_sensor_rate_hz=50.0,
        sequence_gaps=0,
        packets_rejected=0,
        notification_queue_drops=0,
        sensor_error_samples=0,
        status_sensor_error_delta=0,
        status_sensor_retry_delta=0,
        heap_decline_bytes=0,
        clock_state=ClockState.SYNCHRONIZED,
        clock_error_p95_ns=2_000_000,
        require_calibrated=False,
        calibrated_samples=0,
    )

    assert failed == ()


def test_transport_gate_names_each_material_failure():
    failed = _failed_checks(
        configured_rate_hz=50,
        requested_duration_s=10.0,
        samples_received=100,
        observed_sensor_rate_hz=40.0,
        sequence_gaps=2,
        packets_rejected=1,
        notification_queue_drops=3,
        sensor_error_samples=4,
        status_sensor_error_delta=2,
        status_sensor_retry_delta=3,
        heap_decline_bytes=64,
        clock_state=ClockState.DEGRADED,
        clock_error_p95_ns=20_000_000,
        require_calibrated=True,
        calibrated_samples=0,
        actuator_driver_error_delta=1,
    )

    assert failed == (
        "sample_count_below_90_percent",
        "sensor_rate_outside_2_percent",
        "sequence_gaps_detected",
        "packets_rejected",
        "notification_queue_drops",
        "sensor_error_flag_seen",
        "status_sensor_errors_increased",
        "status_sensor_retries_increased",
        "actuator_driver_errors_increased",
        "heap_declined",
        "clock_not_synchronized",
        "clock_error_p95_not_below_20_ms",
        "calibration_required",
    )


def test_bench_argument_limits_reject_unbounded_runs():
    args = Namespace(
        duration=3601.0,
        scan_timeout=15.0,
        connect_timeout=30.0,
        queue_size=512,
        initial_clock_exchanges=8,
        initial_clock_interval=0.1,
        clock_sync_interval=3.0,
    )

    with pytest.raises(ValueError, match="duration"):
        _validate_args(args)
